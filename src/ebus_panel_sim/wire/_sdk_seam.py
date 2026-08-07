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
    EBUS_HOMIE_MQTT_QOS,
    DeviceState,
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
    "publish_will_now",
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


def publish_will_now(root: ebus_sdk.Device, *, owned: MqttClient | None) -> bool:
    """Publish the root's will payload (``$state=lost``) as a retained message, now.

    A Last Will fires only when the broker sees an UNCLEAN disconnect. Every
    orderly teardown path here sends a clean DISCONNECT, and ebus-mqtt-client does
    that deliberately (``MqttClient.stop`` -> ``mqttc.disconnect()``), precisely so
    a normal shutdown is not reported to consumers as a crash. The consequence is
    that a simulator asked to *act* like a producer that died cannot get there by
    letting the will fire: it has to publish the will's own payload itself.

    Topic and payload come from ``Device.will()``, the same descriptor the SDK
    registers as the LWT, so this cannot drift from what a real will would have
    delivered.

    QoS deliberately follows the rest of the tree's ``$state`` publishes rather
    than the ``qos=0`` default the will registration uses: a registered will is
    delivered by the broker from its own state, whereas this goes out over a live
    connection that is about to close and has to actually land first.

    ``set_state`` moves the root's own state to ``LOST`` first, mirroring what
    ``Device.stop()`` does for ``DISCONNECTED``. Publishing a state the device
    object does not itself hold leaves the two disagreeing, and anything that later
    re-announces from that object (``refresh_tree()``, which the SDK asks a
    bring-your-own-transport caller to wire onto their client's on-connect handler)
    republishes ``ready`` straight over the ``lost`` we just sent.

    It runs before the ownership split rather than after, because that
    re-announce is only *reachable* on the injected path. An owned client's
    connection closes immediately behind this call, so nothing survives to
    re-announce from; a caller-supplied one stays up, reconnects, and does. Both
    paths need the state moved, and the path that needs it most is the one an
    ownership guard would have skipped.

    ``set_state`` also publishes ``$state`` itself, retained and at the device's
    QoS, through whichever transport the root holds — so on an injected transport
    that one call is the entire job, and nothing follows it here.

    An earlier revision added an explicit ``transport.publish`` after it, to hand
    the caller a paho ``MQTTMessageInfo`` to wait on. That is removed, because it
    was a byte-identical duplicate of what ``set_state`` had just sent and the
    handle it produced was unusable: waiting on it from the loop thread blocks for
    the full timeout and never completes, which is the same reason
    ``publish_and_flush`` is wrong on this path. Publishing twice to widen a
    window the caller cannot observe is not a service to them.

    The owned path does still repeat the value, for a different and real reason:
    ``set_state`` goes through the ordinary unflushed path, the socket closes
    immediately behind this function, and only a flushed publish is guaranteed to
    land first.

    **Caller obligation on an injected transport.** The ``lost`` is *queued* on
    the caller's loop, not flushed, and the emitter cannot flush it for them.
    Tearing the client down in the same synchronous breath as
    ``stop(graceful=False)`` drops it — measured as deterministic against a real
    broker with an ``asyncio_driver``-pumped client: an immediate ``driver.stop()``
    leaves the retained root at ``ready``, while letting the loop turn first
    leaves it at ``lost``. Letting the loop turn is the whole remedy; there is
    nothing to await.

    Returns whether the ``lost`` is on the wire as far as this function can tell:
    for an owned client, whether the flush completed; for an injected one,
    whether ``set_state`` moved the state and published (False when it was
    already ``LOST``, in which case the wire already carries it).
    """
    moved = root.set_state(DeviceState.LOST)
    if owned is None:
        return moved
    will = root.will()
    return bool(
        owned.publish_and_flush(
            will["topic"], will["payload"], qos=EBUS_HOMIE_MQTT_QOS, retain=True
        )
    )
