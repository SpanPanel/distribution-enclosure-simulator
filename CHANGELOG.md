# Changelog

## [Unreleased]

## [0.3.0] - 2026-08-07

First release published to PyPI, as **`ebus-panel-sim`**.

### Added

- **Published to PyPI.** Releases are tag-triggered and use PyPI trusted publishing (OIDC), so no API token is stored anywhere. The workflow re-runs the full gate set against the tag rather than trusting a green branch run, since a tag can point at any commit, and it refuses to publish when the tag disagrees with `__version__` or when the built wheel is missing its wire data. Consumers pinning by git URL can now `pip install ebus-panel-sim` instead. (#10)
- **`py.typed`.** The package is `mypy --strict` throughout but shipped no PEP 561 marker, so none of its annotations reached consumers: an installed `panel_sim` resolved to `Any`. This is the same class of gap that let the `Device.mqttc` teardown bug below sit unnoticed here until `ebus-sdk` shipped its own marker. Verified from outside: a consumer installing the wheel now types `Emitter.publish_tick` as `(TickInputs) -> EbusPanelSnapshot`. (#10)

### Changed

- **BREAKING (package): renamed to `ebus-panel-sim`, importing as `ebus_panel_sim`.** Was `panel-sim`/`panel_sim`. Update imports and any git-URL or path pin. Across the eBus family the repository name and the distribution name differ freely, but the distribution name always equals the import package under an `ebus` prefix (`ebus-sdk`/`ebus_sdk`, `ebus-tools`/`ebus_tools`, `ebus-service-discovery`/`ebus_service_discovery`), and this package was the outlier. The unprefixed name was also actively misleading: PyPI's `panel` is HoloViz's dashboard framework, with an established `panel-*` plugin ecosystem, so `panel-sim` read as a plugin for it. Done now because it is free before the first release and a breaking change for every consumer after it. (#8)
- `ebus-sdk` pin moved from `>=0.18,<0.19` to `>=0.19,<0.20`. The motivating fix is in **0.18.1**, which the old range already permitted but `uv.lock` had never picked up: `Device.refresh_tree()` published a device's own `$state` before recursing to its children, so a device could announce `ready` while the children it vouches for had published nothing ([python-sdk#31](https://github.com/electrification-bus/python-sdk/issues/31)). That matters here specifically because this package publishes a parent/child tree, which is the shape that exhibits it. **0.19.0** additionally makes the `refresh_tree()` cascade best-effort per child, so one raising descendant can no longer abort the rest of a reconnect republish; with an enclosure plus a device per circuit, lugs pair and DER, this tree has many descendants to abort. Its other changes do not reach us: `Controller.is_tree_complete()`/`on_tree_ready` is consumer-side, and the `Node.delete_property()` `$description` fix applies to an API this package never calls. No source changes. The emitted wire surface is unchanged between `0.18.0` and `0.19.0`: identical publish order, identical subscriptions, and identical retained payloads once the `$description` `version` wall-clock stamp is normalised (it differs run to run regardless of SDK version). Suite is `158 passed` under both.
- `ebus-sdk` pin moved from `>=0.12,<0.13` to `>=0.18,<0.19`. The old range excluded the release carrying the [python-sdk#27](https://github.com/electrification-bus/python-sdk/issues/27) fixes — the `battery` capability key removed in favour of `soc`, and `energy` → `energy_storage` / `total_increasing` → `measurement` for `soe`, `total-energy-storage` and `loadup-headroom` — so a downstream needing those could not stay inside the pin. No source changes: the published tree is byte-identical on `0.12.0` and `0.18.0` (197 retained topics, identical topic sets, zero payload differences once the `$description` `version` timestamp is normalised), and the suite is `158 passed` under both. `uv.lock` also moves `ebus-mqtt-client` 0.1.8 → 0.4.0, which `ebus-sdk` 0.18.0 requires. (#4, closes #3)
- The package version is now single-sourced from `ebus_panel_sim.__version__` and read by `[tool.hatch.version]`, rather than being restated in `pyproject.toml`. Note this is the *package* version, which is distinct from the producer-contract version the module docstrings refer to. (#10)
- `pre-commit` runs mypy from the project venv instead of a pre-commit-managed one. The isolated environment could never see `ebus-sdk` at all, so the hook silently checked less than CI did; restating the pin in `additional_dependencies` would have put a second copy of it somewhere nothing keeps in sync. (#7)

### Fixed

- **The package could not be built at all.** `packages` already carries everything under the package directory, so the `force-include` table naming the profiles/mapping/catalogs trees re-added each file at a path the wheel already held, which hatchling treats as fatal. Every `uv build` failed, on every commit this project has ever had. Nothing caught it because the test suite exercises the source tree rather than the built artifact, so `publish.yml` now asserts the wheel's contents directly. The sdist additionally excludes the agent and issue-tracker symlinks, which are untracked and absent from a clean checkout but break a local build on their absolute link targets. (#8)
- `Emitter.stop(graceful=False)` did not type-check, leaving `main` red from the 0.18 pin bump onward. `ebus-sdk` 0.18 ships a `py.typed` marker, so mypy stopped resolving the SDK to `Any` and started reading its real types, and `Device.mqttc` is typed `MqttDeviceTransport`, which deliberately omits `start`/`stop`: that omission *is* the SDK's no-start/no-stop guarantee, expressed as a type. `stop` resolves only on the concrete client the SDK builds and owns. Now narrowed at runtime in the SDK seam. Thanks to [@cayossarian](https://github.com/cayossarian), who found this independently and contributed the fix. (#7)

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
