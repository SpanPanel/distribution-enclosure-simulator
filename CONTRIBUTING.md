# Contributing to distribution-enclosure-simulator

Thanks for your interest in contributing! This project (`ebus-panel-sim`) is a producer-side [Homie 5](https://homieiot.github.io) publisher and a fully-loaded distribution-enclosure simulator for the [Electrification Bus (eBus)](https://ebus.energy) convention. It publishes a complete eBus Homie device tree (the enclosure plus a device for every circuit, lugs pair, and integrated DER: BESS, PV, EVSE, and MID) so consumers can build and test against a realistic SPAN-like panel without beta firmware or a live installation. It began as a fork of Bill Flood's original simulator and now tracks the latest eBus specification.

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

## What "done" means

This package is published to PyPI, and a PyPI upload can never be replaced. So an increment that lands behaviour and leaves its documentation for later is not a smaller version of the change: it is a release whose docs contradict its code, and the correction costs another release. Ship the whole thing.

A change is done when, in the same PR:

- **Prose it invalidates is fixed.** If a change makes a sentence in the README, `DESIGN.md`, `DEVELOPER.md`, or a docstring untrue, that sentence is part of the change. A new option whose README still describes the old single path is not finished.
- **Types its signatures name are reachable.** A public parameter annotated with a type a caller cannot import from `ebus_panel_sim` forces them to depend on `ebus_sdk` directly, which is what the SDK seam exists to spare them.
- **It carries its `CHANGELOG.md` entry**, under `[Unreleased]` or a version heading.
- **New behaviour has a test that fails without it.** Say so in the PR, and say which. A test that passes against the previous commit is not evidence.
- **Caller obligations are written down where the caller will look.** If correct use requires the caller to do something (wire a callback, set something before connecting, let an event loop turn), a `#` comment in our source does not reach them.

Splitting a change is fine when the parts are genuinely independent, or when a decision is needed that only a maintainer can make. It is not fine as a way to defer the half that needs no decision. If you are unsure which you have, open the PR with the whole thing and let the review split it.

## Local development

Python >= 3.11 (developed and CI-tested on 3.11 and 3.14), managed with [uv](https://docs.astral.sh/uv/). See [DEVELOPER.md](DEVELOPER.md) for the full guide.

```bash
uv sync --group dev                       # create .venv, install runtime + dev deps
uv run pre-commit install                 # install the pre-commit hooks
uv run pytest                             # tests
uv run ruff check --fix src/ tests/       # lint
uv run ruff format src/ tests/            # format
uv run mypy --strict src/ebus_panel_sim/       # type check (strict)
```

Every commit is validated by pre-commit and by the [`ci.yaml`](.github/workflows/ci.yaml) workflow (ruff, ruff-format, mypy `--strict`, pytest). Run the gates locally before pushing; new behaviour needs a test, and bug fixes need a regression test.

## Releases

`ebus-panel-sim` is published to [PyPI](https://pypi.org/project/ebus-panel-sim/). Releases are tag-triggered: pushing a `v*` tag runs `.github/workflows/publish.yml`, which re-runs the gates against the tag, builds, uploads via PyPI trusted publishing (OIDC, no stored token), and mirrors the release to GitHub Releases using the tag's `CHANGELOG.md` section.

A release-worthy change bumps `__version__` in `src/ebus_panel_sim/__init__.py`, the single source of truth, and adds a `CHANGELOG.md` entry under a matching `## [x.y.z]` heading. Do not restate the version in `pyproject.toml`; `[tool.hatch.version]` reads it. The publish workflow refuses to upload when the tag and `__version__` disagree, because a PyPI upload can never be replaced.

## Code of conduct

Be respectful and constructive. We appreciate everyone who takes the time to file an issue, start a discussion, or send a pull request.

## Maintenance posture

This is an active alpha project. Updates and maintenance, including responses to issues filed on GitHub, happen on an "as time and resources permit" basis. It is maintained alongside the [Electrification Bus specification](https://github.com/electrification-bus/specification) and the eBus SDK.
