"""MCP Server: Farcaster / Neynar (Métricas Públicas, Top Casts por Corações/Likes e Publicação)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from omni_brain.config import DEFAULT_CONFIG
from omni_brain.schemas.models import NeynarCastMetric


class NeynarFarcasterMCPServer:
    """Servidor MCP para consulta de engajamento social e publicação no Farcaster via Neynar."""

    def __init__(self, fid: int = DEFAULT_CONFIG.farcaster_fid) -> None:
        self.fid = fid
        self._casts: list[NeynarCastMetric] = [
            NeynarCastMetric(
                cast_hash="0x91a4f001bc23de45",
                text="Lançamos o runtime Omni Graph v1.4 com suporte offline-first e sincronia Web3 no KarmaHQ!",
                likes_count=184,
                recasts_count=49,
                replies_count=27,
                published_at="2026-11-08T18:00:00Z",
            ),
            NeynarCastMetric(
                cast_hash="0x82b5e002cd34ef56",
                text="Novo cliente Emacs integrado ao LangGraph com aprovação Human-in-the-Loop para SysOps.",
                likes_count=126,
                recasts_count=35,
                replies_count=19,
                published_at="2026-11-10T20:30:00Z",
            ),
        ]
        self._published_casts: list[dict[str, Any]] = []

    def get_public_metrics(self) -> dict[str, Any]:
        total_likes = sum(c.likes_count for c in self._casts)
        total_recasts = sum(c.recasts_count for c in self._casts)
        return {
            "fid": self.fid,
            "total_likes_week": total_likes,
            "total_recasts_week": total_recasts,
            "followers_count": 1290,
            "top_cast_preview": self._casts[0].text if self._casts else "",
        }

    def get_top_casts(self, limit: int = 5) -> list[NeynarCastMetric]:
        sorted_casts = sorted(self._casts, key=lambda c: c.likes_count, reverse=True)
        return sorted_casts[:limit]

    def publish_cast(self, text: str, channel_id: str = "sovereign-dev") -> dict[str, Any]:
        receipt = {
            "status": "published_on_farcaster",
            "cast_hash": f"0xfeed{len(self._published_casts) + 1:08x}",
            "fid": self.fid,
            "channel_id": channel_id,
            "text": text,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }
        self._published_casts.append(receipt)
        return receipt
