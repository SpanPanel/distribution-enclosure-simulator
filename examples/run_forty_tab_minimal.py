"""Run a tiny 40-tab emitter example against an in-process MQTT broker.

The script is intentionally producer-shaped: it builds a DeviceManifest from a
small YAML definition, creates an Emitter, drives a couple of ticks, and prints
the retained MQTT topic map. Redirect stdout to capture a transcript:

    uv run python examples/run_forty_tab_minimal.py > /tmp/ebus-topics.txt
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import logging
import socket
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Literal, Protocol, Self, cast, runtime_checkable

import aiomqtt
import yaml
from amqtt.broker import Broker  # type: ignore[import-untyped]

from ebus_emitter import (
    BESSConfig,
    DeviceInstance,
    DeviceManifest,
    Emitter,
    SetterRegistry,
    TickInputs,
)

_VALID_RELAY_BEHAVIORS = frozenset({"controllable", "non-controllable", "always-on"})
_VALID_INVERTER_TYPES = frozenset({"hybrid", "ac-coupled"})


@runtime_checkable
class _MqttClientLike(Protocol):
    def is_connected(self) -> bool: ...

    async def publish(
        self,
        topic: str,
        payload: bytes,
        qos: int = 0,
        retain: bool = False,
    ) -> None: ...

    async def subscribe(self, topic: str) -> None: ...


@dataclass(slots=True)
class RecordingAiomqttClient:
    host: str
    port: int
    will: aiomqtt.Will | None = None
    retained: dict[str, bytes] = field(default_factory=dict)
    published: list[tuple[str, bytes, bool]] = field(default_factory=list)
    _client: aiomqtt.Client | None = None

    async def __aenter__(self) -> Self:
        self._client = aiomqtt.Client(
            hostname=self.host,
            port=self.port,
            identifier="ebus-emitter-example",
            will=self.will,
        )
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._client is not None:
            await self._client.__aexit__(exc_type, exc, tb)
            self._client = None

    def is_connected(self) -> bool:
        return self._client is not None

    async def publish(
        self,
        topic: str,
        payload: bytes,
        qos: int = 0,
        retain: bool = False,
    ) -> None:
        if self._client is None:
            msg = "MQTT client is not connected"
            raise RuntimeError(msg)
        await self._client.publish(topic, payload=payload, qos=qos, retain=retain)
        self.published.append((topic, payload, retain))
        if retain:
            if payload:
                self.retained[topic] = payload
            else:
                self.retained.pop(topic, None)

    async def subscribe(self, topic: str) -> None:
        if self._client is None:
            msg = "MQTT client is not connected"
            raise RuntimeError(msg)
        await self._client.subscribe(topic)


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("amqtt").setLevel(logging.ERROR)
    logging.getLogger("homie").setLevel(logging.ERROR)
    logging.getLogger("transitions").setLevel(logging.ERROR)
    asyncio.run(_run(args.config, tick_count=args.ticks))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("forty_tab_minimal.yaml"),
        help="Example YAML definition to publish.",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=2,
        help="Number of configured ticks to publish.",
    )
    return parser.parse_args()


async def _run(config_path: Path, *, tick_count: int) -> None:
    profile = _load_profile(config_path)
    manifest = _build_manifest(profile)
    bess_config = _build_bess_config(profile)
    lwt_topic, lwt_payload, lwt_qos, lwt_retain = Emitter.lwt_settings(manifest)

    broker = _ExampleBroker()
    await broker.start()
    try:
        will = aiomqtt.Will(lwt_topic, lwt_payload, qos=lwt_qos, retain=lwt_retain)
        async with RecordingAiomqttClient(broker.host, broker.port, will=will) as mqtt:
            emitter = Emitter(
                manifest,
                SetterRegistry(),
                cast("_MqttClientLike", mqtt),
                bess_configs=(bess_config,) if bess_config is not None else (),
            )
            await emitter.start()
            for tick in _ticks(profile)[:tick_count]:
                await emitter.publish_tick(tick)

            _print_retained_topics(mqtt.retained)
    finally:
        await broker.stop()


@dataclass(slots=True)
class _ExampleBroker:
    host: str = "127.0.0.1"
    port: int = field(default_factory=lambda: _free_port())
    _broker: Broker | None = None

    async def start(self) -> None:
        self._broker = Broker(
            config={
                "listeners": {
                    "default": {"type": "tcp", "bind": f"{self.host}:{self.port}"},
                },
                "plugins": {
                    "amqtt.plugins.authentication.AnonymousAuthPlugin": {
                        "allow_anonymous": True,
                    },
                },
            },
        )
        await self._broker.start()
        await asyncio.sleep(0.05)

    async def stop(self) -> None:
        if self._broker is not None:
            with contextlib.suppress(Exception):
                await self._broker.shutdown()
            self._broker = None


def _load_profile(path: Path) -> Mapping[str, object]:
    loaded = yaml.safe_load(path.read_text())
    if not isinstance(loaded, Mapping):
        msg = f"{path} must contain a YAML mapping"
        raise ValueError(msg)
    return cast("Mapping[str, object]", loaded)


def _build_manifest(profile: Mapping[str, object]) -> DeviceManifest:
    panel = _as_mapping(profile["panel_config"], "panel_config")
    instances: list[DeviceInstance] = [
        _panel_instance(profile, panel),
        DeviceInstance("lugs", "lugs-upstream", "Upstream lugs", {"direction": "upstream"}),
        DeviceInstance("lugs", "lugs-downstream", "Downstream lugs", {"direction": "downstream"}),
        *_circuit_instances(profile),
    ]
    bess = _bess_instance(profile)
    if bess is not None:
        instances.append(bess)
    pv = _pv_instance(profile)
    if pv is not None:
        instances.append(pv)
    instances.extend(_evse_instances(profile))
    return DeviceManifest(instances=tuple(instances))


def _panel_instance(profile: Mapping[str, object], panel: Mapping[str, object]) -> DeviceInstance:
    panel_id = str(panel["serial_number"])
    total_tabs = _to_int(panel.get("total_tabs", 40))
    return DeviceInstance(
        "panel",
        panel_id,
        str(panel.get("display_name", "Example 40-tab Panel")),
        metadata={
            "vendor-name": "Span",
            "serial-number": panel_id,
            "firmware-version": str(profile.get("firmware_version", "example/v0.1.0")),
            "hardware-version": str(profile.get("hardware_version", "rev2")),
            "panel-size": str(total_tabs),
            "main-breaker-rating-a": str(_to_int(panel.get("main_size", 200))),
            "panel-model": f"MAIN_{total_tabs}",
            "postal-code": str(panel.get("postal_code", "94103")),
            "time-zone": str(panel.get("time_zone", "America/Los_Angeles")),
            "service-voltage-v": str(panel.get("service_voltage_v", 240.0)),
            "line-voltage-v": str(panel.get("line_voltage_v", 120.0)),
            "islandable": _bool_str(bool(panel.get("islandable", False))),
        },
    )


def _circuit_instances(profile: Mapping[str, object]) -> list[DeviceInstance]:
    templates = _optional_mapping(profile.get("circuit_templates"))
    instances: list[DeviceInstance] = []
    for idx, circuit in enumerate(_sequence_of_mappings(profile.get("circuits")), start=1):
        template = _optional_mapping(templates.get(str(circuit.get("template", ""))))
        relay_behavior = _normalise_relay_behavior(
            str(template.get("relay_behavior", "controllable")),
        )
        priority = str(template.get("priority", "NICE_TO_HAVE")).upper()
        breaker_rating = _to_float(
            template.get("breaker_rating", circuit.get("breaker_rating", 20.0)),
        )
        instance_id = _stable_circuit_id(str(circuit["id"]))
        instances.append(
            DeviceInstance(
                "circuit",
                instance_id,
                str(circuit.get("name", circuit["id"])),
                metadata={
                    "tab-numbers": ",".join(
                        str(_to_int(tab)) for tab in _as_sequence(circuit["tabs"])
                    ),
                    "breaker-rating-a": str(breaker_rating),
                    "default-priority": priority,
                    "relay-behavior": relay_behavior,
                    "placement": str(circuit.get("placement", "downstream-of-lugs")),
                    "always-on": _bool_str(relay_behavior == "always-on"),
                    "pcs-priority": str(circuit.get("pcs_priority", idx)),
                },
            ),
        )
    return instances


def _bess_instance(profile: Mapping[str, object]) -> DeviceInstance | None:
    bess = _optional_mapping(profile.get("bess"))
    if not bess.get("enabled"):
        return None
    metadata = {
        "vendor-name": str(bess.get("vendor", "Span")),
        "nameplate-capacity-kwh": str(bess.get("nameplate_capacity_kwh", 13.5)),
        "relative-position": str(bess.get("relative_position", "UPSTREAM")),
    }
    for source_key, metadata_key in (
        ("product_name", "product-name"),
        ("model", "model"),
        ("serial_number", "serial-number"),
        ("firmware_version", "firmware-version"),
        ("initial_soe_kwh", "initial-soe-kwh"),
    ):
        if source_key in bess:
            metadata[metadata_key] = str(bess[source_key])
    return DeviceInstance("bess", str(bess.get("instance_id", "bess")), "Battery", metadata)


def _pv_instance(profile: Mapping[str, object]) -> DeviceInstance | None:
    pv_feed = _first_feed_for_device_type(profile, "pv")
    if pv_feed is None:
        return None
    template = _first_template_for_device_type(profile, "pv")
    nameplate_w = template.get("nameplate_capacity_w", 5000.0)
    metadata = {
        "vendor-name": "Enphase",
        "nameplate-capacity-w": str(nameplate_w),
        "inverter-type": _normalise_inverter_type(
            str(template.get("inverter_type", "ac-coupled")),
        ),
        "relative-position": "IN_PANEL",
        "feed": pv_feed,
    }
    return DeviceInstance("pv", "pv", "Solar", metadata)


def _evse_instances(profile: Mapping[str, object]) -> list[DeviceInstance]:
    panel = _as_mapping(profile["panel_config"], "panel_config")
    panel_id = str(panel["serial_number"])
    evse_circuits = _circuits_for_device_type(profile, "evse")
    instances: list[DeviceInstance] = []
    for idx, circuit in enumerate(evse_circuits, start=1):
        instance_id = "evse" if idx == 1 else f"evse-{idx}"
        instances.append(
            DeviceInstance(
                "evse",
                instance_id,
                str(circuit.get("name", "EV Charger")),
                metadata={
                    "vendor-name": "SPAN",
                    "product-name": "SPAN Drive",
                    "part-number": "SPN-DRV-001",
                    "serial-number": (
                        f"SIM-EVSE-{panel_id}"
                        if idx == 1
                        else f"SIM-EVSE-{panel_id}-{idx}"
                    ),
                    "firmware-version": str(panel.get("firmware_version", "example/v0.1.0")),
                    "max-current-a": "32.0",
                    "feed": _stable_circuit_id(str(circuit["id"])),
                },
            ),
        )
    return instances


def _build_bess_config(profile: Mapping[str, object]) -> BESSConfig | None:
    bess = _optional_mapping(profile.get("bess"))
    if not bess.get("enabled"):
        return None
    mode: Literal["self-consumption", "backup-only"] = (
        "backup-only" if bess.get("charge_mode") == "backup-only" else "self-consumption"
    )
    return BESSConfig(
        instance_id=str(bess.get("instance_id", "bess")),
        nameplate_capacity_kwh=_to_float(bess.get("nameplate_capacity_kwh", 13.5)),
        max_charge_w=_to_float(bess.get("max_charge_w", 3500.0)),
        max_discharge_w=_to_float(bess.get("max_discharge_w", 3500.0)),
        backup_reserve_pct=_to_float(bess.get("backup_reserve_pct", 20.0)),
        charge_mode=mode,
    )


def _ticks(profile: Mapping[str, object]) -> list[TickInputs]:
    ticks: list[TickInputs] = []
    evse_feeds = {
        ("evse" if idx == 1 else f"evse-{idx}"): _stable_circuit_id(str(circuit["id"]))
        for idx, circuit in enumerate(_circuits_for_device_type(profile, "evse"), start=1)
    }
    for item in _sequence_of_mappings(profile.get("ticks")):
        circuit_values = _as_mapping(item["circuits"], "tick.circuits")
        circuits = {
            _stable_circuit_id(source_id): _to_float(power)
            for source_id, power in circuit_values.items()
        }
        ticks.append(
            TickInputs(
                current_time=_to_float(item.get("current_time", len(ticks))),
                grid_online=bool(item.get("grid_online", True)),
                circuits=circuits,
                evse={
                    evse_id: circuits.get(feed_id, 0.0)
                    for evse_id, feed_id in evse_feeds.items()
                },
            ),
        )
    return ticks


def _print_retained_topics(retained: Mapping[str, bytes]) -> None:
    for topic in sorted(retained):
        payload = retained[topic].decode()
        if topic.endswith("/$description"):
            payload = json.dumps(json.loads(payload), sort_keys=True)
        print(f"{topic} {payload}")


def _circuits_for_device_type(
    profile: Mapping[str, object],
    device_type: str,
) -> list[Mapping[str, object]]:
    templates = _optional_mapping(profile.get("circuit_templates"))
    circuits = []
    for circuit in _sequence_of_mappings(profile.get("circuits")):
        template = _optional_mapping(templates.get(str(circuit.get("template", ""))))
        if template.get("device_type") == device_type:
            circuits.append(circuit)
    return circuits


def _first_feed_for_device_type(profile: Mapping[str, object], device_type: str) -> str | None:
    circuits = _circuits_for_device_type(profile, device_type)
    if not circuits:
        return None
    return _stable_circuit_id(str(circuits[0]["id"]))


def _first_template_for_device_type(
    profile: Mapping[str, object],
    device_type: str,
) -> Mapping[str, object]:
    circuits = _circuits_for_device_type(profile, device_type)
    if not circuits:
        return {}
    templates = _optional_mapping(profile.get("circuit_templates"))
    return _optional_mapping(templates.get(str(circuits[0].get("template", ""))))


def _normalise_relay_behavior(raw: str) -> str:
    candidate = raw.lower().replace("_", "-")
    return candidate if candidate in _VALID_RELAY_BEHAVIORS else "controllable"


def _normalise_inverter_type(raw: str) -> str:
    candidate = raw.lower().replace("_", "-")
    return candidate if candidate in _VALID_INVERTER_TYPES else "ac-coupled"


def _stable_circuit_id(source_id: str) -> str:
    return hashlib.sha256(f"ebus-emitter-example:{source_id}".encode()).hexdigest()[:32]


def _bool_str(value: bool) -> str:
    return "true" if value else "false"


def _as_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        msg = f"{name} must be a mapping"
        raise ValueError(msg)
    return cast("Mapping[str, object]", value)


def _optional_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return cast("Mapping[str, object]", value)
    return {}


def _sequence_of_mappings(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [_as_mapping(item, "sequence item") for item in value]


def _as_sequence(value: object) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        msg = "expected a sequence"
        raise ValueError(msg)
    return value


def _to_float(value: object) -> float:
    if isinstance(value, int | float | str):
        return float(value)
    msg = f"expected a numeric value, got {value!r}"
    raise ValueError(msg)


def _to_int(value: object) -> int:
    return int(_to_float(value))


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


if __name__ == "__main__":
    main()
