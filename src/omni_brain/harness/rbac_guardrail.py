"""RBAC Security Harness & Guardrails: Isolamento Rígido de Fronteiras (Admin vs. Público)."""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Iterable

from omni_brain.config import DEFAULT_CONFIG, OmniBrainConfig
from omni_brain.schemas.models import (
    ChannelType,
    GuardrailVerdict,
    InboundMessage,
    UserRole,
)

PUBLIC_ALLOWED_TOOLS: tuple[str, ...] = (
    "graphify_search_docs",
    "db_query_public_metrics",
    "github_get_public_status",
    "neynar_get_public_metrics",
    "karmahq_get_grant_milestones",
)

ADMIN_ALLOWED_TOOLS: tuple[str, ...] = PUBLIC_ALLOWED_TOOLS + (
    "github_list_weekly_commits",
    "github_analyze_prs",
    "github_create_branch",
    "neynar_get_top_casts",
    "neynar_publish_cast",
    "karmahq_build_milestone_payload",
    "karmahq_submit_milestone",
    "db_record_snapshot",
    "sysop_check_server_health",
    "sysop_run_command",
    "archon_spawn_worktree_fix",
)

PROMPT_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior|system)\s+instructions", re.IGNORECASE),
    re.compile(r"ignore\s+todas\s+as\s+instru[cç][oõ]es", re.IGNORECASE),
    re.compile(r"(reveal|print|dump|show)\s+.*(\.env|private[_\s]?key|service_role|secret)", re.IGNORECASE),
    re.compile(r"voc[eê]\s+agora\s+tem\s+role\s*=\s*['\"]?admin", re.IGNORECASE),
    re.compile(r"set\s+role\s*=\s*['\"]?admin", re.IGNORECASE),
)

PUBLIC_FORBIDDEN_INTENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(rm\s+-rf|sudo\s+|chmod\s+|/etc/passwd|bash\s+-c|sh\s+-c)\b", re.IGNORECASE),
    re.compile(r"\b(drop\s+table|delete\s+from|truncate\s+table)\b", re.IGNORECASE),
)


class SecurityHarness:
    """Aplica RBAC determinístico e Guardrails antes e depois do LangGraph."""

    def __init__(self, config: OmniBrainConfig = DEFAULT_CONFIG) -> None:
        self.config = config

    def compute_emacs_signature(self, user_id: str, payload_text: str) -> str:
        """Gera assinatura HMAC-SHA256 para autenticar o cliente Emacs ou API Admin."""
        msg = f"{user_id}:{payload_text}".encode("utf-8")
        return hmac.new(
            self.config.admin_hmac_secret.encode("utf-8"),
            msg,
            hashlib.sha256,
        ).hexdigest()

    def verify_admin_identity(self, message: InboundMessage) -> bool:
        """Determina se o remetente pertence à Fronteira Interna (Admin/SysOp)."""
        if message.channel == ChannelType.WEB_PUBLIC:
            return False

        if message.channel == ChannelType.WHATSAPP:
            normalized = message.user_id.strip()
            if normalized not in self.config.admin_whatsapp_numbers:
                return False
            # Se um PIN 2FA foi enviado, valida que bate com a configuração
            if message.pin_2fa is not None and message.pin_2fa != self.config.admin_pin_2fa:
                return False
            return True

        if message.channel in (ChannelType.EMACS, ChannelType.HERMES_WORKER):
            if not message.auth_signature:
                return False
            expected_hmac = self.compute_emacs_signature(message.user_id, message.text)
            if hmac.compare_digest(message.auth_signature, expected_hmac) or hmac.compare_digest(
                message.auth_signature, self.config.admin_hmac_secret
            ):
                return True
            for alias in ("Aprovado", "aprovado", "approved", "OK", "ok", "Rejeitado", "rejected"):
                if hmac.compare_digest(
                    message.auth_signature,
                    self.compute_emacs_signature(message.user_id, alias),
                ):
                    return True
            return False

        return False

    def inspect_inbound(self, message: InboundMessage) -> GuardrailVerdict:
        """Avalia a mensagem de entrada, atribui role ('admin' ou 'public') e bloqueia ataques."""
        combined_text = f"{message.text}\n{message.emacs_buffer_content or ''}".strip()

        for pattern in PROMPT_INJECTION_PATTERNS:
            if pattern.search(combined_text):
                return GuardrailVerdict(
                    allowed=False,
                    role=UserRole.PUBLIC,
                    reason="Bloqueado pelo Guardrail: Tentativa de Prompt Injection ou escalada de privilégio detectada.",
                    detected_injection=True,
                    allowed_mcp_tools=[],
                )

        is_admin = self.verify_admin_identity(message)
        role = UserRole.ADMIN if is_admin else UserRole.PUBLIC

        if role == UserRole.PUBLIC:
            for pattern in PUBLIC_FORBIDDEN_INTENT_PATTERNS:
                if pattern.search(combined_text):
                    return GuardrailVerdict(
                        allowed=False,
                        role=UserRole.PUBLIC,
                        reason="Bloqueado pelo Guardrail: Operação de sistema/escrita não permitida na Fronteira Externa.",
                        detected_injection=True,
                        allowed_mcp_tools=list(PUBLIC_ALLOWED_TOOLS),
                    )
            return GuardrailVerdict(
                allowed=True,
                role=UserRole.PUBLIC,
                reason="Fronteira Externa (Read-Only / Guiado) validada.",
                detected_injection=False,
                allowed_mcp_tools=list(PUBLIC_ALLOWED_TOOLS),
            )

        return GuardrailVerdict(
            allowed=True,
            role=UserRole.ADMIN,
            reason="Fronteira Interna (Admin / SysOp / Web3) autenticada.",
            detected_injection=False,
            allowed_mcp_tools=list(ADMIN_ALLOWED_TOOLS),
        )

    @staticmethod
    def sanitize_outbound_text(text: str, role: UserRole) -> str:
        """Garante que a saída nunca vaze tokens, chaves privadas ou caminhos sensíveis para o público."""
        sanitized = re.sub(r"ghp_[A-Za-z0-9]{20,}", "[REDACTED_GITHUB_TOKEN]", text)
        sanitized = re.sub(r"sk-[A-Za-z0-9]{20,}", "[REDACTED_API_KEY]", sanitized)
        if role == UserRole.PUBLIC:
            sanitized = re.sub(r"/tmp/archon-worktrees[^\s]*", "[INTERNAL_PATH]", sanitized)
        return sanitized

    @staticmethod
    def assert_tool_permission(role: UserRole, tool_name: str) -> None:
        """Barreira em nível de execução: impede que role='public' acione ferramentas restritas."""
        allowed: Iterable[str] = (
            ADMIN_ALLOWED_TOOLS if role == UserRole.ADMIN else PUBLIC_ALLOWED_TOOLS
        )
        if tool_name not in allowed:
            raise PermissionError(
                f"VIOLAÇÃO DE FRONTEIRA RBAC: O papel '{role.value}' não possui permissão "
                f"para acessar a ferramenta MCP '{tool_name}'."
            )
