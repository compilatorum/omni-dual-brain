"""Registro Central de Ferramentas MCP com Isolamento por Papel (Public vs. Admin)."""

from __future__ import annotations

from typing import Any, Callable

from omni_brain.context.graphify_indexer import GraphifyKnowledgeIndex
from omni_brain.context.supabase_store import SupabaseHybridStore
from omni_brain.harness.rbac_guardrail import (
    ADMIN_ALLOWED_TOOLS,
    PUBLIC_ALLOWED_TOOLS,
    SecurityHarness,
)
from omni_brain.mcp_servers.github_mcp import GitHubMCPServer
from omni_brain.mcp_servers.karmahq_mcp import KarmaHQMCPServer
from omni_brain.mcp_servers.neynar_mcp import NeynarFarcasterMCPServer
from omni_brain.mcp_servers.sysop_archon_mcp import SysOpArchonMCPServer
from omni_brain.schemas.models import UserRole


class MCPToolRegistry:
    """Conecta todos os servidores MCP ao LangGraph respeitando o isolamento de fronteiras."""

    def __init__(
        self,
        *,
        graphify: GraphifyKnowledgeIndex | None = None,
        supabase: SupabaseHybridStore | None = None,
        github: GitHubMCPServer | None = None,
        neynar: NeynarFarcasterMCPServer | None = None,
        karmahq: KarmaHQMCPServer | None = None,
        sysop: SysOpArchonMCPServer | None = None,
    ) -> None:
        self.graphify = graphify or GraphifyKnowledgeIndex()
        self.supabase = supabase or SupabaseHybridStore()
        self.github = github or GitHubMCPServer()
        self.neynar = neynar or NeynarFarcasterMCPServer()
        self.karmahq = karmahq or KarmaHQMCPServer()
        self.sysop = sysop or SysOpArchonMCPServer()

        self._tools: dict[str, Callable[..., Any]] = {
            # Ferramentas Read-Only (Fronteira Externa & Interna)
            "graphify_search_docs": lambda **kw: self.graphify.search(
                query=str(kw.get("query", "")), top_k=int(kw.get("top_k", 2))
            ),
            "db_query_public_metrics": lambda **kw: self.supabase.get_latest_public_metrics(),
            "github_get_public_status": lambda **kw: self.github.get_public_status(
                repo=kw.get("repo")
            ),
            "neynar_get_public_metrics": lambda **kw: self.neynar.get_public_metrics(),
            "karmahq_get_grant_milestones": lambda **kw: self.karmahq.get_grant_milestones(),
            # Ferramentas Exclusivas da Fronteira Interna (role == 'admin')
            "github_list_weekly_commits": lambda **kw: self.github.list_weekly_commits(
                repo=kw.get("repo")
            ),
            "github_analyze_prs": lambda **kw: self.github.analyze_prs(repo=kw.get("repo")),
            "neynar_get_top_casts": lambda **kw: self.neynar.get_top_casts(
                limit=int(kw.get("limit", 5))
            ),
            "neynar_publish_cast": lambda **kw: self.neynar.publish_cast(
                text=str(kw["text"]), channel_id=str(kw.get("channel_id", "sovereign-dev"))
            ),
            "karmahq_build_milestone_payload": lambda **kw: self.karmahq.build_milestone_payload(
                github_repo=str(kw.get("github_repo", self.github.default_repo)),
                commits=kw["commits"],
                casts=kw["casts"],
                reporting_period=str(kw.get("reporting_period", "2026-W46")),
            ),
            "karmahq_submit_milestone": lambda **kw: self.karmahq.submit_milestone(
                payload=kw["payload"]
            ),
            "db_record_snapshot": lambda **kw: self.supabase.record_metric_snapshot(
                source=str(kw["source"]),
                project_slug=str(kw["project_slug"]),
                metrics=dict(kw.get("metrics", {})),
            ),
            "sysop_check_server_health": lambda **kw: self.sysop.check_server_health(
                role=kw["role"]
            ),
            "sysop_run_command": lambda **kw: self.sysop.run_diagnostic_command(
                role=kw["role"], command=str(kw["command"])
            ),
            "archon_spawn_worktree_fix": lambda **kw: self.sysop.spawn_archon_worktree_fix(
                role=kw["role"],
                issue_summary=str(kw["issue_summary"]),
                target_node_or_module=str(
                    kw.get("target_node_or_module", "src/omni_brain/graph/nodes.py")
                ),
            ),
        }

    def list_tools_for_role(self, role: UserRole) -> list[str]:
        """Retorna apenas os nomes das ferramentas MCP visíveis para o papel atual."""
        return list(ADMIN_ALLOWED_TOOLS if role == UserRole.ADMIN else PUBLIC_ALLOWED_TOOLS)

    def invoke(self, role: UserRole, tool_name: str, **kwargs: Any) -> Any:
        """Executa uma ferramenta MCP após dupla verificação de permissão RBAC."""
        SecurityHarness.assert_tool_permission(role, tool_name)
        handler = self._tools.get(tool_name)
        if handler is None:
            raise KeyError(f"Ferramenta MCP desconhecida: {tool_name}")
        if tool_name.startswith(("sysop_", "archon_")):
            kwargs["role"] = role
        return handler(**kwargs)
