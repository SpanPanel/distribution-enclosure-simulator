from dist_enc_sim.manifest import DeviceInstance, DeviceManifest
from dist_enc_sim.wire.graph_builder import build_graph
from dist_enc_sim.wire.mapping_loader import load_mapping_table
from dist_enc_sim.wire.profile_loader import load_profiles


def _manifest_panel_with_one_circuit() -> DeviceManifest:
    return DeviceManifest(
        instances=(
            DeviceInstance(entity_class="panel", instance_id="p1", display_name="Span"),
            DeviceInstance(entity_class="circuit", instance_id="c1", display_name="Kitchen"),
        )
    )


def test_build_graph_for_panel_and_one_circuit() -> None:
    profiles = load_profiles()
    mapping = load_mapping_table()
    g = build_graph(_manifest_panel_with_one_circuit(), mapping, profiles)
    # Under child-of-parent, the circuit is its own child Device beneath the panel.
    assert "p1" in g.devices
    assert "c1" in g.devices
    assert g.device_descriptors["c1"] == ("circuit", "p1")
    assert "c1" in g.description_payloads["p1"]["children"]  # parent advertises children
    # Circuit's properties are present on the child device under plain capability nodes.
    assert ("circuit", "c1", "meter/active-power") in g.properties
    assert ("circuit", "c1", "switch/relay") in g.properties


def test_build_graph_is_deterministic() -> None:
    profiles = load_profiles()
    mapping = load_mapping_table()
    g1 = build_graph(_manifest_panel_with_one_circuit(), mapping, profiles)
    g2 = build_graph(_manifest_panel_with_one_circuit(), mapping, profiles)
    assert sorted(g1.properties.keys()) == sorted(g2.properties.keys())
    assert g1.description_payloads == g2.description_payloads


def test_build_graph_includes_panel_settable_property() -> None:
    profiles = load_profiles()
    mapping = load_mapping_table()
    g = build_graph(_manifest_panel_with_one_circuit(), mapping, profiles)
    assert ("panel", "p1", "shed/asserted-islanding-state") in g.properties
