"""The span (SPAN-faithful) vs reference (vendor-neutral, spec-conformant) variant split."""

from __future__ import annotations

from panel_sim import DeviceInstance, DeviceManifest, Emitter, SetterRegistry, TickInputs
from panel_sim.wire.profile_loader import load_profiles

from .conftest import PahoRecorder


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
                "circuit",
                "kitchen",
                "Kitchen",
                metadata={
                    "tab-numbers": "1",
                    "breaker-rating-a": "20",
                    "default-priority": "NICE_TO_HAVE",
                    "relay-behavior": "controllable",
                    "placement": "downstream-of-lugs",
                },
            ),
        )
    )


def test_reference_variant_strips_the_span_overlay() -> None:
    span = load_profiles(variant="span")
    ref = load_profiles(variant="reference")
    # panel status diagnostics are SPAN-vendor-specific
    assert "status" in span["panel"].capabilities
    assert "status" not in ref["panel"].capabilities
    # circuit identity extras are SPAN-specific (they are the whole of circuit
    # info, so the reference circuit has no info capability at all)
    assert "name" in span["circuit"].capabilities["info"].properties
    ref_info = ref["circuit"].capabilities.get("info")
    assert ref_info is None or "name" not in ref_info.properties
    # evse config grab-bag is SPAN-only (spec uses charge-limit)
    assert "config" in span["evse"].capabilities
    assert "config" not in ref["evse"].capabilities
    # shed/policy: read-only on a SPAN panel, settable per the spec
    assert span["panel"].capabilities["shed"].properties["policy"].settable is False
    assert ref["panel"].capabilities["shed"].properties["policy"].settable is True


def _tick() -> TickInputs:
    return TickInputs(current_time=0.0, grid_online=True, circuits={"kitchen": 500.0})


def test_span_emitter_publishes_span_diagnostics(rec: PahoRecorder) -> None:
    em = Emitter(_manifest(), SetterRegistry())  # default variant = span
    em.start()
    em.publish_tick(_tick())
    retained = rec.retained
    assert retained["ebus/5/abc-123/status/postal-code"] == "94103"
    assert retained["ebus/5/kitchen/meter/active-power"] == "-500.0"


def test_reference_emitter_omits_the_span_surface(rec: PahoRecorder) -> None:
    em = Emitter(_manifest(), SetterRegistry(), variant="reference")
    em.start()
    em.publish_tick(_tick())
    retained = rec.retained
    # no SPAN status diagnostics on the reference tree
    assert not any(t.startswith("ebus/5/abc-123/status/") for t in retained)
    assert not any(t.endswith("/info/name") for t in retained)
    # the spec-conformant metering still flows
    assert retained["ebus/5/kitchen/meter/active-power"] == "-500.0"
