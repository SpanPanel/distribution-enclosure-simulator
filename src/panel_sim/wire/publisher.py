"""Wire publisher — the per-tick diff/publish loop over the SDK device tree.

The emitter hands the publisher a ``PropertyBag`` of this tick's full property
values. The publisher diffs against the prior tick and, for each changed
property, calls its ebus-sdk ``Property.set_value``: the SDK encodes the value
and publishes the retained topic through the root device's shared MQTT client.

Encoding and topic construction are the SDK's job now; this module owns the
diff-only guarantee (only changed properties are re-published) and the fan-out.
The ``None``-skip in ``BagBuilder.build`` means a bag never carries ``None``, so
``set_value`` is never asked to retract a topic here.
"""

from __future__ import annotations

from panel_sim.wire.graph_builder import BuiltGraph
from panel_sim.wire.property_bag import PropertyBag, PropertyDiffer, PropertyKey


class Publisher:
    """Owns the diff/publish loop. Consumers hand it a ``PropertyBag``; it
    computes the delta against the prior tick and publishes each change via the
    property's ``set_value``."""

    def __init__(self, graph: BuiltGraph) -> None:
        self._graph = graph
        self._differ = PropertyDiffer(all_keys=tuple(graph.properties.keys()))

    def publish(self, bag: PropertyBag) -> list[PropertyKey]:
        """Publish every property changed since the last call. Returns the list
        of changed keys (the diff) for observability and tests."""
        changes = self._differ.diff(bag)
        for key, value in changes:
            self._graph.properties[key].set_value(value)
        self._differ.commit(changes)
        return [key for key, _ in changes]
