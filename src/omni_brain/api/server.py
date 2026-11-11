"""API Central Unificada (FastAPI + Controlador de Gateway para WhatsApp, Emacs e Frontend Web)."""

from __future__ import annotations

from typing import Any

from omni_brain.config import DEFAULT_CONFIG, OmniBrainConfig
from omni_brain.graph.workflow import OmniDualBrainWorkflow
from omni_brain.harness.debounce_buffer import WhatsAppDebounceBuffer
from omni_brain.schemas.models import (
    AgentResponse,
    ChannelType,
    HITLDecision,
    InboundMessage,
    UserRole,
)


class UnifiedGatewayController:
    """Controlador central da API Python consumido por WhatsApp Gateway, Emacs Client e Web."""

    def __init__(
        self,
        workflow: OmniDualBrainWorkflow | None = None,
        config: OmniBrainConfig = DEFAULT_CONFIG,
    ) -> None:
        self.config = config
        self.workflow = workflow or OmniDualBrainWorkflow()
        self.debounce = WhatsAppDebounceBuffer(
            debounce_seconds=config.whatsapp_debounce_seconds
        )
        self.dispatched_whatsapp_replies: list[AgentResponse] = []

    async def receive_whatsapp_webhook(
        self,
        message: InboundMessage,
        *,
        immediate_flush: bool = False,
    ) -> AgentResponse | None:
        """Recebe webhook do WhatsApp, aplica Debounce (Redis/Memória) e aciona o LangGraph."""
        user_key = f"{message.channel.value}:{message.user_id}"

        async def _on_flush(merged_msg: InboundMessage) -> None:
            resp = self.workflow.process_message(merged_msg)
            self.dispatched_whatsapp_replies.append(resp)

        await self.debounce.enqueue(message, _on_flush)
        if immediate_flush:
            merged = await self.debounce.flush_now(user_key)
            if merged is not None:
                resp = self.workflow.process_message(merged)
                self.dispatched_whatsapp_replies.append(resp)
                return resp
        return None

    def receive_emacs_command(
        self,
        *,
        user_id: str,
        command_text: str,
        auth_signature: str,
        buffer_name: str | None = None,
        buffer_content: str | None = None,
        thread_id: str | None = None,
    ) -> AgentResponse:
        """Endpoint síncrono/SSE para o cliente Emacs (`omni-brain.el`)."""
        msg = InboundMessage(
            message_id="emacs_cmd",
            user_id=user_id,
            channel=ChannelType.EMACS,
            text=command_text,
            auth_signature=auth_signature,
            emacs_buffer_name=buffer_name,
            emacs_buffer_content=buffer_content,
        )
        return self.workflow.process_message(msg, thread_id=thread_id)

    def submit_hitl_decision(self, decision: HITLDecision) -> AgentResponse:
        """Retoma o grafo pausado no nó Human-in-the-Loop."""
        return self.workflow.resume_hitl(decision)

    def get_public_dashboard_metrics(self) -> dict[str, Any]:
        """Endpoint Read-Only para o Frontend Web exibir dashboards de métricas."""
        return self.workflow.mcp.invoke(UserRole.PUBLIC, "db_query_public_metrics")


def create_fastapi_app(controller: UnifiedGatewayController | None = None) -> Any:
    """Cria a aplicação FastAPI caso o pacote `fastapi` esteja instalado no ambiente."""
    from fastapi import FastAPI, HTTPException

    ctrl = controller or UnifiedGatewayController()
    app = FastAPI(
        title="Omni Dual-Brain Unified API",
        version="1.0.0",
        description="Cérebro Único com Duas Fronteiras de Segurança (WhatsApp + Emacs + Web3 MCP)",
    )

    @app.post("/webhooks/whatsapp", response_model=AgentResponse)
    async def whatsapp_webhook(message: InboundMessage) -> AgentResponse:
        resp = await ctrl.receive_whatsapp_webhook(message, immediate_flush=True)
        if resp is None:
            raise HTTPException(status_code=202, detail="Mensagem agrupada no Debounce Buffer")
        return resp

    @app.post("/api/v1/emacs/command", response_model=AgentResponse)
    async def emacs_command(message: InboundMessage) -> AgentResponse:
        return ctrl.workflow.process_message(message)

    @app.post("/api/v1/hitl/decision", response_model=AgentResponse)
    async def hitl_decision(decision: HITLDecision) -> AgentResponse:
        return ctrl.submit_hitl_decision(decision)

    @app.get("/api/v1/metrics/dashboard")
    async def dashboard_metrics() -> dict[str, Any]:
        return ctrl.get_public_dashboard_metrics()

    return app
