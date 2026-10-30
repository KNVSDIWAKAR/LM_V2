"""Node functions are registered by name so a playbook can refer to them (`run: intake.load_case`).

A node function takes (state, deps) and returns a dict of state updates. Include `outcome`
when the playbook routes on it, and `detail` for a one-line note in the trace.
"""

import importlib
import pkgutil
from collections.abc import Callable
from typing import Any

NodeFn = Callable[[dict[str, Any], Any], dict[str, Any]]
NODES: dict[str, NodeFn] = {}


def node(name: str) -> Callable[[NodeFn], NodeFn]:
    def register(fn: NodeFn) -> NodeFn:
        if name in NODES:
            raise ValueError(f"node {name!r} registered twice")
        NODES[name] = fn
        return fn

    return register


def load_node_modules() -> None:
    """Import every module in app/engine/nodes so their @node functions register."""
    from . import nodes

    for module in pkgutil.iter_modules(nodes.__path__):
        importlib.import_module(f"{nodes.__name__}.{module.name}")
