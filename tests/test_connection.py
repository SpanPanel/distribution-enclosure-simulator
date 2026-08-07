"""Cross-device connection index is populated on the panel-side owner (DESIM-a5p.16).

Real SPAN publishes connection/* on the circuit or lugs that feeds a DER, never
on the DER child: a DER's feed circuit carries the feeds-* triple, and an
upstream BESS's fed-by triple lands on the upstream lugs."""

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


def _circuit(cid: str) -> DeviceInstance:
    return DeviceInstance(
        "circuit",
        cid,
        cid.title(),
        metadata={
            "tab-numbers": "1",
            "breaker-rating-a": "20",
            "default-priority": "NICE_TO_HAVE",
            "relay-behavior": "controllable",
            "placement": "downstream-of-lugs",
        },
    )


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
            _circuit("kitchen"),  # a plain load: no DER, no connection edge
            _circuit("solar"),  # feeds the PV
            _circuit("ev"),  # feeds the EVSE
            DeviceInstance("lugs", "lugs-upstream", "Upstream lugs", {"direction": "upstream"}),
            DeviceInstance(
                "lugs", "lugs-downstream", "Downstream lugs", {"direction": "downstream"}
            ),
            DeviceInstance(
                "pv",
                "pv",
                "Solar",
                metadata={
                    "vendor-name": "Enphase",
                    "model": "IQ8PLUS-72-2-US",
                    "nominal-power-w": "5000",
                    "inverter-type": "ac-coupled",
                    "relative-position": "IN_PANEL",
                    "feed": "solar",
                },
            ),
            DeviceInstance(
                "evse",
                "evse",
                "EV Charger",
                metadata={
                    "vendor-name": "SPAN",
                    "model": "SPAN Drive",
                    "part-number": "SPN-DRV-001",
                    "serial-number": "SIM-EVSE-1",
                    "firmware-version": "sim/v0.1.0",
                    "max-current-a": "32.0",
                    "feed": "ev",
                },
            ),
            DeviceInstance(
                "bess",
                "abc-123-bess",
                "Battery",
                metadata={
                    "vendor-name": "Span",
                    "nameplate-capacity-kwh": "13.5",
                    "relative-position": "UPSTREAM",
                },
            ),
        )
    )


def _started(rec: PahoRecorder) -> dict[str, str]:
    cfg = BESSConfig(
        instance_id="abc-123-bess",
        nameplate_capacity_kwh=13.5,
        max_charge_w=3500.0,
        max_discharge_w=3500.0,
    )
    em = Emitter(_manifest(), SetterRegistry(), bess_configs=(cfg,))
    em.start()
    em.publish_tick(
        TickInputs(
            current_time=0.0,
            grid_online=True,
            circuits={"kitchen": 500.0, "solar": -2000.0, "ev": 1500.0},
        )
    )
    return rec.retained


def test_circuit_feeding_a_der_publishes_the_feeds_triple(rec: PahoRecorder) -> None:
    retained = _started(rec)
    assert retained["ebus/5/solar/connection/feeds-device-id"] == "pv"
    assert retained["ebus/5/solar/connection/feeds-device-type"] == "energy.ebus.device.pv"
    assert retained["ebus/5/solar/connection/feeds-device-status"] == "OK"
    assert retained["ebus/5/ev/connection/feeds-device-id"] == "evse"
    assert retained["ebus/5/ev/connection/feeds-device-type"] == "energy.ebus.device.evse"


def test_upstream_lugs_publishes_the_fed_by_triple_for_an_upstream_bess(
    rec: PahoRecorder,
) -> None:
    retained = _started(rec)
    assert retained["ebus/5/lugs-upstream/connection/fed-by-device-id"] == "abc-123-bess"
    assert (
        retained["ebus/5/lugs-upstream/connection/fed-by-device-type"] == "energy.ebus.device.bess"
    )
    assert retained["ebus/5/lugs-upstream/connection/fed-by-device-status"] == "OK"


def test_connection_is_absent_where_there_is_no_edge(rec: PahoRecorder) -> None:
    retained = _started(rec)
    # a plain load circuit carries no connection edge
    assert not any(t.startswith("ebus/5/kitchen/connection/") for t in retained)
    # the downstream lugs is not fed by the upstream BESS
    assert "ebus/5/lugs-downstream/connection/fed-by-device-id" not in retained
    # connection lives on the panel-side owner, never on the DER child device
    assert not any(t.startswith("ebus/5/pv/connection/") for t in retained)
    assert not any(t.startswith("ebus/5/evse/connection/") for t in retained)
