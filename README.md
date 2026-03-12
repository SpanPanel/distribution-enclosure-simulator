# ebus-emitter

Producer-side Homie 5 publisher for the eBus convention. The producer (a
simulator, a real panel gateway, an LLM-driven modelling agent) hands the
emitter a small per-tick driving signal — signed power per circuit, current
time, grid-online flag — and the emitter publishes Homie-conformant retained
MQTT messages with diff-only updates.

The emitter knows about **all** the device types the eBus convention covers
today — `panel`, `lugs`, `circuit`, `pv`, `evse`, `bess` — and ships a Homie 5
profile for each (capabilities, properties, datatypes, units, settability,
topic placement). Device identity and static attributes (vendor name, serial,
firmware, ratings, tab number, breaker rating, nameplate capacity, voltage,
etc.) come from the producer once at startup via `DeviceManifest.metadata`;
dynamic state (per-circuit power, energy accumulators, relay state, currents,
panel meter aggregates) is derived inside the emitter from the per-tick
driving signal. The split is **identity = manifest, telemetry = derived from
TickInputs**.

Two of those device types are also **native devices** with behaviour that runs
inside the emitter (BESS dispatch, load shedding); see `Native devices` below.
The rest are pure publishers — the emitter owns their topic layout, property
schema, and field derivation.

## Purpose

The emitter serves two roles:

1. **Test and validation layer**: Exhibits real panel behavior to SDK consumers
   without requiring beta firmware or a live panel. Allows teams building on the
   eBus SDK to validate their code against new firmware changes before they ship
   to the field. Validates correct Homie 5 wire production by verifying that
   device profiles, topic structure, and data derivation logic match the live
   panel schema. See the `examples/` directory for a minimal standalone example
   that demonstrates correct output.

2. **Producer library**: Acts as the canonical MQTT publisher for any producer
   (simulator, real gateway, modelling agent) that wants to emit eBus-conformant
   topics. Producers hand the emitter a per-tick driving signal and receive
   correct Homie-formatted retained MQTT messages, abstracting away device
   topology, property derivation, energy integration, and relay state management.

## Install

This package is **not** published to PyPI. Pin via local path or git URL:

```toml
# pyproject.toml — local-path dep during development
ebus-emitter = { path = "../emitter", editable = true }

# or git URL
"ebus-emitter @ git+https://github.com/<owner>/<repo>@<sha>"
```

It depends on the local `ebus-sdk` (also not on PyPI):

```toml
ebus-sdk = { path = "../ebus-sdk", editable = true }
```

## Architecture in one paragraph

The producer builds a `DeviceManifest` (identity + physics keys per device) at
startup and hands it to `Emitter` along with optional `BESSConfig` and
`LoadSheddingConfig`. Each tick the producer builds a `TickInputs` (signed
power per circuit, current time, grid-online, panel envelope) and calls
`emitter.publish_tick(tick_inputs)`. Inside, the emitter resolves BESS
dispatch, decides load-shedding, applies relay-state precedence (always-on >
/set > shed > default-CLOSED), gates per-circuit power, integrates energy via
`EnergyIntegrator`, computes per-leg currents and panel meter aggregates via
`PanelMeter`, and publishes the Homie diff to MQTT.

## Usage

```python
import asyncio
import time

from ebus_emitter import (
    BESSConfig, DeviceInstance, DeviceManifest, Emitter,
    LoadSheddingConfig, SetterRegistry, TickInputs,
)

async def main():
    manifest = DeviceManifest(instances=(
        DeviceInstance(
            entity_class="panel", instance_id="abc-123",
            display_name="Span Panel",
            metadata={
                "vendor-name": "Span",
                "serial-number": "abc-123",
                "firmware-version": "sim/v0.1.0",
                "hardware-version": "rev2",
                "panel-size": "40",
                "main-breaker-rating-a": "200",
                "panel-model": "MAIN_40",
                "postal-code": "94103",
                "time-zone": "America/Los_Angeles",
            },
        ),
        DeviceInstance(
            entity_class="lugs", instance_id="abc-123-lugs-upstream",
            display_name="Upstream lugs", metadata={"direction": "upstream"},
        ),
        DeviceInstance(
            entity_class="lugs", instance_id="abc-123-lugs-downstream",
            display_name="Downstream lugs", metadata={"direction": "downstream"},
        ),
        DeviceInstance(
            entity_class="circuit", instance_id="kitchen", display_name="Kitchen",
            metadata={
                "tab-numbers": "1",
                "breaker-rating-a": "20",
                "default-priority": "NICE_TO_HAVE",
                "relay-behavior": "controllable",
                "placement": "downstream-of-lugs",
            },
        ),
        DeviceInstance(
            entity_class="bess", instance_id="abc-123-bess", display_name="Battery",
            metadata={"vendor-name": "Span", "nameplate-capacity-kwh": "13.5"},
        ),
    ))

    bess_cfg = BESSConfig(
        instance_id="abc-123-bess",
        nameplate_capacity_kwh=13.5,
        max_charge_w=3500.0,
        max_discharge_w=3500.0,
        backup_reserve_pct=20.0,
        charge_mode="self-consumption",
    )
    shed_cfg = LoadSheddingConfig(soc_threshold_pct=20.0)

    lwt = Emitter.lwt_settings(manifest)
    mqtt = build_your_mqtt_client(will=lwt, ...)
    await mqtt.connect()

    # Empty SetterRegistry — emitter installs internal default handlers for
    # the four /set-able properties. Producers that want custom routing
    # register their own handler before construction.
    emitter = Emitter(manifest, SetterRegistry(), mqtt,
                      bess_configs=(bess_cfg,), load_shedding_config=shed_cfg)
    await emitter.start()

    while True:
        circuit_powers = collect_powers_from_your_model()  # producer's job
        await emitter.publish_tick(TickInputs(
            current_time=time.time(),
            grid_online=True,
            circuits=circuit_powers,        # instance_id -> signed watts
        ))
        await asyncio.sleep(1.0)

asyncio.run(main())
```

