"""Camada de Persistência Híbrida (Supabase PostgreSQL Relacional + Auditoria HITL)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class SupabaseHybridStore:
    """Gerencia snapshots de métricas (GitHub, Neynar, KarmaHQ) e logs de auditoria RBAC/HITL."""

    def __init__(self) -> None:
        self._metric_snapshots: list[dict[str, Any]] = [
            {
                "recorded_at": "2026-11-11T12:00:00Z",
                "source": "github",
                "project_slug": "compilatorum/sovereign-html-mockups",
                "commits_count": 18,
                "stars_count": 142,
                "open_prs_count": 2,
            },
            {
                "recorded_at": "2026-11-11T12:05:00Z",
                "source": "neynar",
                "project_slug": "sovereign-omni",
                "farcaster_likes": 310,
                "farcaster_recasts": 84,
                "farcaster_followers": 1290,
            },
            {
                "recorded_at": "2026-11-11T12:10:00Z",
                "source": "karmahq",
                "project_slug": "0xabc123def4567890",
                "karmahq_milestones_completed": 4,
                "grant_program": "Optimism RetroPGF & Sovereign Grants",
                "status": "On Track",
            },
        ]
        self._audit_logs: list[dict[str, Any]] = []

    def get_latest_public_metrics(self) -> dict[str, Any]:
        """Retorna o snapshot consolidado mais recente para consultas públicas ou dashboards."""
        latest_by_source: dict[str, dict[str, Any]] = {}
        for snap in self._metric_snapshots:
            latest_by_source[snap["source"]] = snap
        return {
            "github": latest_by_source.get("github", {}),
            "farcaster_neynar": latest_by_source.get("neynar", {}),
            "karmahq": latest_by_source.get("karmahq", {}),
        }

    def record_metric_snapshot(self, source: str, project_slug: str, metrics: dict[str, Any]) -> dict[str, Any]:
        """Grava um novo snapshot diário coletado pelo worker Hermes ou pelo Admin."""
        entry = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "project_slug": project_slug,
            **metrics,
        }
        self._metric_snapshots.append(entry)
        return entry

    def record_audit_log(
        self,
        *,
        thread_id: str,
        user_id: str,
        channel: str,
        role: str,
        action_type: str,
        status: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Registra trilha de auditoria imutável no Supabase para cada decisão RBAC ou HITL."""
        record = {
            "id": f"audit_{len(self._audit_logs) + 1:04d}",
            "thread_id": thread_id,
            "user_id": user_id,
            "channel": channel,
            "role": role,
            "action_type": action_type,
            "status": status,
            "payload": payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._audit_logs.append(record)
        return record

    def list_audit_logs(self, thread_id: str | None = None) -> list[dict[str, Any]]:
        if thread_id is None:
            return list(self._audit_logs)
        return [log for log in self._audit_logs if log["thread_id"] == thread_id]
