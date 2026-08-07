"""Bring-your-own-transport: publishing through a client the caller owns.

ebus-sdk supports this at the ``Device`` level (``Device(mqttc=...)``, with an
explicit guarantee that it never starts or stops a client it did not build).
These tests cover the emitter honouring the same contract, so a host that
already owns its MQTT connection — a Home Assistant add-on, say, whose MQTT
integration is ``single_config_entry`` and which forbids background threads —
can publish an eBus tree through it rather than having a second connection
opened underneath it.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest
from ebus_mqtt_client import MqttClient

from ebus_panel_sim import (
    DeviceInstance,
    DeviceManifest,
    Emitter,
    EmitterStateError,
    SetterRegistry,
    TickInputs,
)
from ebus_panel_sim.exceptions import ManifestValidationError
from ebus_panel_sim.wire.graph_builder import build_graph
from ebus_panel_sim.wire.mapping_loader import load_mapping_table
from ebus_panel_sim.wire.profile_loader import load_profiles

from .conftest import effective_retained

ROOT_STATE = "ebus/5/p1/$state"


class RecordingTransport:
    """Satisfies ebus-sdk's ``MqttDeviceTransport``: publish, subscribe,
    ``is_connected`` and ``is_running``, and nothing else.

    Deliberately has no ``start``/``stop``. The SDK's contract is that it never
    calls them on an injected client, and a transport without them turns a
    violation into an ``AttributeError`` here rather than a silently closed
    connection in production.
    """

    def __init__(self, *, connected: bool = True) -> None:
        self.published: list[tuple[str, str, int, bool]] = []
        self.subscribed: list[str] = []
        self.is_running = True
        self._connected = connected

    def is_connected(self) -> bool:
        return self._connected

    def publish(self, topic: str, data: str, qos: int = 1, retain: bool = False) -> object:
        self.published.append((topic, data, qos, retain))
        return None

    def subscribe(self, sub: str, param: object = None, qos: int = 1) -> object:
        self.subscribed.append(sub)
        return None

    @property
    def retained(self) -> dict[str, str]:
        """The effective retained view a late-joining consumer would see.

        Delegated to the shared rule so this and ``PahoRecorder`` cannot drift:
        the earlier version here stored an empty retained payload as ``""``
        instead of retracting the topic, which reported retracted topics as
        present.
        """
        return effective_retained(self.published)


def _manifest() -> DeviceManifest:
    return DeviceManifest(
        instances=(
            DeviceInstance(
                "panel",
                "p1",
                "Span",
                metadata={
                    "vendor-name": "Span",
                    "serial-number": "p1",
                    "firmware-version": "r2026",
                    "hardware-version": "rev2",
                    "panel-size": "32",
                    "main-breaker-rating-a": "200",
                    "panel-model": "MAIN_32",
                    "postal-code": "94103",
                    "time-zone": "America/Los_Angeles",
                },
            ),
            DeviceInstance(
                "circuit",
                "c1",
                "Kitchen",
                metadata={
                    "tab-numbers": "1",
                    "breaker-rating-a": "20",
                    "default-priority": "NICE_TO_HAVE",
                    "relay-behavior": "controllable",
                    "placement": "downstream-of-lugs",
                },
            ),
        )
    )


def test_injected_transport_receives_the_tree() -> None:
    """The whole point: the caller's client carries the traffic."""
    transport = RecordingTransport()
    emitter = Emitter(_manifest(), SetterRegistry(), mqttc=transport)
    emitter.start()
    emitter.publish_tick(TickInputs(current_time=0.0, grid_online=True, circuits={"c1": 200.0}))

    topics = [t for t, _d, _q, _r in transport.published]
    assert topics, "nothing was published through the injected transport"
    for device_id in ("p1", "c1"):
        assert any(f"/{device_id}/$description" in t for t in topics), (
            f"no $description for {device_id}"
        )
        assert any(f"/{device_id}/$state" in t for t in topics), f"no $state for {device_id}"
    assert any("meter/active-power" in t for t in topics), (
        "no property values reached the transport"
    )


def test_mqtt_cfg_and_mqttc_together_is_rejected() -> None:
    """Two answers to "which connection" is a producer-side bug, and silently
    preferring one would hide it until the wrong broker had the traffic."""
    with pytest.raises(EmitterStateError):
        Emitter(
            _manifest(),
            SetterRegistry(),
            mqtt_cfg={"host": "localhost", "port": 1883},
            mqttc=RecordingTransport(),
        )


