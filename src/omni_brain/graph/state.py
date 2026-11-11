"""Estado Tipado e Checkpointer do Grafo (Suporte Nativo a Pausa/Retomada Human-in-the-Loop)."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Literal

from omni_brain.schemas.models import (
    HITLApprovalRequest,
    InboundMessage,
    UserRole,
)


@dataclass
class OmniBrainState:
    """Estado completo de uma sessão conversacional no LangGraph."""

    thread_id: str
    inbound_message: InboundMessage
    role: UserRole = UserRole.PUBLIC
    guardrail_allowed: bool = True
    guardrail_reason: str = ""
    allowed_mcp_tools: list[str] = field(default_factory=list)
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    compressed_summary: str = ""
    invoked_tools: list[str] = field(default_factory=list)
    structured_output: dict[str, Any] | None = None
    pending_approval: HITLApprovalRequest | None = None
    status: Literal["running", "waiting_approval", "completed", "blocked_by_guardrail"] = "running"
    reply_text: str = ""


class StatefulCheckpointer:
    """Persiste snapshots de estado por `thread_id` (compatível com Redis/Postgres em produção)."""

    def __init__(self) -> None:
        self._storage: dict[str, OmniBrainState] = {}

    def save(self, state: OmniBrainState) -> None:
        self._storage[state.thread_id] = copy.deepcopy(state)

    def load(self, thread_id: str) -> OmniBrainState | None:
        saved = self._storage.get(thread_id)
        return copy.deepcopy(saved) if saved is not None else None
