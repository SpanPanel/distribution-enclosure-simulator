"""Setter registry, ``/set`` coverage validation, and SDK callback wiring.

ebus-sdk owns the ``/set`` subscription and payload decode (empty-string ``0x00``
convention + JSON-schema validation); this module owns the producer-facing
fan-in:

* ``SetterRegistry`` — sync handlers keyed by ``(entity_class, property_path)``.
* ``check_setter_coverage`` — fail-loud if any settable property whose class is
  present in the manifest has no registered handler.
* ``make_set_callback`` — adapt a registry handler into an ebus-sdk
  ``Property`` set-callback. The SDK delivers a non-json payload as a decoded
  ``str`` (and a json payload as a parsed object); we coerce per the profile
  datatype and invoke the handler with
  ``(entity_class, instance_id, property_path, value)``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from dist_enc_sim.exceptions import MissingSetterError

_LOG = logging.getLogger(__name__)

# Sync handler: (entity_class, instance_id, property_path, value) -> None. The
# callback runs on the MQTT client's network thread.
SetterHandler = Callable[[str, str, str, object], None]


class SetterRegistry:
    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], SetterHandler] = {}

    def register(
        self,
        entity_class: str,
        property_path: str,
        handler: SetterHandler,
    ) -> None:
        self._handlers[(entity_class, property_path)] = handler

    def get(self, entity_class: str, property_path: str) -> SetterHandler | None:
        return self._handlers.get((entity_class, property_path))


def check_setter_coverage(
    *,
    instances: list[tuple[str, str]],
    settables_by_class: dict[str, list[tuple[str, str]]],
    registry: SetterRegistry,
) -> None:
    """Raise ``MissingSetterError`` if any settable property (for an entity class
    present in the manifest) has no registered handler."""
    declared_classes = {ec for ec, _iid in instances}
    missing: list[tuple[str, str]] = []
    for ec in declared_classes:
        for cap, key in settables_by_class.get(ec, []):
            prop_path = f"{cap}/{key}"
            if registry.get(ec, prop_path) is None:
                missing.append((ec, prop_path))
    if missing:
        raise MissingSetterError(missing=sorted(set(missing)))


def make_set_callback(
    handler: SetterHandler,
    *,
    entity_class: str,
    instance_id: str,
    property_path: str,
    datatype: str,
) -> Callable[[object], None]:
    """Wrap a registry handler as an ebus-sdk ``Property`` set-callback.

    Decode failure (a malformed ``/set`` payload) is logged and dropped — a bad
    command must not crash the emitter. A handler that raises is logged at ERROR
    and swallowed: the callback runs on the MQTT network thread, so propagating
    would only tear that thread down."""

    def _callback(raw: object) -> None:
        try:
            value = _coerce(raw, datatype)
        except (TypeError, ValueError):
            _LOG.warning(
                "set decode failed: entity_class=%s instance_id=%s property_path=%s "
                "raw=%r datatype=%s",
                entity_class,
                instance_id,
                property_path,
                raw,
                datatype,
            )
            return
        try:
            handler(entity_class, instance_id, property_path, value)
        except Exception:
            _LOG.exception(
                "setter handler raised: entity_class=%s instance_id=%s property_path=%s value=%r",
                entity_class,
                instance_id,
                property_path,
                value,
            )

    return _callback


def _coerce(raw: object, datatype: str) -> object:
    """Coerce an SDK-delivered ``/set`` payload to the profile datatype. JSON
    payloads arrive already parsed (non-str) and pass through unchanged."""
    if not isinstance(raw, str):
        return raw
    match datatype:
        case "float":
            return float(raw)
        case "integer":
            return int(raw)
        case "boolean":
            return raw.strip().lower() in ("true", "1")
        case _:
            return raw
