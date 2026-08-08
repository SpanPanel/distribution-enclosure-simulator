"""Executes the documentation instead of trusting it.

Every caller obligation this package's bring-your-own-transport path adds is
carried by prose, and prose is not covered by any other test here. The recipes
below have already been wrong twice: the README's first draft invented
``MqttClient.on_connect`` and ``MqttClient.connect``, neither of which exists,
and the fix was applied to the README while an identical broken recipe stayed in
``Emitter.lwt_settings``'s docstring — which is what ``help()`` and every IDE
hover shows, and which ships inside the wheel.

A hand-copied transcription of a recipe cannot catch that: it passes while the
document it claims to mirror says something else entirely. So these tests read
the actual bytes of ``README.md`` and of ``inspect.getdoc(...)`` and run them.

They execute under the autouse paho mock from ``conftest``, so no socket opens.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import re
import textwrap
from pathlib import Path
from typing import Any

import pytest

from ebus_panel_sim import DeviceInstance, DeviceManifest, Emitter

README = Path(__file__).resolve().parents[1] / "README.md"

_PYTHON_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _manifest() -> DeviceManifest:
    """A manifest the documented recipes can be run against."""
    return DeviceManifest(
        instances=(
            DeviceInstance(
                "panel",
                "p1",
                "Span",
                metadata={
                    "vendor-name": "Span",
                    "serial-number": "p1",
                    "firmware-version": "r2026",
                    "hardware-version": "rev2",
                    "panel-size": "32",
                    "main-breaker-rating-a": "200",
                    "panel-model": "MAIN_32",
                    "postal-code": "94103",
                    "time-zone": "America/Los_Angeles",
                },
            ),
            DeviceInstance(
                "circuit",
                "c1",
                "Kitchen",
                metadata={
                    "tab-numbers": "1",
                    "breaker-rating-a": "20",
                    "default-priority": "NICE_TO_HAVE",
                    "relay-behavior": "controllable",
                    "placement": "downstream-of-lugs",
                },
            ),
        )
    )


def readme_python_blocks() -> list[str]:
    return _PYTHON_BLOCK.findall(README.read_text())


def byo_readme_block() -> str:
    """The bring-your-own-transport recipe, located by content rather than index.

    Keyed on ``lwt_settings`` so inserting another Python block above it does not
    silently point this test at the wrong code.
    """
    blocks = [b for b in readme_python_blocks() if "lwt_settings" in b]
    assert len(blocks) == 1, f"expected exactly one BYO recipe in README.md, found {len(blocks)}"
    return blocks[0]


def docstring_code_blocks(obj: object) -> list[str]:
    """Indented code blocks introduced by ``::`` in a runtime docstring."""
    doc = inspect.getdoc(obj) or ""
    return [textwrap.dedent(b) for b in re.findall(r"::\n\n((?:    .*\n|\n)+)", doc)]


def run_snippet(source: str, **namespace: Any) -> dict[str, Any]:
    scope: dict[str, Any] = dict(namespace)
    exec(compile(source, "<documentation>", "exec"), scope)
    return scope


async def run_async_snippet(source: str, **namespace: Any) -> dict[str, Any]:
    """Execute a snippet that uses top-level ``await``, as documentation may.

    ``PyCF_ALLOW_TOP_LEVEL_AWAIT`` makes the compiled code a coroutine, which is
    the only way to run an ``async`` recipe as written rather than rewriting it
    into a shape no reader would copy.
    """
    scope: dict[str, Any] = dict(namespace)
    code = compile(source, "<documentation>", "exec", ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    coroutine = eval(code, scope)
    if coroutine is not None:
        await coroutine
    return scope


def test_readme_byo_recipe_executes() -> None:
    """The guide. Read from README.md itself, so editing it back to a broken
    shape fails here — the property a transcription cannot provide."""
    scope = run_snippet(byo_readme_block(), manifest=_manifest())

    emitter = scope["emitter"]
    client = scope["client"]
    assert client.on_connect_callback == emitter.republish_tree, (
        "the recipe must leave the re-announce hook wired"
    )
    client.on_connect_callback()  # the client invokes it with no arguments


def test_lwt_settings_docstring_example_executes() -> None:
    """The API reference, which ships in the wheel and is what ``help()`` shows.

    Held to the same standard as the README because it is the one people reach
    for first, and because this is precisely where the previous fix was missed.
    """
    blocks = docstring_code_blocks(Emitter.lwt_settings)
    assert blocks, "Emitter.lwt_settings should carry a usable example"

    for block in blocks:
        run_snippet(block, manifest=_manifest())


def test_readme_asyncio_driver_recipe_executes() -> None:
    """The motivating use case, and the line the previous fix missed.

    ``client.asyncio_driver()`` was offered as an inline alternative to
    ``client.start()`` in a synchronous script, where it raises
    ``RuntimeError: no running event loop``; and even inside a loop it only
    *constructs* a driver whose ``start()`` is a coroutine, so it opened nothing
    either way. It is a separate ``async`` block now, and this runs it.

    Driven through ``asyncio.run`` from a synchronous test rather than an async
    one, so the suite needs no async pytest plugin: this repo's dev group has
    none, and one test is not worth a dependency in it.
    """
    blocks = [b for b in readme_python_blocks() if "asyncio_driver" in b]
    assert len(blocks) == 1, f"expected one asyncio_driver recipe, found {len(blocks)}"

    setup = run_snippet(byo_readme_block(), manifest=_manifest())
    scope = asyncio.run(
        run_async_snippet(blocks[0], client=setup["client"], emitter=setup["emitter"])
    )
    assert scope["driver"] is not None


@pytest.mark.parametrize("block", readme_python_blocks(), ids=range(len(readme_python_blocks())))
def test_every_readme_python_block_at_least_parses(block: str) -> None:
    """Blocks this suite does not execute must still be syntactically real.

    Weaker than execution, and deliberately so: some blocks describe a producer
    loop that never terminates. Parsing is what can be checked for all of them,
    and it still catches a fenced block that was never run at all. Top-level
    ``await`` is allowed, since an async recipe is legitimate documentation.
    """
    compile(block, "<documentation>", "exec", ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
