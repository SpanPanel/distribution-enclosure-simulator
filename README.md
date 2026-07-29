# dist-enc-sim

A fully-loaded, spec-conformant **distribution-enclosure simulator** and producer-side Homie 5 publisher for the eBus convention. It publishes a complete eBus Homie device tree (the enclosure plus a device for every circuit, lugs pair, and integrated DER: BESS, PV, EVSE, and MID) so external developers can build and test their consumers against a realistic SPAN-like panel without beta firmware, a live panel, or the commissioned add-ons (SPAN Drive/EVSE, BESS, PV, MID) a real installation would have.

It serves two roles:

- **Simulator / test fixture.** Drive it from a small YAML definition and it publishes a spec-conformant, fully-commissioned enclosure to any MQTT broker. Consumers (Home Assistant integrations, dashboards, SDK code) validate against it before shipping to the field.
- **Producer library.** The canonical eBus Homie publisher. A producer (a simulator, a real panel gateway, an LLM-driven model) hands the emitter a small per-tick driving signal (signed power per circuit, current time, grid-online flag) via `TickInputs`; the emitter derives all telemetry and publishes Homie-conformant retained MQTT with diff-only updates. The split is **identity = manifest (once at startup), telemetry = derived from TickInputs (per tick)**.

For the internals (the per-tick pipeline, the native BESS/load-shed devices, `/set` handling, the wire model) see [DESIGN.md](DESIGN.md); for the dev setup see [DEVELOPER.md](DEVELOPER.md).

## Requirements

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/)
- An MQTT broker (the bundled example starts its own in-process broker, so none is needed to try it)

## Install

Not published to PyPI. Pin via git URL or local path:

```toml
dist-enc-sim = { git = "https://github.com/electrification-bus/distribution-enclosure-simulator", rev = "<sha>" }
# or, during local development:
dist-enc-sim = { path = "../distribution-enclosure-simulator", editable = true }
```

It depends on `ebus-sdk`.

## Run

The repo ships a runnable example that starts an in-process MQTT broker, builds an emitter from a YAML definition, drives a couple of ticks, and prints the retained Homie topic map:

```bash
uv sync --group dev
uv run python examples/run_forty_tab_minimal.py             # print the retained topic tree
uv run python examples/run_forty_tab_minimal.py > tree.txt  # capture a transcript
```

The definition is `examples/forty_tab_minimal.yaml`: a fully-commissioned enclosure with circuits, upstream/downstream lugs, a BESS (plus its MID), PV, and SPAN Drive EVSEs. Each node is its own Homie device: the enclosure at `ebus/5/<enclosure-id>/…` and each circuit, lugs pair, and DER at its own topic root, for example `ebus/5/<circuit-id>/switch/relay`, `ebus/5/<lugs-id>/meter/current-a`, `ebus/5/<bess-id>-mid/grid/islanding-state`.

## Configure

The simulator is driven by a config that says which enclosure, which add-ons, and which circuits. There are two entry points.

### 1. Example YAML

`examples/forty_tab_minimal.yaml` is the quickest path. Top-level sections:

- `panel_config` — enclosure identity plus `total_tabs`, `main_size`, `postal_code`, `time_zone`, and `islandable`. A grid-forming BESS in an islandable enclosure automatically exposes an integrated MID (the islanding authority), mirroring a real SPAN panel.
- `circuit_templates` and `circuits` — per-circuit `tabs`, breaker rating, priority, relay behavior, and an optional `device_type` (`evse` or `pv`) to land a DER on a circuit.
- `bess` — nameplate capacity, charge mode, charge/discharge limits.
- `ticks` — the per-tick driving signal: signed watts per circuit and the grid-online flag.

### 2. DeviceManifest (programmatic)

A producer can build `DeviceInstance`s directly instead of using the YAML loader. Each device class's identity and static attributes live in the instance's `metadata`, validated once at startup by `ManifestPhysicsView` (missing required keys or malformed values raise `ManifestValidationError` naming the offending instance). The metadata keys per device class:

