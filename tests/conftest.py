"""Shared test fixtures.

The simulator publishes through ebus-sdk, whose root ``Device`` owns a real
``ebus_mqtt_client.MqttClient`` (paho under the hood). We test broker-free the
same way ebus-sdk tests itself: patch paho's ``Client`` with a ``MagicMock`` so
the real SDK + MqttClient run but no socket opens. ``rec`` wraps the mock and
exposes the publishes/subscriptions in the ``(topic, payload, qos, retain)``
shape assertions want. Payloads are ``str`` (the SDK's ``coerced_value``) and
QoS is 2 (the eBus convention default), not the pre-migration ``bytes``/QoS-1.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def effective_retained(published: list[tuple[str, str, int, bool]]) -> dict[str, str]:
    """The retained view a late-joining consumer would see.

    Last non-empty retained payload per topic; an empty retained payload is a
    retraction and removes the topic rather than storing ``""``. Non-retained
    publishes are invisible to a late joiner and do not appear.

    Shared by every recorder rather than reimplemented per transport: two views
    that disagree about what "retained" means would let a test assert against a
    consumer that does not exist.
    """
    out: dict[str, str] = {}
    for topic, data, _qos, retain in published:
        if not retain:
            continue
        if data == "":
            out.pop(topic, None)
        else:
            out[topic] = data
    return out


class PahoRecorder:
    """Read model over the mocked paho client's recorded calls."""

    def __init__(self, paho: MagicMock) -> None:
        self._paho = paho

    @property
    def published(self) -> list[tuple[str, str, int, bool]]:
        """Every publish as (topic, payload, qos, retain), in call order."""
        return [
            (c.args[0], c.args[1], c.args[2], c.args[3]) for c in self._paho.publish.call_args_list
        ]

    @property
    def retained(self) -> dict[str, str]:
        return effective_retained(self.published)

    @property
    def subscribed(self) -> list[str]:
        return [c.args[0] for c in self._paho.subscribe.call_args_list]

    def reset(self) -> None:
        self._paho.publish.reset_mock()
        self._paho.subscribe.reset_mock()


@pytest.fixture(autouse=True)
def mock_paho() -> object:
    """Patch paho so no real MQTT socket opens; is_connected/publish/subscribe
    all report success. Autouse: every test gets a mocked transport."""
    with patch("ebus_mqtt_client.client.mqtt.Client") as mock_cls:
        paho = MagicMock()
        paho.is_connected.return_value = True
        paho.subscribe.return_value = (0, 1)  # (MQTT_ERR_SUCCESS, msg_id)
        paho.publish.return_value = MagicMock(rc=0)  # MQTT_ERR_SUCCESS
        mock_cls.return_value = paho
        yield paho


@pytest.fixture
def rec(mock_paho: MagicMock) -> PahoRecorder:
    """Recorder over the mocked paho client, for wire-level assertions."""
    return PahoRecorder(mock_paho)
