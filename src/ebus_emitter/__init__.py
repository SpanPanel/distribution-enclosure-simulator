"""ebus-emitter — producer-side Homie wire publisher with native-device runtime.

Architecture (v0.3.0):

- **Wire layer** (``wire/``): vendored Homie 5 device profiles + mapping descriptors,
  graph builder, lifecycle controller, /set router, property bag diff cache, SDK seam.
- **Native devices** (``native_devices/``): emitter-resident, configured-and-self-driving
  device runtimes (BESS dispatch, load shedding).
- **Manifest physics** (``manifest_physics.py``): typed accessor over
  ``DeviceInstance.metadata`` for physics-relevant fields (voltage, breaker rating,
  tabs/legs, placement, default priority, relay behaviour).
- **Tick pipeline** (``relay_resolver.py`` + ``energy_integrator.py`` + ``panel_meter.py``
  + ``conventions/tab_legs.py``): per-tick state machinery the emitter uses to
  resolve circuit relay state, integrate energy, derive per-leg currents, and
  aggregate panel-level fields.

Producer contract (v0.3.0): build a ``DeviceManifest`` once at startup, then call
``Emitter.publish_tick(TickInputs)`` each tick with signed circuit/EVSE powers,
``current_time``, and ``grid_online``. The emitter does the rest."""

from ebus_emitter.conventions.tab_legs import Leg, legs_for_tabs
from ebus_emitter.emitter import Emitter
from ebus_emitter.exceptions import (
    EmitterError,
    EmitterStateError,
    ManifestValidationError,
    MissingSetterError,
    ProfileValidationError,
    RuntimeSpecValidationError,
)
from ebus_emitter.manifest import DeviceInstance, DeviceManifest
from ebus_emitter.manifest_physics import (
    BessPhysics,
    CircuitPhysics,
    EvsePhysics,
    LugsPhysics,
    ManifestPhysicsView,
    PanelPhysics,
    PvPhysics,
)
from ebus_emitter.native_devices import (
    BESSConfig,
    BESSDevice,
    LoadSheddingConfig,
    LoadSheddingDevice,
    NativeDevice,
    NativeTickContext,
)
from ebus_emitter.relay_resolver import RelayRequester, RelayResolver, RelayState
from ebus_emitter.snapshot import (
    EbusBatterySnapshot,
    EbusCircuitSnapshot,
    EbusEvseSnapshot,
    EbusLugsSnapshot,
    EbusPanelDoor,
    EbusPanelInfo,
    EbusPanelMeter,
    EbusPanelPcs,
    EbusPanelPowerFlows,
    EbusPanelSnapshot,
    EbusPanelStatus,
    EbusPvSnapshot,
)
from ebus_emitter.tick_inputs import PanelEnvelopeTick, TickInputs
from ebus_emitter.wire.set_router import SetterHandler, SetterRegistry

__all__ = [
    "BESSConfig",
    "BESSDevice",
    "BessPhysics",
    "CircuitPhysics",
    "DeviceInstance",
    "DeviceManifest",
    "EbusBatterySnapshot",
    "EbusCircuitSnapshot",
    "EbusEvseSnapshot",
    "EbusLugsSnapshot",
    "EbusPanelDoor",
    "EbusPanelInfo",
    "EbusPanelMeter",
    "EbusPanelPcs",
    "EbusPanelPowerFlows",
    "EbusPanelSnapshot",
    "EbusPanelStatus",
    "EbusPvSnapshot",
    "Emitter",
    "EmitterError",
    "EmitterStateError",
    "EvsePhysics",
    "Leg",
    "LoadSheddingConfig",
    "LoadSheddingDevice",
    "LugsPhysics",
    "ManifestPhysicsView",
    "ManifestValidationError",
    "MissingSetterError",
    "NativeDevice",
    "NativeTickContext",
    "PanelEnvelopeTick",
    "PanelPhysics",
    "ProfileValidationError",
    "PvPhysics",
    "RelayRequester",
    "RelayResolver",
    "RelayState",
    "RuntimeSpecValidationError",
    "SetterHandler",
    "SetterRegistry",
    "TickInputs",
    "legs_for_tabs",
]
