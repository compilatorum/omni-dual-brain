"""Schemas Pydantic v2 para validação estrita, RBAC, HITL e tradução determinística entre APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChannelType(str, Enum):
    WHATSAPP = "whatsapp"
    EMACS = "emacs"
    WEB_PUBLIC = "web_public"
    HERMES_WORKER = "hermes_worker"


class UserRole(str, Enum):
    PUBLIC = "public"
    ADMIN = "admin"


class MediaType(str, Enum):
    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    DOCUMENT = "document"


class MultimodalAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_type: MediaType
    media_url: str | None = None
    mime_type: str | None = None
    raw_bytes_b64: str | None = None
    transcript_or_caption: str | None = None


class InboundMessage(BaseModel):
    """Mensagem de entrada normalizada pelo Harness (WhatsApp, Emacs ou Web)."""

    model_config = ConfigDict(extra="forbid")

    message_id: str
    user_id: str = Field(..., description="Número E.164 no WhatsApp, user ID no Emacs ou sessão Web")
    channel: ChannelType
    text: str = ""
    attachments: list[MultimodalAttachment] = Field(default_factory=list)
    auth_signature: str | None = Field(
        default=None, description="Assinatura HMAC/Bearer enviada pelo cliente Emacs ou API Admin"
    )
    pin_2fa: str | None = Field(
        default=None, description="PIN opcional para operações críticas via WhatsApp Admin"
    )
    emacs_buffer_name: str | None = None
    emacs_buffer_content: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GuardrailVerdict(BaseModel):
    """Resultado do Guardrail de Entrada e Saída."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    role: UserRole
    reason: str
    detected_injection: bool = False
    allowed_mcp_tools: list[str] = Field(default_factory=list)


class GitHubCommitSummary(BaseModel):
    """Resumo estruturado de commit do GitHub."""

    model_config = ConfigDict(extra="forbid")

    sha: str = Field(..., min_length=7, max_length=40)
    author: str
    message: str
    committed_at: str
    files_changed: int = Field(ge=0)


class NeynarCastMetric(BaseModel):
    """Métricas de engajamento de um cast no Farcaster via API da Neynar."""

    model_config = ConfigDict(extra="forbid")

    cast_hash: str = Field(..., pattern=r"^0x[a-fA-F0-9]+$")
    text: str
    likes_count: int = Field(ge=0, description="Quantidade de corações/likes")
    recasts_count: int = Field(ge=0)
    replies_count: int = Field(ge=0)
    published_at: str


class KarmaHQMilestonePayload(BaseModel):
    """Payload JSON determinístico validado via Pydantic para atualização de projeto no KarmaHQ."""

    model_config = ConfigDict(extra="forbid")

    project_uid: str = Field(..., pattern=r"^0x[a-fA-F0-9]+$")
    milestone_title: str = Field(..., min_length=5, max_length=160)
    reporting_period: str
    summary_markdown: str = Field(..., min_length=20)
    github_repo: str
    total_commits_week: int = Field(ge=0)
    highlighted_commits: list[GitHubCommitSummary] = Field(default_factory=list)
    farcaster_total_likes: int = Field(ge=0)
    farcaster_total_recasts: int = Field(ge=0)
    top_casts: list[NeynarCastMetric] = Field(default_factory=list)
    deliverables_links: list[str] = Field(default_factory=list)
    verified_by_admin: bool = False

    @field_validator("summary_markdown")
    @classmethod
    def forbid_secrets_in_summary(cls, value: str) -> str:
        forbidden_tokens = ("ghp_", "sk-", "SUPABASE_SERVICE_ROLE_KEY", "PRIVATE_KEY")
        for token in forbidden_tokens:
            if token in value:
                raise ValueError(f"Possível segredo detectado no relatório: {token}")
        return value


class HITLActionType(str, Enum):
    KARMAHQ_SUBMIT = "karmahq_submit"
    FARCASTER_PUBLISH = "farcaster_publish"
    GITHUB_PUSH_OR_PR = "github_push_or_pr"
    SYSOP_TERMINAL_EXEC = "sysop_terminal_exec"
    ARCHON_WORKTREE_PR = "archon_worktree_pr"


class HITLApprovalRequest(BaseModel):
    """Estrutura gerada pelo nó Human-in-the-Loop ao pausar o grafo."""

    model_config = ConfigDict(extra="forbid")

    approval_id: str
    thread_id: str
    action_type: HITLActionType
    target_mcp_tool: str
    description: str
    structured_payload: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HITLDecision(BaseModel):
    """Decisão enviada pelo Admin no Emacs ou WhatsApp ('Aprovado' / 'Rejeitado')."""

    model_config = ConfigDict(extra="forbid")

    thread_id: str
    approval_id: str
    decision: Literal["approved", "rejected"]
    admin_user_id: str
    channel: ChannelType
    auth_signature: str | None = None
    edited_payload: dict[str, Any] | None = None


class ArchonTaskSpec(BaseModel):
    """Especificação de auto-correção disparada pelo Hermes/Admin para o Archon."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    issue_summary: str
    target_node_or_module: str
    worktree_path: str
    branch_name: str
    test_command: str = "pytest"
    status: Literal["planned", "worktree_created", "tests_passed", "pr_ready"] = "planned"


class AgentResponse(BaseModel):
    """Resposta padronizada do Cérebro Único para WhatsApp, Emacs ou Frontend."""

    model_config = ConfigDict(extra="forbid")

    thread_id: str
    role: UserRole
    status: Literal["completed", "waiting_approval", "blocked_by_guardrail"]
    reply_text: str
    pending_approval: HITLApprovalRequest | None = None
    structured_data: dict[str, Any] | None = None
    invoked_tools: list[str] = Field(default_factory=list)