def test_start_does_not_block_on_an_unconnected_injected_client() -> None:
    """``start()`` waits for the link only for a client it built.

    The caller owns an injected client's lifecycle and its timing, and the SDK
    never starts one — so there is nothing to wait for, and waiting would stall
    the loop such a client is likely being driven on. Retained values republish
    on connect regardless.
    """
    transport = RecordingTransport(connected=False)
    emitter = Emitter(_manifest(), SetterRegistry(), mqttc=transport)

    started = time.monotonic()
    emitter.start(connect_timeout_s=30.0)
    elapsed = time.monotonic() - started

    # Timed rather than merely observed to return: without this the call polls
    # is_connected() for the full timeout, which a slow test would pass and only
    # a stalled event loop in production would reveal.
    assert elapsed < 1.0, f"start() blocked for {elapsed:.1f}s on a client it does not own"

    emitter.publish_tick(TickInputs(current_time=0.0, grid_online=True, circuits={"c1": 200.0}))


def test_stop_never_stops_a_client_it_did_not_build() -> None:
    """Tearing down the caller's connection would take out whatever else they
    were using it for. ``RecordingTransport`` has no ``stop``, so an attempt
    raises rather than passing quietly.

    On its own this proves only that nothing was stopped, which an ungraceful
    path that did nothing at all would also satisfy. The two tests below are
    what pin that it still did its work."""
    transport = RecordingTransport()
    emitter = Emitter(_manifest(), SetterRegistry(), mqttc=transport)
    emitter.start()

    emitter.stop(graceful=False)
    emitter.stop(graceful=True)


def test_graceful_stop_leaves_the_caller_holding_a_live_client_and_a_mute_emitter() -> None:
    """The trap the README's own recipe sets, pinned so the docstring stays true.

    ebus-sdk's ``Device.stop()`` clears the root's transport reference on *both*
    paths — correctly declining to stop a client it did not build, but detaching
    from it either way. The caller is left with a connection that is still open
    and still connected, and an ``Emitter`` that can no longer publish through
    it.

    That matters because step 4 of the documented wiring hands
    ``republish_tree`` to ``client.on_connect_callback``. After a graceful stop
    that callback is still attached to a live client and does nothing at all, so
    a later reconnect quietly fails to restore the tree — no exception, no log,
    and the retained store stays as the broker left it.

    Asserted rather than merely written down because it is invisible: every
    observable here is a *non*-event.
    """
    transport = RecordingTransport()
    emitter = Emitter(_manifest(), SetterRegistry(), mqttc=transport)
    emitter.start()
    emitter.publish_tick(TickInputs(current_time=0.0, grid_online=True, circuits={"c1": 200.0}))

    emitter.stop(graceful=True)

    # The caller's connection is untouched: theirs to close, on their schedule.
    assert transport.is_running is True
    assert transport.is_connected() is True

    # But the emitter is detached, so the on-connect hook is now a no-op.
    transport.published.clear()
    emitter.republish_tree()
    assert transport.published == [], (
        "republish_tree() published after a graceful stop; Emitter.stop's docstring "
        "and the README both say it goes mute, so one of them is now wrong"
    )


def test_ungraceful_stop_leaves_the_root_lost_on_an_injected_transport() -> None:
    """An injected transport is where a silent ungraceful stop is least
    recoverable, not most.

    The caller's connection outlives the emitter, so the broker never sees a
    disconnect and would never deliver the registered will either. Publishing
    the payload here is the only route to ``lost``; without it the retained tree
    claims ``ready`` indefinitely with no second chance.
    """
    transport = RecordingTransport()
    emitter = Emitter(_manifest(), SetterRegistry(), mqttc=transport)
    emitter.start()
    emitter.stop(graceful=False)

    assert transport.retained[ROOT_STATE] == "lost"


def test_ungraceful_stop_on_an_injected_transport_uses_the_sdk_will_descriptor() -> None:
    """Byte-identical to what the broker would have delivered from the
    registered will, or the simulation is a fiction. Same guarantee the owned
    path gets, sourced from the same ``Device.will()``."""
    transport = RecordingTransport()
    emitter = Emitter(_manifest(), SetterRegistry(), mqttc=transport)
    emitter.start()
    will = emitter._root.will()
    emitter.stop(graceful=False)

    assert transport.retained[will["topic"]] == will["payload"]


def test_build_graph_requires_exactly_one_connection_source() -> None:
    """Two answers to "which connection" is a producer-side bug that would
    otherwise surface as traffic on the wrong broker, and zero answers builds a
    tree that can never publish. ``Emitter`` guards its own pair; this pins the
    guard on the function underneath, which is reachable directly and whose
    ``mqtt_cfg`` argument this change weakened from required to defaulted."""
    manifest = _manifest()
    mapping = load_mapping_table()
    profiles = load_profiles(variant="span")

    with pytest.raises(ManifestValidationError):
        build_graph(manifest, mapping, profiles)

    with pytest.raises(ManifestValidationError):
        build_graph(
            manifest,
            mapping,
            profiles,
            mqtt_cfg={"host": "h", "port": 1883},
            mqttc=RecordingTransport(),
        )


