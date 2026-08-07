"""Panel shed-forecast (Battery Time Remaining) values publish when a BESS is
present and are omitted otherwise (DESIM-a5p.17).

The five BTR forecast fields are simulator-derived dynamics, published only when
a BESS is commissioned (matching real SPAN, lc3 nt-2026-c192x)."""

from __future__ import annotations

from ebus_panel_sim import (
    BESSConfig,
    DeviceInstance,
    DeviceManifest,
    Emitter,
    SetterRegistry,
    TickInputs,
)

from .conftest import PahoRecorder

_FORECAST = "ebus/5/abc-123/shed-forecast/"


def _panel() -> DeviceInstance:
    return DeviceInstance(
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
    )


def _circuit() -> DeviceInstance:
    return DeviceInstance(
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
    )


def _bess() -> DeviceInstance:
    return DeviceInstance(
        "bess",
        "abc-123-bess",
        "Battery",
        metadata={"vendor-name": "Span", "nameplate-capacity-kwh": "13.5"},
    )


def _tick() -> TickInputs:
    return TickInputs(current_time=0.0, grid_online=True, circuits={"kitchen": 1000.0})


def test_shed_forecast_published_when_a_bess_is_present(rec: PahoRecorder) -> None:
    manifest = DeviceManifest(instances=(_panel(), _circuit(), _bess()))
    cfg = BESSConfig(
        instance_id="abc-123-bess",
        nameplate_capacity_kwh=13.5,
        max_charge_w=3500.0,
        max_discharge_w=3500.0,
    )
    em = Emitter(manifest, SetterRegistry(), bess_configs=(cfg,))
    em.start()
    em.publish_tick(_tick())
    retained = rec.retained
    assert retained[_FORECAST + "total-time-remaining"] == "4320"
    assert retained[_FORECAST + "time-to-priority-shed"] == "3037"
    assert retained[_FORECAST + "full-charge-total-time-remaining"] == "4320"
    assert retained[_FORECAST + "full-charge-time-to-priority-shed"] == "3038"
    assert retained[_FORECAST + "confidence"] == "HIGH"


def test_shed_forecast_absent_without_a_bess(rec: PahoRecorder) -> None:
    manifest = DeviceManifest(instances=(_panel(), _circuit()))
    em = Emitter(manifest, SetterRegistry())
    em.start()
    em.publish_tick(_tick())
    assert not any(t.startswith(_FORECAST) for t in rec.retained)