## Example runtime

The repository includes a slim 40-tab-style example that starts an in-process
Python MQTT broker, builds an emitter manifest from a small YAML definition, and
prints the retained Homie topic map to stdout:

```bash
uv run python examples/run_forty_tab_minimal.py
```

The definition lives in `examples/forty_tab_minimal.yaml`. It uses a 40-tab
panel envelope but only declares the few circuits needed to demonstrate the
schema: two standalone 120 V loads, two SPAN Drive EVSE feed circuits, one PV
feed circuit, upstream/downstream lugs, a BESS on upstream lugs, `core`, `pcs`,
and `power-flows`. Redirect stdout if you want a retained-topic transcript:

```bash
uv run python examples/run_forty_tab_minimal.py > /tmp/ebus-topics.txt
```

## What lives where

| Concern                                                                   | Owner                   |
|---------------------------------------------------------------------------|-------------------------|
| Homie wire (topics, retained, LWT)                                        | emitter                 |
| Device profiles for `panel` / `lugs` / `circuit` / `pv` / `evse` / `bess` | emitter                 |
| Property graph + diff publishing                                          | emitter                 |
| Settable-property routing (`/set` -> internal state)                      | emitter                 |
| Relay state machine (always-on > /set > shed > default-CLOSED)            | emitter                 |
| BESS dispatch (charge/discharge/idle)                                     | emitter                 |
| BESS SOC/SOE integration                                                  | emitter                 |
| Load shedding policy (SOC threshold, off-grid priority)                   | emitter                 |
| Energy integration (per-circuit consumed/produced Wh)                     | emitter                 |
| Per-leg current calculation                                               | emitter                 |
| Panel meter aggregation (grid power, feedthrough, mode flags)             | emitter                 |
| Device identity + static attributes (vendor, serial, ratings, tabs, etc.) | producer (via manifest) |
| Per-circuit / per-EVSE signed power                                       | producer (per tick)     |
| `current_time` / `grid_online` / panel envelope (door, links)             | producer (per tick)     |
| Energy accumulator persistence across emitter restart                     | producer (via seed API) |
| Weather, schedules, time-of-use rates, modelling                          | producer                |
| Recorder / replay history                                                 | producer                |

## Manifest physics keys

`ManifestPhysicsView` is the typed accessor for the physics-relevant subset of
`DeviceInstance.metadata`. Validated once at `Emitter.__init__`; missing
required keys, malformed values, and contradictory physics (e.g. dipole
declared on tabs all on the same leg) raise `ManifestValidationError` with the
offending instance_id.

| entity_class | required keys | optional keys |
| --- | --- | --- |
| `panel` | `vendor-name`, `serial-number`, `firmware-version` (or `software-version`), `hardware-version`, `panel-size`, `main-breaker-rating-a`, `panel-model`, `postal-code`, `time-zone` | `service-voltage-v` (240), `line-voltage-v` (120), `islandable` (false) |
| `lugs` | `direction` (`upstream` or `downstream`) | |
| `circuit` | `tab-numbers` (CSV ints), `breaker-rating-a`, `default-priority`, `relay-behavior`, `placement` (`upstream-of-lugs` or `downstream-of-lugs`) | `always-on` (derived from relay-behavior), `pcs-priority` (0), `initial-consumed-wh` (0), `initial-produced-wh` (0) |
| `bess` | `vendor-name`, `nameplate-capacity-kwh` | `product-name`, `model`, `serial-number`, `firmware-version`/`software-version`, `relative-position` (`UPSTREAM`), `feed`, `initial-soe-kwh` |
| `pv` | `vendor-name`, `nameplate-capacity-w`, `inverter-type` (`hybrid` or `ac-coupled`) | `product-name`, `serial-number`, `firmware-version`/`software-version`, `relative-position` (`IN_PANEL`), `feed` |
| `evse` | `vendor-name`, `product-name`, `part-number`, `serial-number`, `firmware-version` (or `software-version`), `max-current-a` | `feed` |

