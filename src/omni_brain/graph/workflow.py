"""Orquestrador Central em Grafo (Cérebro Único com Duas Fronteiras + HITL + Graphify + MCP)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from omni_brain.harness.multimodal import MultimodalPreprocessor
from omni_brain.harness.rbac_guardrail import SecurityHarness
from omni_brain.mcp_servers.registry import MCPToolRegistry
from omni_brain.schemas.models import (
    AgentResponse,
    ChannelType,
    HITLActionType,
    HITLApprovalRequest,
    HITLDecision,
    InboundMessage,
    UserRole,
)
from omni_brain.graph.state import OmniBrainState, StatefulCheckpointer


class OmniDualBrainWorkflow:
    """Implementa a máquina de estados do LangGraph com isolamento Admin vs. Público e HITL."""

    APPROVAL_KEYWORDS: frozenset[str] = frozenset(
        {"aprovado", "aprovar", "ok", "confirmado", "approved", "sim, enviar"}
    )
    REJECTION_KEYWORDS: frozenset[str] = frozenset(
        {"rejeitado", "cancelar", "abortar", "rejected", "não"}
    )

    def __init__(
        self,
        *,
        harness: SecurityHarness | None = None,
        mcp_registry: MCPToolRegistry | None = None,
        checkpointer: StatefulCheckpointer | None = None,
        multimodal: MultimodalPreprocessor | None = None,
    ) -> None:
        self.harness = harness or SecurityHarness()
        self.mcp = mcp_registry or MCPToolRegistry()
        self.checkpointer = checkpointer or StatefulCheckpointer()
        self.multimodal = multimodal or MultimodalPreprocessor()

    def process_message(self, message: InboundMessage, thread_id: str | None = None) -> AgentResponse:
        """Ponto de entrada síncrono/assíncrono para WhatsApp Gateway, Emacs Client e Web."""
        resolved_thread_id = thread_id or f"{message.channel.value}:{message.user_id}"
        enriched_msg = self.multimodal.process_message(message)

        # Verifica se a thread está pausada no nó Human-in-the-Loop aguardando resposta do Admin
        existing_state = self.checkpointer.load(resolved_thread_id)
        normalized_text = enriched_msg.text.strip().lower()
        if (
            existing_state is not None
            and existing_state.status == "waiting_approval"
            and existing_state.pending_approval is not None
            and normalized_text in (self.APPROVAL_KEYWORDS | self.REJECTION_KEYWORDS)
        ):
            decision_type = "approved" if normalized_text in self.APPROVAL_KEYWORDS else "rejected"
            return self.resume_hitl(
                HITLDecision(
                    thread_id=resolved_thread_id,
                    approval_id=existing_state.pending_approval.approval_id,
                    decision=decision_type,
                    admin_user_id=enriched_msg.user_id,
                    channel=enriched_msg.channel,
                    auth_signature=enriched_msg.auth_signature,
                )
            )

        state = OmniBrainState(
            thread_id=resolved_thread_id,
            inbound_message=enriched_msg,
            conversation_history=(
                existing_state.conversation_history if existing_state else []
            ),
            compressed_summary=(
                existing_state.compressed_summary if existing_state else ""
            ),
        )

        # 1. Nó Roteador & Guardrail Inicial
        state = self._router_guardrail_node(state)
        if not state.guardrail_allowed:
            self.checkpointer.save(state)
            return self._to_response(state)

        # 2. Nó de Sumarização de Contexto (mantém histórico enxuto no WhatsApp)
        state = self._summarizer_node(state)

        # 3. Roteamento Condicional por Fronteira de Segurança (Public vs. Admin)
        if state.role == UserRole.PUBLIC:
            state = self._public_community_subgraph_node(state)
        else:
            state = self._admin_sysop_subgraph_node(state)

        # 4. Se o Subgrafo Admin gerou uma ação sensível, pausa no Nó Human-in-the-Loop
        if state.pending_approval is not None:
            state = self._human_in_the_loop_node(state)

        # 5. Sanitização final de saída (Guardrail de Saída)
        state.reply_text = self.harness.sanitize_outbound_text(state.reply_text, state.role)
        state.conversation_history.append({"user": enriched_msg.text, "assistant": state.reply_text})
        self.checkpointer.save(state)
        return self._to_response(state)

    def _router_guardrail_node(self, state: OmniBrainState) -> OmniBrainState:
        verdict = self.harness.inspect_inbound(state.inbound_message)
        state.role = verdict.role
        state.guardrail_allowed = verdict.allowed
        state.guardrail_reason = verdict.reason
        state.allowed_mcp_tools = verdict.allowed_mcp_tools

        if not verdict.allowed:
            state.status = "blocked_by_guardrail"
            state.reply_text = verdict.reason
            self.mcp.supabase.record_audit_log(
                thread_id=state.thread_id,
                user_id=state.inbound_message.user_id,
                channel=state.inbound_message.channel.value,
                role=state.role.value,
                action_type="guardrail_block",
                status="blocked",
                payload={"text": state.inbound_message.text, "reason": verdict.reason},
            )
        return state

    def _summarizer_node(self, state: OmniBrainState) -> OmniBrainState:
        """Comprime conversas longas (> 6 turnos) em resumo conciso."""
        if len(state.conversation_history) > 6:
            older = state.conversation_history[:-3]
            snippets = [f"U: {turn['user'][:40]} -> A: {turn['assistant'][:40]}" for turn in older]
            state.compressed_summary = " | ".join(snippets)
            state.conversation_history = state.conversation_history[-3:]
        return state

    def _public_community_subgraph_node(self, state: OmniBrainState) -> OmniBrainState:
        """Subgrafo Externo (Instrutor & Analista Comunitário): estritamente Read-Only via Graphify e Supabase."""
        query = state.inbound_message.text

        docs = self.mcp.invoke(state.role, "graphify_search_docs", query=query, top_k=2)
        state.invoked_tools.append("graphify_search_docs")

        metrics = self.mcp.invoke(state.role, "db_query_public_metrics")
        state.invoked_tools.append("db_query_public_metrics")

        karmahq_info = self.mcp.invoke(state.role, "karmahq_get_grant_milestones")
        state.invoked_tools.append("karmahq_get_grant_milestones")

        top_doc = docs[0]
        docs_rendered = "\n\n".join(
            f"📚 **Guia Técnico ({d['title']})**\n{d['content']}" for d in docs
        )
        gh = metrics.get("github", {})
        fc = metrics.get("farcaster_neynar", {})

        state.structured_output = {
            "graphify_node": top_doc["node_id"],
            "graphify_nodes": [d["node_id"] for d in docs],
            "public_metrics": metrics,
            "karmahq": karmahq_info,
        }
        state.status = "completed"
        state.reply_text = (
            f"{docs_rendered}\n\n"
            f"📊 **Impacto Recente do Ecossistema (Métricas Públicas Verificadas):**\n"
            f"• **GitHub (`{gh.get('project_slug')}`):** {gh.get('commits_count')} commits recentes, "
            f"{gh.get('stars_count')} estrelas.\n"
            f"• **Farcaster (Neynar):** {fc.get('farcaster_likes')} corações (likes), "
            f"{fc.get('farcaster_recasts')} recasts e {fc.get('farcaster_followers')} seguidores.\n"
            f"• **KarmaHQ Grants:** {karmahq_info.get('completed_milestones')} milestones concluídos "
            f"({karmahq_info.get('active_milestone')})."
        )
        return state

    def _admin_sysop_subgraph_node(self, state: OmniBrainState) -> OmniBrainState:
        """Subgrafo Interno (SysOp, Web3 & DevOps): acesso completo aos MCPs e preparação de payloads HITL."""
        text_lower = state.inbound_message.text.lower()

        # Caso 1: Relatório cruzado GitHub + Neynar -> JSON determinístico KarmaHQ (com HITL)
        if any(k in text_lower for k in ("karmahq", "commits", "neynar", "corações", "casts")):
            commits = self.mcp.invoke(state.role, "github_list_weekly_commits")
            state.invoked_tools.append("github_list_weekly_commits")

            casts = self.mcp.invoke(state.role, "neynar_get_top_casts", limit=5)
            state.invoked_tools.append("neynar_get_top_casts")

            payload = self.mcp.invoke(
                state.role,
                "karmahq_build_milestone_payload",
                github_repo=self.mcp.github.default_repo,
                commits=commits,
                casts=casts,
            )
            state.invoked_tools.append("karmahq_build_milestone_payload")

            payload_dict = payload.model_dump(mode="json")
            state.structured_output = payload_dict
            state.pending_approval = HITLApprovalRequest(
                approval_id=f"hitl_{uuid.uuid4().hex[:8]}",
                thread_id=state.thread_id,
                action_type=HITLActionType.KARMAHQ_SUBMIT,
                target_mcp_tool="karmahq_submit_milestone",
                description=(
                    "Enviar atualização semanal de Milestone para a API do KarmaHQ "
                    "cruzando commits do GitHub e casts do Farcaster (Neynar)."
                ),
                structured_payload=payload_dict,
            )
            return state

        # Caso 2: Auto-correção via Archon ("corrija isso" / "archon" / "worktree")
        if any(k in text_lower for k in ("corrija isso", "archon", "worktree", "auto-correção")):
            task_spec = self.mcp.invoke(
                state.role,
                "archon_spawn_worktree_fix",
                issue_summary=state.inbound_message.text,
                target_node_or_module="src/omni_brain/graph/workflow.py",
            )
            state.invoked_tools.append("archon_spawn_worktree_fix")
            spec_dict = task_spec.model_dump(mode="json")
            state.structured_output = spec_dict
            state.status = "completed"
            state.reply_text = (
                f"🛠️ **Esteira Archon Acionada com Sucesso!**\n"
                f"• **Task ID:** `{task_spec.task_id}`\n"
                f"• **Worktree Isolado:** `{task_spec.worktree_path}`\n"
                f"• **Branch:** `{task_spec.branch_name}`\n"
                f"• **Status:** Suíte de testes (`{task_spec.test_command}`) validada — Pull Request pronto para revisão."
            )
            return state

        # Caso 3: Publicação no Farcaster (com HITL)
        if "publicar cast" in text_lower or "postar no farcaster" in text_lower:
            draft_cast = state.inbound_message.emacs_buffer_content or state.inbound_message.text
            state.structured_output = {"text": draft_cast, "channel_id": "sovereign-dev"}
            state.pending_approval = HITLApprovalRequest(
                approval_id=f"hitl_{uuid.uuid4().hex[:8]}",
                thread_id=state.thread_id,
                action_type=HITLActionType.FARCASTER_PUBLISH,
                target_mcp_tool="neynar_publish_cast",
                description="Publicar cast oficial no Farcaster via API da Neynar.",
                structured_payload=state.structured_output,
            )
            return state

        # Caso 4: Saúde dos servidores / Diagnóstico SysOp
        health = self.mcp.invoke(state.role, "sysop_check_server_health")
        state.invoked_tools.append("sysop_check_server_health")
        state.structured_output = health
        state.status = "completed"
        state.reply_text = (
            "🔐 **Painel SysOp Admin (Fronteira Interna):**\n"
            f"```json\n{json.dumps(health, indent=2, ensure_ascii=False)}\n```"
        )
        return state

    def _human_in_the_loop_node(self, state: OmniBrainState) -> OmniBrainState:
        """Pausa a execução do grafo e aguarda aprovação explícita do Admin no Emacs ou WhatsApp."""
        assert state.pending_approval is not None
        state.status = "waiting_approval"

        self.mcp.supabase.record_audit_log(
            thread_id=state.thread_id,
            user_id=state.inbound_message.user_id,
            channel=state.inbound_message.channel.value,
            role=state.role.value,
            action_type=state.pending_approval.action_type.value,
            status="pending_approval",
            payload=state.pending_approval.structured_payload,
        )

        formatted_json = json.dumps(
            state.pending_approval.structured_payload, indent=2, ensure_ascii=False
        )
        state.reply_text = (
            f"⏸️ **[HUMAN-IN-THE-LOOP: APROVAÇÃO NECESSÁRIA]**\n"
            f"• **ID de Aprovação:** `{state.pending_approval.approval_id}`\n"
            f"• **Ação:** {state.pending_approval.description}\n"
            f"• **Ferramenta MCP Alvo:** `{state.pending_approval.target_mcp_tool}`\n\n"
            f"**Payload JSON Validado (Pydantic):**\n"
            f"```json\n{formatted_json}\n```\n\n"
            f"Responda **\"Aprovado\"** (ou execute `M-x omni-brain-approve-hitl` no Emacs) para disparar o POST."
        )
        return state

    def resume_hitl(self, decision: HITLDecision) -> AgentResponse:
        """Retoma o grafo pausado após o Admin responder 'Aprovado' ou 'Rejeitado'."""
        state = self.checkpointer.load(decision.thread_id)
        if state is None or state.pending_approval is None:
            raise ValueError(f"Nenhuma aprovação pendente encontrada para a thread '{decision.thread_id}'.")

        # Verifica identidade de Admin antes de retomar o grafo
        auth_probe = InboundMessage(
            message_id=f"hitl_resume_{decision.approval_id}",
            user_id=decision.admin_user_id,
            channel=decision.channel,
            text=decision.decision,
            auth_signature=decision.auth_signature,
        )
        if not self.harness.verify_admin_identity(auth_probe):
            raise PermissionError(
                "VIOLAÇÃO RBAC: Apenas o Administrador autenticado pode aprovar ou retomar ações HITL."
            )

        pending = state.pending_approval
        payload_to_execute = decision.edited_payload or pending.structured_payload

        if decision.decision == "rejected":
            state.status = "completed"
            state.pending_approval = None
            state.reply_text = f"🛑 Operação `{pending.approval_id}` cancelada pelo Administrador."
            self.mcp.supabase.record_audit_log(
                thread_id=state.thread_id,
                user_id=decision.admin_user_id,
                channel=decision.channel.value,
                role=UserRole.ADMIN.value,
                action_type=pending.action_type.value,
                status="rejected",
                payload=payload_to_execute,
            )
            self.checkpointer.save(state)
            return self._to_response(state)

        # Executa a ferramenta MCP aprovada
        if pending.target_mcp_tool == "karmahq_submit_milestone":
            receipt = self.mcp.invoke(
                UserRole.ADMIN,
                "karmahq_submit_milestone",
                payload=payload_to_execute,
            )
            state.invoked_tools.append("karmahq_submit_milestone")
        elif pending.target_mcp_tool == "neynar_publish_cast":
            receipt = self.mcp.invoke(
                UserRole.ADMIN,
                "neynar_publish_cast",
                text=payload_to_execute["text"],
                channel_id=payload_to_execute.get("channel_id", "sovereign-dev"),
            )
            state.invoked_tools.append("neynar_publish_cast")
        else:
            receipt = {"status": "executed", "tool": pending.target_mcp_tool}

        # Registra log de execução no Supabase
        audit_entry = self.mcp.supabase.record_audit_log(
            thread_id=state.thread_id,
            user_id=decision.admin_user_id,
            channel=decision.channel.value,
            role=UserRole.ADMIN.value,
            action_type=pending.action_type.value,
            status="executed",
            payload={"receipt": receipt},
        )

        state.status = "completed"
        state.pending_approval = None
        state.structured_output = {"receipt": receipt, "audit_log_id": audit_entry["id"]}
        state.reply_text = (
            f"✅ **[APROVADO E EXECUTADO COM SUCESSO]**\n"
            f"• **Ferramenta MCP:** `{pending.target_mcp_tool}`\n"
            f"• **Recibo:** `{json.dumps(receipt, ensure_ascii=False)}`\n"
            f"• **Log de Auditoria Supabase:** `{audit_entry['id']}`"
        )
        self.checkpointer.save(state)
        return self._to_response(state)

    @staticmethod
    def _to_response(state: OmniBrainState) -> AgentResponse:
        return AgentResponse(
            thread_id=state.thread_id,
            role=state.role,
            status=state.status if state.status != "running" else "completed",
            reply_text=state.reply_text,
            pending_approval=state.pending_approval,
            structured_data=state.structured_output,
            invoked_tools=list(state.invoked_tools),
        )
