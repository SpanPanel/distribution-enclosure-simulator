"""Guard the vendored spec capability catalogs against silent drift.

``src/ebus_panel_sim/wire/catalogs/*.json`` are byte copies of the eBus specification's
``capabilities/*.json``, vendored so the wire datatypes are single-sourced from the
spec (see ``wire/profile_loader.py``). Two things must stay honest:

1. ``.ebus-spec.json`` pins a version for each capability ebus-panel-sim implements; that
   pin must match the ``version`` in the vendored catalog it was copied from. This is
   self-contained and always runs.
2. The vendored copies must still match the spec source. This can only run when the
   ``../specification`` sibling checkout is present, so it skips otherwise.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_DIR = _ROOT / "src" / "ebus_panel_sim" / "wire" / "catalogs"
_LOCKFILE = _ROOT / ".ebus-spec.json"
_SPEC_CAPABILITIES = _ROOT.parent / "specification" / "capabilities"


def _short_name(capability_urn: str) -> str:
    """energy.ebus.capability.shed-forecast -> shed-forecast."""
    return capability_urn.rsplit(".", 1)[-1]


def _vendored_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for path in sorted(_CATALOG_DIR.glob("*.json")):
        raw = json.loads(path.read_text())
        versions[_short_name(raw["capability"])] = raw["version"]
    return versions


def test_lockfile_pins_match_vendored_catalog_versions() -> None:
    """Every capability the lockfile pins that is also vendored must agree on version.

    (A vendored-but-unpinned catalog like charge-limit is fine: it is staged for a
    migration the profiles don't reference yet.)"""
    pinned: dict[str, str] = json.loads(_LOCKFILE.read_text())["implements"]["capabilities"]
    vendored = _vendored_versions()
    for name, pin in pinned.items():
        assert name in vendored, f".ebus-spec.json pins {name!r} but no catalog is vendored"
        assert vendored[name] == pin, (
            f"{name}: lockfile pins {pin} but vendored catalog is {vendored[name]}"
        )


@pytest.mark.skipif(
    not _SPEC_CAPABILITIES.is_dir(),
    reason="../specification checkout not present; cannot compare vendored catalogs to source",
)
def test_vendored_catalogs_match_spec_source() -> None:
    """Each vendored catalog is byte-identical to the spec source it was copied from."""
    drift: list[str] = []
    for path in sorted(_CATALOG_DIR.glob("*.json")):
        source = _SPEC_CAPABILITIES / path.name
        if not source.is_file():
            drift.append(f"{path.name}: no longer exists in the spec")
        elif path.read_text() != source.read_text():
            drift.append(f"{path.name}: differs from ../specification/capabilities/{path.name}")
    assert not drift, "vendored catalogs have drifted from the spec:\n  " + "\n  ".join(drift)