| entity_class | required keys | optional keys |
| --- | --- | --- |
| `panel` | `vendor-name`, `serial-number`, `firmware-version` (or `software-version`), `hardware-version`, `panel-size`, `main-breaker-rating-a`, `panel-model`, `postal-code`, `time-zone` | `service-voltage-v` (240), `line-voltage-v` (120), `islandable` (false) |
| `lugs` | `direction` (`upstream` \| `downstream`) | |
| `circuit` | `tab-numbers` (CSV ints), `breaker-rating-a`, `default-priority`, `relay-behavior`, `placement` (`upstream-of-lugs` \| `downstream-of-lugs`) | `always-on`, `pcs-priority` (0), `initial-consumed-wh` (0), `initial-produced-wh` (0) |
| `bess` | `vendor-name`, `nameplate-capacity-kwh` | `product-name`, `model`, `serial-number`, `firmware-version`/`software-version`, `relative-position` (`UPSTREAM`), `feed`, `initial-soe-kwh` |
| `pv` | `vendor-name`, `nameplate-capacity-w`, `inverter-type` (`hybrid` \| `ac-coupled`) | `product-name`, `serial-number`, `firmware-version`/`software-version`, `relative-position` (`IN_PANEL`), `feed` |
| `evse` | `vendor-name`, `product-name`, `part-number`, `serial-number`, `firmware-version` (or `software-version`), `max-current-a` | `feed` |
| `mid` | (none) | `vendor-name`, `serial-number`, `product-name`, `model`, `firmware-version`/`software-version`, `hardware-version` |

## Usage (as a producer library)

```python
import asyncio
import time

from dist_enc_sim import (
    BESSConfig, DeviceInstance, DeviceManifest, Emitter,
    LoadSheddingConfig, SetterRegistry, TickInputs,
)


async def main() -> None:
    manifest = DeviceManifest(instances=(
        DeviceInstance("panel", "abc-123", "Span Panel", metadata={
            "vendor-name": "Span", "serial-number": "abc-123",
            "firmware-version": "sim/v0.1.0", "hardware-version": "rev2",
            "panel-size": "40", "main-breaker-rating-a": "200",
            "panel-model": "MAIN_40", "postal-code": "94103",
            "time-zone": "America/Los_Angeles", "islandable": "true",
        }),
        DeviceInstance("lugs", "abc-123-lugs-up", "Upstream lugs", {"direction": "upstream"}),
        DeviceInstance("circuit", "kitchen", "Kitchen", metadata={
            "tab-numbers": "1", "breaker-rating-a": "20",
            "default-priority": "NICE_TO_HAVE", "relay-behavior": "controllable",
            "placement": "downstream-of-lugs",
        }),
        DeviceInstance("bess", "abc-123-bess", "Battery", metadata={
            "vendor-name": "Span", "nameplate-capacity-kwh": "13.5",
        }),
    ))
    bess_cfg = BESSConfig(instance_id="abc-123-bess", nameplate_capacity_kwh=13.5,
                          max_charge_w=3500.0, max_discharge_w=3500.0)

    mqtt = build_your_mqtt_client(will=Emitter.lwt_settings(manifest))
    await mqtt.connect()

    # Empty SetterRegistry: the emitter installs internal default handlers for the
    # settable properties. Register your own before construction to override them.
    emitter = Emitter(manifest, SetterRegistry(), mqtt, bess_configs=(bess_cfg,),
                      load_shedding_config=LoadSheddingConfig(soc_threshold_pct=20.0))
    await emitter.start()

    while True:
        await emitter.publish_tick(TickInputs(
            current_time=time.time(),
            grid_online=True,
            circuits=collect_powers_from_your_model(),  # instance_id -> signed watts
        ))
        await asyncio.sleep(1.0)


asyncio.run(main())
```

Read the most recently published state back through `emitter.last_snapshot`.

## Layout

- `src/dist_enc_sim/` — the package (`emitter.py`, `manifest.py`, `wire/` profiles + publishing, `native_devices/`); see [DESIGN.md](DESIGN.md).
- `examples/` — the runnable example and its YAML definition.
- `tests/` — the pytest suite.

## Tests

```bash
uv run pytest
uv run mypy --strict src/dist_enc_sim tests
uv run ruff check src tests
```

## Credits

Created by **Bill Flood** ([@cayossarian](https://github.com/cayossarian)); since updated to track the latest eBus specification. See [AUTHORS](AUTHORS).

## License

See [LICENSE](LICENSE).
