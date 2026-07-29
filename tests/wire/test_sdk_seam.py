"""Smoke test for the SDK seam — exercises real ebus_sdk Property construction.

Broker-free via the autouse ``mock_paho`` fixture; a root ``Device`` needs a
``mqtt_cfg`` (empty dict = localhost defaults, harmless under the mock)."""

from __future__ import annotations

import ebus_sdk

from panel_sim.wire._sdk_seam import make_property


def _prop() -> ebus_sdk.Property:
    device = ebus_sdk.Device("d1", name="Test", type="test", mqtt_cfg={})
    node = device.add_node_from_dict({"id": "meter", "name": "Meter", "type": "meter"})
    return make_property(
        node=node,
        key="active-power",
        name="Active Power",
        datatype=ebus_sdk.PropertyDatatype.FLOAT,
        unit=ebus_sdk.Unit.WATT,
        format_str=None,
        settable=False,
    )


def test_make_property_attaches_to_node() -> None:
    prop = _prop()
    assert prop.id() == "active-power"


def test_make_property_value_encodes() -> None:
    prop = _prop()
    # set_value stores + publishes (through the mocked client); the SDK encodes
    # the float via str().
    prop.set_value(1234.5)
    assert prop.coerced_value() == "1234.5"
