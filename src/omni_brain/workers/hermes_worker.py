"""Worker Assíncrono Hermes / OpenClaw: Heartbeats, Coleta de Métricas e Alerta Proativo + Archon."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from omni_brain.config import DEFAULT_CONFIG, OmniBrainConfig
from omni_brain.graph.workflow import OmniDualBrainWorkflow
from omni_brain.schemas.models import (
    AgentResponse,
    ChannelType,
    InboundMessage,
    UserRole,
)


class HermesProactiveWorker:
    """Serviço isolado de background para rotinas proativas, heartbeats e monitoramento de falhas."""

    def __init__(
        self,
        workflow: OmniDualBrainWorkflow,
        config: OmniBrainConfig = DEFAULT_CONFIG,
    ) -> None:
        self.workflow = workflow
        self.config = config
        self.proactive_alerts_sent: list[dict[str, Any]] = []

    def run_metrics_heartbeat(self) -> dict[str, Any]:
        """Coleta métricas atualizadas da Neynar e GitHub e persiste snapshots no Supabase."""
        gh_status = self.workflow.mcp.invoke(UserRole.ADMIN, "github_get_public_status")
        fc_metrics = self.workflow.mcp.invoke(UserRole.ADMIN, "neynar_get_public_metrics")

        snap_gh = self.workflow.mcp.invoke(
            UserRole.ADMIN,
            "db_record_snapshot",
            source="github",
            project_slug=gh_status["repo"],
            metrics={
                "commits_count": gh_status["weekly_commits_count"],
                "stars_count": gh_status["stars"],
                "open_prs_count": gh_status["open_prs"],
            },
        )
        snap_fc = self.workflow.mcp.invoke(
            UserRole.ADMIN,
            "db_record_snapshot",
            source="neynar",
            project_slug="sovereign-omni",
            metrics={
                "farcaster_likes": fc_metrics["total_likes_week"],
                "farcaster_recasts": fc_metrics["total_recasts_week"],
                "farcaster_followers": fc_metrics["followers_count"],
            },
        )
        return {
            "heartbeat_at": datetime.now(timezone.utc).isoformat(),
            "github_snapshot": snap_gh,
            "neynar_snapshot": snap_fc,
        }

    def inspect_flow_anomalies(self, error_logs: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Detecta falhas recorrentes nos fluxos conversacionais e alerta o WhatsApp Admin."""
        if len(error_logs) < 3:
            return None

        admin_number = sorted(self.config.admin_whatsapp_numbers)[0]
        reason = error_logs[0].get("error", "erro de formato de data")
        flow_name = error_logs[0].get("flow", "agendamento")

        alert = {
            "to_admin_whatsapp": admin_number,
            "alert_text": (
                f"⚠️ [Hermes Monitor]: O fluxo de {flow_name} falhou {len(error_logs)} vezes hoje "
                f"por {reason}. Responda 'Corrija isso' para acionar o Archon."
            ),
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }
        self.proactive_alerts_sent.append(alert)
        return alert

    def handle_admin_autofix_reply(self, admin_whatsapp: str, reply_text: str) -> AgentResponse:
        """Recebe o 'Corrija isso' do Admin no WhatsApp e dispara o Archon via grafo interno."""
        msg = InboundMessage(
            message_id="hermes_autofix_trigger",
            user_id=admin_whatsapp,
            channel=ChannelType.WHATSAPP,
            text=reply_text,
        )
        return self.workflow.process_message(msg)
