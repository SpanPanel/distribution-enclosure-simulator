"""The MID is published as a child of its BESS, not the panel (DESIM-a5p.18).

Real SPAN (lc3 reference nt-2026-c192x) publishes the microgrid interconnect
device as a child of the proxied BESS (a grandchild of the panel): the MID's
$description carries parent = the BESS device id and root = the panel device id,
and the MID appears in the BESS's children[], not the panel's."""

from __future__ import annotations

import json

from panel_sim import (
    BESSConfig,
    DeviceInstance,
    DeviceManifest,
    Emitter,
    SetterRegistry,
)
from panel_sim.wire.mapping_loader import load_mapping_table

from .conftest import PahoRecorder


def test_mid_mapping_parents_the_mid_under_the_bess() -> None:
    """Guard the shipped mapping data that regressed: the MID's parent is the BESS."""
    mapping = load_mapping_table()
    placement = mapping["mid"].placement
    assert placement.kind == "child-of-parent"
    assert placement.parent_entity_class == "bess"


def _manifest() -> DeviceManifest:
    return DeviceManifest(
        instances=(
            DeviceInstance(
                "panel",
                "abc-123",
                "Span Panel",
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
                "bess",
                "abc-123-bess",
                "Battery",
                metadata={"vendor-name": "Span", "nameplate-capacity-kwh": "13.5"},
            ),
            DeviceInstance(
                "mid",
                "abc-123-bess-mid",
                "Microgrid Interconnect Device",
                metadata={
                    "vendor-name": "Span",
                    "serial-number": "abc-123-bess-mid",
                    "model": "MID-1",
                    "firmware-version": "sim/v0.1.0",
                },
            ),
        )
    )


def test_mid_is_a_child_of_the_bess_on_the_wire(rec: PahoRecorder) -> None:
    bess_cfg = BESSConfig(
        instance_id="abc-123-bess",
        nameplate_capacity_kwh=13.5,
        max_charge_w=3500.0,
        max_discharge_w=3500.0,
    )
    Emitter(_manifest(), SetterRegistry(), bess_configs=(bess_cfg,)).start()
    retained = rec.retained

    panel_desc = json.loads(retained["ebus/5/abc-123/$description"])
    assert "abc-123-bess" in panel_desc["children"]
    assert "abc-123-bess-mid" not in panel_desc["children"]

    bess_desc = json.loads(retained["ebus/5/abc-123-bess/$description"])
    assert "abc-123-bess-mid" in bess_desc["children"]

    mid_desc = json.loads(retained["ebus/5/abc-123-bess-mid/$description"])
    assert mid_desc["parent"] == "abc-123-bess"
    assert mid_desc["root"] == "abc-123"
