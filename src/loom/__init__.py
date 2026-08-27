"""Loom: a hardware-aware execution runtime for AI agents."""

from loom.adapters import AdapterRequest, ModelAdapter
from loom.contracts import (
    HardwareSnapshot,
    ModelRequest,
    ModelResponse,
    Operation,
    RouteDecision,
    ToolCall,
    ToolResult,
    TraceEvent,
)

__version__ = "0.1.0.dev0"

__all__ = [
    "AdapterRequest",
    "HardwareSnapshot",
    "ModelAdapter",
    "ModelRequest",
    "ModelResponse",
    "Operation",
    "RouteDecision",
    "ToolCall",
    "ToolResult",
    "TraceEvent",
    "__version__",
]
