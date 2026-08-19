"""Cross-device connection index is populated on the panel-side owner (DESIM-a5p.16).

Real SPAN publishes connection/* on the circuit or lugs that feeds a DER, never
on the DER child: a DER's feed circuit carries the feeds-* triple, and an
upstream BESS's fed-by triple lands on the upstream lugs."""

from __future__ import annotations

import json

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


def test_every_declared_connection_property_can_be_published(rec: PahoRecorder) -> None:
    """A device that has a connection edge publishes every ``connection``
    property its own ``$description`` declares.

    ``connection/count`` failed this. It was declared by every circuit and both
    lugs devices, and the snapshot fields behind it (``feeds_count``,
    ``connection_count``) were never assigned by any code path -- so it was
    unpublishable by construction, and a consumer reading the description waited
    for a value that could not arrive. The catalog scopes ``count`` to a node that
    "aggregates multiple physical units behind a *single* connection point"; this
    emitter models each DER as its own device and aggregates nothing, so the
    property is not merely unpopulated, it has nothing to describe.

    Asserted against circuits that DO have an edge, because absence is meaningful
    elsewhere -- a circuit feeding nothing correctly publishes none of these (see
    ``test_connection_is_absent_where_there_is_no_edge``).

    Lugs are deliberately not asserted this way. They declare ``feeds-device-*``
    as well as ``fed-by-device-*``, and nothing assigns the former: the lugs
    snapshot sets only the fed-by triple. That is the same defect as ``count``,
    but it is not the same decision -- a downstream lugs feeding a subpanel is a
    real topology, so the fix could as easily be to populate it as to stop
    declaring it. Raised upstream rather than settled here, and left out of this
    assertion instead of being written in as expected.
    """
    retained = _started(rec)

    for device_id in ("solar", "ev"):
        description = json.loads(retained[f"ebus/5/{device_id}/$description"])
        declared = set(description["nodes"]["connection"]["properties"])
        published = {
            topic.rsplit("/", 1)[1]
            for topic in retained
            if topic.startswith(f"ebus/5/{device_id}/connection/")
        }
        assert declared == published, (
            f"{device_id}: declared-but-unpublished {declared - published}"
        )

    # No device declares it anywhere, which is the part `count` failed: every
    # circuit and both lugs carried it, and no configuration could fill it.
    for topic, payload in retained.items():
        if topic.endswith("/$description"):
            nodes = json.loads(payload).get("nodes", {})
            connection = nodes.get("connection")
            if connection is not None:
                assert "count" not in connection["properties"], topic
