# Changelog

## [0.2.0] - 2026-08-01

### Fixed

- **BREAKING (wire):** circuit `meter/imported-energy` and `meter/exported-energy` are now published in the enclosure reference frame, matching the already-enclosure-framed `meter/active-power` and real panel firmware. Previously a load circuit published a rising `imported-energy` while its `active-power` was negative, so integrating the published power grew the opposite accumulator (every load looked like it produced energy). Consumers that compensated for the old inverted behaviour must drop the workaround; consumers written against real panel firmware need no change. Lugs metering is unchanged (the frames coincide there). (#2, fixes #1)

## [0.1.0] — 2026-05-02

### Added

- Initial scaffolding of the `panel-sim` package: wire layer (manifest/mapping/profiles,
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