## Tab → leg convention

`legs_for_tabs((tab,...)) -> tuple[Leg, ...]` is the single source of truth for
the US residential split-phase convention: odd-numbered tabs land on L1,
even-numbered tabs on L2. A 240 V dipole circuit occupies two adjacent tabs
(e.g. `(1, 2)`) — one per leg.

The function is isolated in `ebus_emitter.conventions.tab_legs` so non-US /
3-phase support can land here later without touching `PanelMeter` or per-leg
current calculations.

## Native devices

### BESS — `ebus_emitter.native_devices.bess`

Owns dispatch decision, SOC/SOE accumulation, mode behaviour
(self-consumption / backup-only), charge/discharge windows, and the
backup-reserve floor. Instantiated automatically when `Emitter` is constructed
with a `bess_config` argument.

**Per-tick inputs** (read from `TickInputs`):

- `current_time` — UNIX epoch seconds, used for charge/discharge window evaluation.
- `grid_online: bool` — when False, BESS discharges to meet `load_demand - pv_available`.
- `load_demand_w` (derived) — Σ positive circuit powers.
- `pv_available_w` (derived) — |Σ negative circuit powers|.

**Per-tick outputs** (written into `snapshot.battery`):

- `soe_percentage`, `soe_kwh`
- `active_power_w` (positive = discharging, negative = charging)
- `nameplate_capacity_kwh`, `connected`

**Mid-run config changes** — call `emitter.update_bess_config(new_config)`.
The device swaps the `BESSConfig` reference; SOC/SOE state persists across
the swap. This is the path for dashboard edits to charge windows, mode, max
rates, etc.

**Persistence across emitter restart** — call `emitter.seed_bess_soe(instance_id, soe_kwh)`
between `__init__` and `start()` (or declare `initial-soe-kwh` in the manifest)
to restore the last-known SOC/SOE.

Subclassing `BESSDevice` is supported for vendor-variant behaviour (Powerwall
vs Enphase IQ etc.) without a plugin framework.

### Load shedding — `ebus_emitter.native_devices.load_shedding`

When the grid is offline, the policy returns the set of circuit instance_ids
whose priority is `OFF_GRID`, or `SOC_THRESHOLD` when the live SOC falls
below `soc_threshold_pct`. The emitter writes that decision into the
`RelayResolver` shed map; final relay state is then resolved per the
precedence rules (always-on > /set > shed > default-CLOSED).

Mid-run config: `emitter.update_load_shedding_config(new_config)`.

## `/set` command behaviour

`/set` commands arrive on live-panel-shaped Homie settable-property topics (e.g.
`ebus/5/<panel>/<circuit>/relay/set`) and are dispatched through the
`SetterRegistry`. The emitter installs **internal default handlers** for the
schema settable properties when the producer hasn't supplied one:

| Entity class | Property                       | Effect                                              |
|--------------|--------------------------------|-----------------------------------------------------|
| circuit      | `circuit/relay`                | Updates `RelayResolver` user override               |
| circuit      | `circuit/shed-priority`        | Updates emitter's per-circuit priority override     |
| panel        | `core/dominant-power-source`   | Updates emitter's panel-level dom. source override  |

Producer-supplied handlers always win — the emitter's defaults only fill gaps.

### Relay state precedence

```text
always-on > /set override > load-shed > default-CLOSED
```

- `always-on` circuits (`relay-behavior=always-on` in manifest) ignore both
  `/set` and load-shed; their relay is permanently CLOSED. `relay_requester`
  reports `NEVER`.
- `/set` overrides take effect immediately on the next tick. No debounce.
  `relay_requester` reports `USER`. Operator can override safety-shed.
- Load-shed only applies when there's no `/set` override. `relay_requester`
  reports `BACKUP`.
- Default-CLOSED is the resting state when no decision-maker has spoken.
  `relay_requester` reports `UNKNOWN`.

### Latency

Relay state changes are reflected on the wire on the next `publish_tick`
call, bounded by the producer's tick cadence (typically 1.0 s).

## Energy integration

`EnergyIntegrator` accumulates per-circuit (and per-EVSE) `consumed_wh` /
`produced_wh` across ticks using `dt = current_time - last_tick_time` per
instance. The producer can seed values at startup:

```python
emitter.seed_energy("kitchen", consumed_wh=12345.0, produced_wh=0.0)
```

…or declare them in the manifest via `initial-consumed-wh` /
`initial-produced-wh` keys. Either path lets the producer add a new circuit
to a running deployment without zeroing existing accumulators.

## Snapshot read-back

`emitter.last_snapshot` returns the most recently published `EbusPanelSnapshot`.
Consumers (dashboards, HA-API endpoints) read aggregated state through this
property — they do not construct snapshots.
