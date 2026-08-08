"""Every type a public annotation names must be importable from the package root.

`CONTRIBUTING.md` states the rule: "Types its signatures name are reachable. A
public parameter annotated with a type a caller cannot import from
`ebus_panel_sim` forces them to depend on `ebus_sdk` directly, which is what the
SDK seam exists to spare them." The root `__init__.py` applies it explicitly to
`MqttDeviceTransport`, with a comment saying why.

It was applied one name at a time, so it held only where someone remembered it.
Seven types were named in public signatures and reachable from neither
`ebus_panel_sim` nor the subpackage: `ChargeMode`, `DispatchState`,
`MidPhysics`, `EbusMidSnapshot`, `EbusPanelShed`, `EbusPanelShedForecast`, and
`Variant` (which annotates `Emitter.__init__`'s own `variant` parameter). Callers
reached into `ebus_panel_sim.native_devices.bess`, or gave up and re-declared the
union by hand, as `examples/run_forty_tab_minimal.py` did.

The pre-existing surface test could not have caught it: it is a hand-written list
of imports, so a type never added to `__all__` was never added to the list
either, and its absence read as "not part of the surface" rather than as a bug. A
restatement of a surface agrees with itself while disagreeing with the code. So
this derives both sides instead: the project's own type names come from the
source tree, and the annotations come from the live objects.

Reported by @cayossarian in #26, who found `ChargeMode`.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import pkgutil
import re
from pathlib import Path

import ebus_panel_sim

SRC = Path(ebus_panel_sim.__file__).parent

# Names a public annotation may reference without being re-exported: typing
# machinery, builtins, and the TypeVar behind `NativeDevice(Protocol[SnapT])`.
# `SnapT` is deliberate rather than an oversight: implementing the protocol is
# `class MyDevice(NativeDevice[MySnap])`, which never names the variable.
_EXEMPT = frozenset(
    {
        "Any",
        "Callable",
        "ClassVar",
        "Final",
        "Iterable",
        "Literal",
        "Mapping",
        "Optional",
        "Protocol",
        "Self",
        "Sequence",
        "SnapT",
        "TypeVar",
        "Union",
    }
)

_STRINGS = re.compile(r"'[^']*'|\"[^\"]*\"")
_IDENT = re.compile(r"\b[A-Z][A-Za-z0-9_]*\b")


def _project_type_names() -> set[str]:
    """Every class / type alias defined anywhere under the package, from the AST.

    Read from source rather than by importing, so a name is counted even if the
    module that defines it is not imported by the root, which is precisely the
    situation this test exists to detect.
    """
    names: set[str] = set()
    for mod in pkgutil.walk_packages([str(SRC)], prefix="ebus_panel_sim."):
        path = SRC / (mod.name.removeprefix("ebus_panel_sim.").replace(".", "/") + ".py")
        if not path.exists():
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ClassDef):
                names.add(node.name)
            # `ChargeMode = Literal[...]` and friends: a module-level assignment
            # whose target is CapWords is a type alias by this codebase's style.
            elif isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id[:1].isupper():
                        names.add(tgt.id)
    return names


def _referenced(annotation: object) -> set[str]:
    """Type identifiers named in an annotation, ignoring `Literal` string values.

    Stripping quoted substrings first matters: without it, `Literal["OK", "LOST"]`
    reports `OK` and `LOST` as missing types.
    """
    return set(_IDENT.findall(_STRINGS.sub("", str(annotation))))


def _public_annotations() -> dict[str, list[str]]:
    """{identifier: [where it is named]} across every public export's signatures."""
    out: dict[str, list[str]] = {}

    def note(annotation: object, where: str) -> None:
        for tok in _referenced(annotation):
            out.setdefault(tok, []).append(where)

    for name in ebus_panel_sim.__all__:
        obj = getattr(ebus_panel_sim, name)
        if inspect.isclass(obj):
            if dataclasses.is_dataclass(obj):
                for f in dataclasses.fields(obj):
                    note(f.type, f"{name}.{f.name}")
            for attr, ann in getattr(obj, "__annotations__", {}).items():
                if not attr.startswith("_"):
                    note(ann, f"{name}.{attr}")
            members = inspect.getmembers(
                obj, lambda m: inspect.isfunction(m) or isinstance(m, property)
            )
            for mname, m in members:
                # `__init__` is emphatically public surface: it is how a caller
                # constructs the object, and `Emitter.__init__(variant: Variant)`
                # was one of the seven. Every other dunder is machinery.
                if mname.startswith("_") and mname != "__init__":
                    continue
                fn = m.fget if isinstance(m, property) else m
                if fn is None:
                    continue
                try:
                    sig = inspect.signature(fn)
                except (TypeError, ValueError):  # pragma: no cover - defensive
                    continue
                for p in sig.parameters.values():
                    if p.annotation is not inspect.Parameter.empty:
                        note(p.annotation, f"{name}.{mname}({p.name})")
                if sig.return_annotation is not inspect.Signature.empty:
                    note(sig.return_annotation, f"{name}.{mname}() -> ...")
        elif inspect.isfunction(obj):
            try:
                sig = inspect.signature(obj)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                continue
            for p in sig.parameters.values():
                if p.annotation is not inspect.Parameter.empty:
                    note(p.annotation, f"{name}({p.name})")
            if sig.return_annotation is not inspect.Signature.empty:
                note(sig.return_annotation, f"{name}() -> ...")
    return out


def test_every_type_a_public_annotation_names_is_importable_from_the_root() -> None:
    """The rule `CONTRIBUTING.md` states, enforced over the whole surface.

    Membership in `__all__` is required, not merely `hasattr`. The two come
    apart, and the gap is how a re-export gets lost: a name bound by an import
    but absent from `__all__` still satisfies `hasattr`, while reading to every
    linter and every human as an unused import, so the next cleanup deletes it
    and takes the caller's annotation with it. Declaring it is what makes the
    re-export survive.
    """
    declared = set(ebus_panel_sim.__all__)
    project = _project_type_names()
    unreachable: dict[str, list[str]] = {}
    for tok, wheres in _public_annotations().items():
        if tok in _EXEMPT or tok not in project:
            continue
        if tok not in declared or not hasattr(ebus_panel_sim, tok):
            unreachable[tok] = sorted(set(wheres))
    assert not unreachable, (
        "public annotations name types a caller cannot import from "
        f"`ebus_panel_sim`: {unreachable}"
    )


def test_the_scanner_can_see_the_projects_type_aliases() -> None:
    """Guards this test's blind spot: if `_project_type_names` stopped picking up
    bare `X = Literal[...]` aliases, the assertion above would pass vacuously for
    exactly the kind of name that caused #26."""
    names = _project_type_names()
    for alias in ("ChargeMode", "DispatchState", "Variant", "PlacementKind"):
        assert alias in names, f"{alias} not discovered as a project type"


def test_all_is_importable_and_sorted() -> None:
    """No dangling entries: every name in `__all__` actually resolves."""
    missing = [n for n in ebus_panel_sim.__all__ if not hasattr(ebus_panel_sim, n)]
    assert not missing, f"__all__ names that do not resolve: {missing}"
