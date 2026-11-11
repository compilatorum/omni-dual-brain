"""MCP Server: GitHub (Status Público, Commits da Semana, Análise de PRs e Branches)."""

from __future__ import annotations

from typing import Any

from omni_brain.config import DEFAULT_CONFIG
from omni_brain.schemas.models import GitHubCommitSummary


class GitHubMCPServer:
    """Servidor MCP modular para operações de leitura e engenharia no GitHub."""

    def __init__(self, default_repo: str = DEFAULT_CONFIG.github_default_repo) -> None:
        self.default_repo = default_repo
        self._weekly_commits: list[GitHubCommitSummary] = [
            GitHubCommitSummary(
                sha="a1b2c3d4e5f601",
                author="sukata",
                message="feat(omni-graph): add Cytoscape universal WebSocket adapter and OmniState",
                committed_at="2026-11-09T16:40:00Z",
                files_changed=6,
            ),
            GitHubCommitSummary(
                sha="f9e8d7c6b5a402",
                author="sukata",
                message="feat(rbac): enforce dual security boundary between WhatsApp public and Emacs admin",
                committed_at="2026-11-10T19:15:00Z",
                files_changed=8,
            ),
            GitHubCommitSummary(
                sha="778899aabbcc03",
                author="sukata",
                message="fix(scheduler): enforce ISO-8601 date parser in booking and milestone flow",
                committed_at="2026-11-11T11:20:00Z",
                files_changed=3,
            ),
        ]

    def get_public_status(self, repo: str | None = None) -> dict[str, Any]:
        target = repo or self.default_repo
        return {
            "repo": target,
            "visibility": "public",
            "stars": 142,
            "open_issues": 4,
            "open_prs": 2,
            "latest_release": "v1.4.0-sovereign",
            "weekly_commits_count": len(self._weekly_commits),
        }

    def list_weekly_commits(self, repo: str | None = None) -> list[GitHubCommitSummary]:
        _ = repo or self.default_repo
        return list(self._weekly_commits)

    def analyze_prs(self, repo: str | None = None) -> list[dict[str, Any]]:
        target = repo or self.default_repo
        return [
            {
                "pr_number": 42,
                "repo": target,
                "title": "feat: integrate Sparklin Notes RAG with Graphify decay score",
                "ci_status": "passing",
                "review_state": "approved",
            }
        ]
