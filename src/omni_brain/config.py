"""Configurações centrais e políticas de segurança RBAC do Omni Dual-Brain."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OmniBrainConfig:
    """Configuração imutável do Cérebro Único e suas duas fronteiras."""

    admin_whatsapp_numbers: frozenset[str] = field(
        default_factory=lambda: frozenset(
            num.strip()
            for num in os.getenv(
                "OMNI_ADMIN_WHATSAPP_NUMBERS",
                "+5531984353632,+553184353632,+5511999999999,+5511888888888",
            ).split(",")
            if num.strip()
        )
    )
    admin_hmac_secret: str = field(
        default_factory=lambda: os.getenv(
            "OMNI_ADMIN_HMAC_SECRET",
            "change-me-super-secret-hmac-key-for-emacs-and-internal-api",
        )
    )
    admin_pin_2fa: str = field(
        default_factory=lambda: os.getenv("OMNI_ADMIN_PIN_2FA", "7391")
    )
    whatsapp_debounce_seconds: float = field(
        default_factory=lambda: float(os.getenv("WHATSAPP_DEBOUNCE_SECONDS", "3.5"))
    )
    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    github_default_repo: str = field(
        default_factory=lambda: os.getenv(
            "GITHUB_DEFAULT_REPO", "compilatorum/sovereign-html-mockups"
        )
    )
    karmahq_project_uid: str = field(
        default_factory=lambda: os.getenv(
            "KARMAHQ_PROJECT_UID", "0xabc123def4567890"
        )
    )
    farcaster_fid: int = field(
        default_factory=lambda: int(os.getenv("FARCASTER_FID", "12345"))
    )
    archon_worktree_base_dir: str = field(
        default_factory=lambda: os.getenv(
            "ARCHON_WORKTREE_BASE_DIR", "/tmp/archon-worktrees"
        )
    )


DEFAULT_CONFIG = OmniBrainConfig()
