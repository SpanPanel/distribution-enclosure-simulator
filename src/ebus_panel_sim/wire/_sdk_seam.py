"""Internal seam over ebus_sdk property construction.

Localises Property construction so a future SDK change to the property-dict
shape touches one file. NOT an abstraction layer: other modules hold and mutate
``ebus_sdk.Property`` instances directly (the publisher calls ``Property.set_value``;
the SDK owns ``/set`` decode and value encoding).
"""

from __future__ import annotations

from typing import Any

import ebus_sdk
from ebus_sdk import (
    MqttClient,
    MqttDeviceTransport,
    PropertyDatatype,
    Unit,
)

# Re-exported so ``emitter.py`` can name the injection point's type without
# importing ebus_sdk itself, which is the property this seam exists to preserve.
__all__ = [
    "MqttDeviceTransport",
    "make_property",
    "owned_client",
    "will_for_root_id",
]


def make_property(
    *,
    node: ebus_sdk.Node,
    key: str,
    name: str,
    datatype: PropertyDatatype,
    unit: Unit | None,
    format_str: str | None,
    settable: bool,
) -> ebus_sdk.Property:
    """Construct an ebus_sdk.Property from a profile property and attach it to a node."""
    spec: dict[str, Any] = {
        "id": key,
        "name": name,
        "datatype": datatype,
    }
    if unit is not None:
        spec["unit"] = unit
    if format_str is not None:
        spec["format"] = format_str
    if settable:
        spec["settable"] = True
    return node.add_property_from_dict(spec)


def owned_client(mqttc: object) -> MqttClient | None:
    """Return *mqttc* when it is a client the SDK built and therefore owns.

    ebus-sdk 0.18 narrowed the injected-transport contract: ``MqttDeviceTransport``
    deliberately omits ``start`` / ``stop``, because those resolve only on the
    concrete client the SDK constructs for an ``mqtt_cfg=`` root — never on one the
    caller injected and still owns. The SDK makes the same distinction internally
    (``Controller.stop`` stops via its owned handle, "never via self.mqttc").

    Narrowing to the concrete class states that rule in the types instead of
    assuming it: a bring-your-own-transport root returns None here and is left for
    its owner to stop, which is the behaviour the SDK's contract asks for.
    """
    return mqttc if isinstance(mqttc, MqttClient) else None


def will_for_root_id(root_id: str) -> dict[str, str]:
    """The Last Will descriptor for a tree rooted at *root_id*, before any tree exists.

    A bring-your-own-transport caller has to register the will on their client
    *before connecting*, because it rides the CONNECT packet — which is earlier
    than they can hand that client to an ``Emitter``, and earlier than there is a
    root ``Device`` to ask. So this answers the question from the id alone.

    It does so by building a throwaway transport-free ``Device`` and returning its
    own ``will()``, rather than formatting the topic here. Construction opens no
    socket, and sourcing the descriptor from the SDK function that the SDK itself
    registers (``connect_broker`` passes ``lwt=self.will()``) is what makes a
    caller-registered will provably identical to an SDK-registered one. Formatting
    the topic locally would be the same string today and a silent divergence the
    day the SDK changes it.

    The shape is ``Device.will()``'s and therefore ``MqttClient(lwt=...)``'s, so
    it drops straight in where either is expected.
    """
    return ebus_sdk.Device(root_id).will()
