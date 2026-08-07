# Changelog

## [Unreleased]

### Changed

- `ebus-sdk` pin moved from `>=0.18,<0.19` to `>=0.19,<0.20`. The motivating fix is in **0.18.1**, which the old range already permitted but `uv.lock` had never picked up: `Device.refresh_tree()` published a device's own `$state` before recursing to its children, so a device could announce `ready` while the children it vouches for had published nothing ([python-sdk#31](https://github.com/electrification-bus/python-sdk/issues/31)). That matters here specifically because this package publishes a parent/child tree, which is the shape that exhibits it. **0.19.0** additionally makes the `refresh_tree()` cascade best-effort per child, so one raising descendant can no longer abort the rest of a reconnect republish; with an enclosure plus a device per circuit, lugs pair and DER, this tree has many descendants to abort. Its other changes do not reach us: `Controller.is_tree_complete()`/`on_tree_ready` is consumer-side, and the `Node.delete_property()` `$description` fix applies to an API this package never calls. No source changes. The emitted wire surface is unchanged between `0.18.0` and `0.19.0`: identical publish order, identical subscriptions, and identical retained payloads once the `$description` `version` wall-clock stamp is normalised (it differs run to run regardless of SDK version). Suite is `158 passed` under both.
- `ebus-sdk` pin moved from `>=0.12,<0.13` to `>=0.18,<0.19`. The old range excluded the release carrying the [python-sdk#27](https://github.com/electrification-bus/python-sdk/issues/27) fixes — the `battery` capability key removed in favour of `soc`, and `energy` → `energy_storage` / `total_increasing` → `measurement` for `soe`, `total-energy-storage` and `loadup-headroom` — so a downstream needing those could not stay inside the pin. No source changes: the published tree is byte-identical on `0.12.0` and `0.18.0` (197 retained topics, identical topic sets, zero payload differences once the `$description` `version` timestamp is normalised), and the suite is `158 passed` under both. `uv.lock` also moves `ebus-mqtt-client` 0.1.8 → 0.4.0, which `ebus-sdk` 0.18.0 requires. (#4, closes #3)

## [0.2.0] - 2026-08-01

### Fixed

- **BREAKING (wire):** circuit `meter/imported-energy` and `meter/exported-energy` are now published in the enclosure reference frame, matching the already-enclosure-framed `meter/active-power` and real panel firmware. Previously a load circuit published a rising `imported-energy` while its `active-power` was negative, so integrating the published power grew the opposite accumulator (every load looked like it produced energy). Consumers that compensated for the old inverted behaviour must drop the workaround; consumers written against real panel firmware need no change. Lugs metering is unchanged (the frames coincide there). (#2, fixes #1)

## [0.1.0] — 2026-05-02

### Added

- Initial scaffolding of the `ebus-panel-sim` package: wire layer (manifest/mapping/profiles,
  graph builder, lifecycle, set router, SDK seam, property bag diff) and schedule runner
  (clock, energy package, simulated circuits, solar curve evaluation, override store,
  tick orchestration).
- Public `Emitter` API: `start()`, `tick()`, `stop()`, `set_property_override()`,
  `clear_property_override()`, `force_grid_state()`, `last_snapshot`, `topology_version`,
  static `lwt_settings()`.
- Vendored Homie 5 device profiles for panel, circuit, lugs, BESS, PV, EVSE (v1_flat).
- Four canonical example manifest + runtime-spec pairs.
- End-to-end mosquitto integration test.
- 132 passing tests across `wire/`, `scheduleRunner/`, and integration suites.

### Deferred

- Full lift of the simulator's `RealisticBehaviorEngine` with cycling state, smart-load
  noise, and HVAC seasonal modulation. v0.1.0 ships a stub that applies the runtime-
  spec's pre-baked hour/monthly factors directly with deterministic noise.
- v2_children topology (parent-child Homie schema). Pending the upstream `ebus-sdk` adding
  parent/child support.
