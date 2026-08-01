# Contributing to distribution-enclosure-simulator

Thanks for your interest in contributing! This project (`panel-sim`) is a producer-side [Homie 5](https://homieiot.github.io) publisher and a fully-loaded distribution-enclosure simulator for the [Electrification Bus (eBus)](https://ebus.energy) convention. It publishes a complete eBus Homie device tree (the enclosure plus a device for every circuit, lugs pair, and integrated DER: BESS, PV, EVSE, and MID) so consumers can build and test against a realistic SPAN-like panel without beta firmware or a live installation. It began as a fork of Bill Flood's original simulator and now tracks the latest eBus specification.

## How to contribute

### Discussions

Use [Discussions](https://github.com/electrification-bus/distribution-enclosure-simulator/discussions) for:

- Open-ended questions about the simulator's design, the producer/emitter split, or the wire model ("how should the producer drive circuit X?")
- Integration questions ("I'm building a consumer / dashboard / Home Assistant integration against the published tree, what's the recommended pattern?")
- Proposed new device types, native behaviours, or profile/mapping changes worth aligning on before writing the code
- Questions about the relationship between this simulator and the [Electrification Bus specification](https://github.com/electrification-bus/specification) (this repo aims to be a faithful producer of the spec; spec-level questions belong in the spec repo's Discussions)
- Thinking out loud about a proposed change before scoping it

Discussions are open-ended: a good place to align on direction before something becomes a concrete change. Aligned outcomes often turn into one or more Issues or pull requests.

### Issues

Use [Issues](https://github.com/electrification-bus/distribution-enclosure-simulator/issues) for actionable changes:

- Bug reports with reproduction steps (the YAML device definition, broker, and a code snippet or the published topics you saw versus expected)
- Spec-conformance gaps where the published tree diverges from the [Electrification Bus specification](https://github.com/electrification-bus/specification) (note which spec document, capability catalog, and section)
- Concrete feature requests with a clear scope and a use case
- Documentation gaps where a specific README, example, or docstring change is intended
- Discussion outcomes that have alignment and a clear scope

If you're not sure whether something is an Issue or a Discussion, start with a Discussion: we can convert it later.

### Pull requests

Pull requests are welcome.

- For small fixes (typos, docstring tweaks, version bumps, low-risk bug fixes with a test), open a PR directly.
- For substantive changes (new public API surface, changes to `TickInputs` or the manifest contract, new device types, changes that alter discovery/topic structure or property semantics), open a Discussion or Issue first so we can align on scope before you invest the effort.
- **Spec conformance is the north star.** This simulator exists to publish a spec-conformant eBus Homie tree. When a PR's behaviour is normative (device states, property contracts, topic structure, capability surface), point to the spec section it implements. The wire type contract is single-sourced from the vendored spec capability catalogs and guarded by `tests/test_catalog_drift.py`; if you touch a capability, keep the catalog and the lockfile (`.ebus-spec.json`) in sync. If the spec is ambiguous or wrong, file an Issue against the spec repo first and reference it from the PR here.
- **Respect the producer/emitter boundary.** The producer computes generation-side physics and hands the emitter a per-tick driving signal via `TickInputs`; the emitter derives wire-facing telemetry and publishes it. Keep generation models out of the emitter (see `DESIGN.md` and `DEVELOPER.md`).
- **Keep comments to a minimum.** The project style is self-explanatory code, with comments reserved for the non-obvious *why* (a spec quirk, a Homie nuance, a SPAN-variant deviation). Don't add comments that just restate the code.
- One commit per logical change is fine; we don't require squash or any particular branch naming.

## Local development

Python >= 3.11 (developed and CI-tested on 3.11 and 3.14), managed with [uv](https://docs.astral.sh/uv/). See [DEVELOPER.md](DEVELOPER.md) for the full guide.

```bash
uv sync --group dev                       # create .venv, install runtime + dev deps
uv run pre-commit install                 # install the pre-commit hooks
uv run pytest                             # tests
uv run ruff check --fix src/ tests/       # lint
uv run ruff format src/ tests/            # format
uv run mypy --strict src/panel_sim/       # type check (strict)
```

Every commit is validated by pre-commit and by the [`ci.yaml`](.github/workflows/ci.yaml) workflow (ruff, ruff-format, mypy `--strict`, pytest). Run the gates locally before pushing; new behaviour needs a test, and bug fixes need a regression test.

## Releases

`panel-sim` is not published to PyPI. Consumers pin it via a git URL or a local path (see the README). A release-worthy change bumps `version` in `pyproject.toml` and adds a `CHANGELOG.md` entry.

## Code of conduct

Be respectful and constructive. We appreciate everyone who takes the time to file an issue, start a discussion, or send a pull request.

## Maintenance posture

This is an active alpha project. Updates and maintenance, including responses to issues filed on GitHub, happen on an "as time and resources permit" basis. It is maintained alongside the [Electrification Bus specification](https://github.com/electrification-bus/specification) and the eBus SDK.
