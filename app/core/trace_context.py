from __future__ import annotations
import contextvars
from pydantic import BaseModel, Field
from typing import Dict, List, Literal, Optional, Any
import time

class LayerTrace(BaseModel):
    total_ms: float = 0.0
    llm_ms: float = 0.0
    network_ms: float = 0.0
    provider: str = ""
    retry_count: int = 0
    tool_ms: float = 0.0
    db_ms: float = 0.0

class RequestTrace(BaseModel):
    trace_id: str
    layers: Dict[str, LayerTrace] = Field(default_factory=lambda: {
        "planner": LayerTrace(),
        "execution": LayerTrace(),
        "renderer": LayerTrace()
    })
    fallback_chain: List[str] = Field(default_factory=list)
    errors: List[Any] = Field(default_factory=list)
    tool_result_tokens: int = 0

    # ── Fast Path metrics ────────────────────────────────────────────────
    fast_path_used: bool = False
    fast_path_type: Optional[Literal["greeting", "identity", "thanks", "goodbye"]] = None

    # ── Execution-phase flags ────────────────────────────────────────────
    planner_executed: bool = False
    renderer_executed: bool = False
    planner_skipped: bool = False
    renderer_skipped: bool = False
    skip_reason: Optional[str] = None

    # ── Timing ──────────────────────────────────────────────────────────
    end_to_end_ms: float = 0.0

    # ── Token savings ───────────────────────────────────────────────────
    saved_planner_tokens: int = 0
    saved_renderer_tokens: int = 0
    saved_total_tokens: int = 0

_trace_ctx: contextvars.ContextVar[Optional[RequestTrace]] = contextvars.ContextVar("active_trace", default=None)

def set_active_trace(trace: RequestTrace):
    return _trace_ctx.set(trace)

def get_active_trace() -> Optional[RequestTrace]:
    return _trace_ctx.get(None)

def reset_active_trace(token):
    _trace_ctx.reset(token)
