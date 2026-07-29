"""Tests for the setter fan-in: coverage validation + SDK callback adaptation.

ebus-sdk owns the ``/set`` subscription + decode; set_router owns the registry,
the fail-loud coverage check, and ``make_set_callback`` (coerce per datatype +
invoke the handler)."""

from __future__ import annotations

import pytest

from dist_enc_sim.exceptions import MissingSetterError
from dist_enc_sim.wire.set_router import (
    SetterRegistry,
    check_setter_coverage,
    make_set_callback,
)


def _settables() -> dict[str, list[tuple[str, str]]]:
    return {
        "circuit": [("switch", "relay"), ("load-shed", "priority")],
        "panel": [("pcs", "dominant-power-source")],
    }


def _instances() -> list[tuple[str, str]]:
    return [("circuit", "c1"), ("circuit", "c2"), ("panel", "p1")]


def _noop(*_a: object) -> None:
    return None


def test_coverage_passes_when_all_registered() -> None:
    reg = SetterRegistry()
    reg.register("circuit", "switch/relay", _noop)
    reg.register("circuit", "load-shed/priority", _noop)
    reg.register("panel", "pcs/dominant-power-source", _noop)
    # No raise.
    check_setter_coverage(instances=_instances(), settables_by_class=_settables(), registry=reg)


def test_coverage_raises_on_missing_handler() -> None:
    reg = SetterRegistry()
    reg.register("circuit", "switch/relay", _noop)

    with pytest.raises(MissingSetterError) as excinfo:
        check_setter_coverage(
            instances=_instances(), settables_by_class=_settables(), registry=reg
        )
    assert ("circuit", "load-shed/priority") in excinfo.value.missing
    assert ("panel", "pcs/dominant-power-source") in excinfo.value.missing


def test_callback_coerces_boolean_and_invokes() -> None:
    got: list[tuple[str, str, str, object, str]] = []

    def handler(ec: str, iid: str, pp: str, value: object) -> None:
        got.append((ec, iid, pp, value, type(value).__name__))

    cb = make_set_callback(
        handler,
        entity_class="circuit",
        instance_id="c1",
        property_path="switch/relay",
        datatype="boolean",
    )
    cb("false")  # ebus-sdk delivers a decoded str for non-json datatypes
    cb("true")
    assert got == [
        ("circuit", "c1", "switch/relay", False, "bool"),
        ("circuit", "c1", "switch/relay", True, "bool"),
    ]


def test_callback_coerces_numeric() -> None:
    got: list[object] = []
    fcb = make_set_callback(
        lambda *a: got.append(a[3]),
        entity_class="evse",
        instance_id="e1",
        property_path="config/max-charge-current",
        datatype="float",
    )
    fcb("1500.5")
    icb = make_set_callback(
        lambda *a: got.append(a[3]),
        entity_class="evse",
        instance_id="e1",
        property_path="config/max-charge-current",
        datatype="integer",
    )
    icb("32")
    assert got == [1500.5, 32]


def test_callback_json_payload_passes_through() -> None:
    got: list[object] = []
    cb = make_set_callback(
        lambda *a: got.append(a[3]),
        entity_class="panel",
        instance_id="p1",
        property_path="shed/policy",
        datatype="json",
    )
    cb({"algorithm": "soc-priority.v1"})  # SDK delivers a parsed object for json
    assert got == [{"algorithm": "soc-priority.v1"}]


def test_callback_decode_failure_is_dropped() -> None:
    got: list[object] = []
    cb = make_set_callback(
        lambda *a: got.append(a),
        entity_class="evse",
        instance_id="e1",
        property_path="config/max-charge-current",
        datatype="float",
    )
    cb("not-a-number")  # malformed payload logged + dropped, handler not called
    assert got == []


def test_callback_swallows_handler_exception() -> None:
    def boom(*_a: object) -> None:
        raise RuntimeError("handler bug")

    cb = make_set_callback(
        boom,
        entity_class="circuit",
        instance_id="c1",
        property_path="switch/relay",
        datatype="boolean",
    )
    # Runs on the MQTT network thread: a raising handler is logged + swallowed,
    # never propagated.
    cb("true")
