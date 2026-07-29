from dist_enc_sim.manifest import DeviceInstance, DeviceManifest
from dist_enc_sim.wire.graph_builder import BuiltGraph, build_graph
from dist_enc_sim.wire.mapping_loader import load_mapping_table
from dist_enc_sim.wire.profile_loader import load_profiles


def _manifest_panel_with_one_circuit() -> DeviceManifest:
    return DeviceManifest(
        instances=(
            DeviceInstance(entity_class="panel", instance_id="p1", display_name="Span"),
            DeviceInstance(entity_class="circuit", instance_id="c1", display_name="Kitchen"),
        )
    )


def _build() -> BuiltGraph:
    profiles = load_profiles()
    mapping = load_mapping_table()
    return build_graph(_manifest_panel_with_one_circuit(), mapping, profiles, mqtt_cfg={})


def test_build_graph_for_panel_and_one_circuit() -> None:
    g = _build()
    # Under child-of-parent, the circuit is its own child Device beneath the panel.
    assert "p1" in g.devices
    assert "c1" in g.devices
    child = g.devices["c1"]
    assert child.parent_id() == "p1"
    assert child.root_id() == "p1"
    # The parent enclosure advertises its child devices (ebus-sdk description()).
    assert "c1" in g.devices["p1"].description()["children"]
    # Circuit's properties are present on the child device under plain capability nodes.
    assert ("circuit", "c1", "meter/active-power") in g.properties
    assert ("circuit", "c1", "switch/relay") in g.properties


def test_build_graph_is_deterministic() -> None:
    g1 = _build()
    g2 = _build()
    assert sorted(g1.properties.keys()) == sorted(g2.properties.keys())
    d1 = g1.devices["p1"].description()
    d2 = g2.devices["p1"].description()
    # description() restamps ``version`` each call, so compare the stable parts.
    assert d1["children"] == d2["children"]
    assert sorted(d1["nodes"]) == sorted(d2["nodes"])


def test_build_graph_includes_panel_settable_property() -> None:
    g = _build()
    assert ("panel", "p1", "shed/asserted-islanding-state") in g.properties