def test_mqtt_device_transport_is_nameable_from_the_public_package() -> None:
    """``Emitter(mqttc=...)`` is public API typed with this, so a downstream
    annotating what it passes must be able to import it from here rather than
    reaching into ``ebus_sdk`` — the coupling the wire seam exists to spare
    them."""
    from ebus_panel_sim import MqttDeviceTransport as Exported

    assert isinstance(RecordingTransport(), Exported)


def test_lwt_settings_is_answerable_without_an_emitter_and_names_the_same_tree() -> None:
    """Both halves matter, and they pull against each other.

    It has to be answerable with no ``Emitter`` in existence, because the will
    rides the CONNECT packet and so must be on the client before the client that
    would be injected has connected. But it also has to describe the device the
    built tree will actually publish as — a will naming a different root is worse
    than no will, since it reports the wrong device dead.
    """
    manifest = _manifest()

    lwt = Emitter.lwt_settings(manifest)  # no Emitter, no client, no connection

    emitter = Emitter(manifest, SetterRegistry(), mqttc=RecordingTransport())
    assert lwt == emitter._root.will()


def test_republish_tree_restores_the_whole_retained_tree() -> None:
    """The SDK wires this on-connect only for a client it built; an injected one
    reaches ``connect_broker``'s ``if self.mqttc`` return first. Without a way to
    call it, a broker that loses its retained store never gets the tree back.

    Asserts the whole retained set returns, not merely that a couple of
    ``$description`` topics appear. Against a real broker the failure this
    prevents was 5 topics of 56 — a handful of later-tick values with every
    ``$description`` missing — which a spot-check on two devices would pass.
    """
    transport = RecordingTransport()
    emitter = Emitter(_manifest(), SetterRegistry(), mqttc=transport)
    emitter.start()
    emitter.publish_tick(TickInputs(current_time=0.0, grid_online=True, circuits={"c1": 200.0}))
    before = effective_retained(transport.published)

    # Simulate the broker losing its retained store, then the caller's client
    # reconnecting and invoking the hook the README tells them to wire.
    transport.published.clear()
    emitter.republish_tree()
    after = effective_retained(transport.published)

    missing = sorted(set(before) - set(after))
    assert not missing, f"{len(missing)} of {len(before)} retained topics did not come back"


def test_stop_never_stops_an_injected_client_that_is_itself_an_mqtt_client() -> None:
    """The production injection, and the only shape that tests the ownership rule.

    ``RecordingTransport`` cannot catch this. It is not an ``MqttClient``, so
    ``owned_client()``'s isinstance narrowing rejects it on *type* before
    ownership is ever consulted — meaning the whole suite passes with the
    ownership flag deleted and the guard left as a bare type check. What a caller
    actually injects is an ``MqttClient`` they drive on their own loop via
    ``asyncio_driver``, which that type check waves straight through and tears
    down. Ownership is a fact about who built the client, not about its class.
    """
    client = MqttClient.from_config({"host": "localhost", "port": 1883}, client_id="caller-owned")
    client.stop = MagicMock()  # type: ignore[method-assign]

    emitter = Emitter(_manifest(), SetterRegistry(), mqttc=client)
    emitter.start()
    emitter.stop(graceful=False)

    assert client.stop.called is False, "tore down a connection the caller owns"


def test_ungraceful_stop_moves_the_device_state_on_an_injected_transport() -> None:
    """The wire and the object must agree here as they do on the owned path.

    0.3.3 fixed that disagreement but sourced the fix through ``owned_client()``,
    which returns None for a caller-supplied transport — so this path kept both
    halves of the bug: object on ``ready``, nothing on the wire at all.
    """
    transport = RecordingTransport()
    emitter = Emitter(_manifest(), SetterRegistry(), mqttc=transport)
    emitter.start()
    emitter.stop(graceful=False)

    assert transport.retained[ROOT_STATE] == "lost"
    assert emitter._root.state().value == "lost"


def test_a_later_refresh_tree_re_announces_lost_on_an_injected_transport() -> None:
    """The injected transport is the only path where this is reachable rather
    than hypothetical.

    ``refresh_tree()`` republishes from the Device's own state, and the SDK asks
    a bring-your-own-transport caller to wire it onto their client's on-connect
    handler. An owned client's socket closes behind ``stop()`` so it never gets
    the chance; a caller's connection stays up and reconnects. If the ungraceful
    stop left the object on ``ready``, that hook resurrects ``ready`` over the
    ``lost`` — the stale-tree bug 0.3.1 removed, restored on the one
    configuration that can actually trigger it.
    """
    transport = RecordingTransport()
    emitter = Emitter(_manifest(), SetterRegistry(), mqttc=transport)
    emitter.start()
    emitter.stop(graceful=False)
    emitter._root.refresh_tree()

    assert transport.retained[ROOT_STATE] == "lost"
