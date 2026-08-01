"""Homie units survive to the wire $description (regression for the live-panel
conformance gate, DESIM-a5p.9).

``ebus_sdk.Unit`` is a str-enum whose value is the wire string, so the profile's
unit strings must resolve by value. A prior hand-maintained name table mapped
"V" to a non-existent "VOLT" member and had no entry for "min", silently
dropping those units from the published $description (found by the lc3
conformance gate)."""

from __future__ import annotations

import json

from panel_sim import (
    BESSConfig,
    DeviceInstance,
    DeviceManifest,
    Emitter,
    SetterRegistry,
)
from panel_sim.wire.graph_builder import _to_sdk_unit

from .conftest import PahoRecorder


def test_to_sdk_unit_resolves_by_value() -> None:
    # "V" and "min" are the two the conformance gate caught; the rest already worked
    for wire in ("V", "min", "W", "A", "Wh", "%"):
        resolved = _to_sdk_unit(wire)
        assert resolved is not None
        assert resolved.value == wire
    assert _to_sdk_unit(None) is None
    assert _to_sdk_unit("not-a-real-unit") is None


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
        )
    )


def test_panel_description_carries_units_on_the_wire(rec: PahoRecorder) -> None:
    cfg = BESSConfig(
        instance_id="abc-123-bess",
        nameplate_capacity_kwh=13.5,
        max_charge_w=3500.0,
        max_discharge_w=3500.0,
    )
    Emitter(_manifest(), SetterRegistry(), bess_configs=(cfg,)).start()
    panel = json.loads(rec.retained["ebus/5/abc-123/$description"])
    nodes = panel["nodes"]
    assert nodes["meter"]["properties"]["voltage-a"]["unit"] == "V"
    assert nodes["meter"]["properties"]["voltage-b"]["unit"] == "V"
    assert nodes["shed-forecast"]["properties"]["total-time-remaining"]["unit"] == "min"
    assert (
        nodes["shed-forecast"]["properties"]["full-charge-time-to-priority-shed"]["unit"] == "min"
    )
