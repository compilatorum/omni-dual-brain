"""Servidor HTTP Standalone + API REST em Tempo Real para o Console Web e Testes E2E Playwright."""

from __future__ import annotations

import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from omni_brain.api.server import UnifiedGatewayController
from omni_brain.config import DEFAULT_CONFIG
from omni_brain.schemas.models import (
    ChannelType,
    HITLDecision,
    InboundMessage,
    MediaType,
    MultimodalAttachment,
    UserRole,
)
from omni_brain.workers.hermes_worker import HermesProactiveWorker

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class OmniBrainRuntimeState:
    """Mantém a instância única do controlador, worker Hermes e histórico de eventos para a UI."""

    def __init__(self) -> None:
        self.controller = UnifiedGatewayController()
        self.hermes = HermesProactiveWorker(self.controller.workflow)
        self.whatsapp_history: list[dict[str, Any]] = []
        self.emacs_history: list[dict[str, Any]] = []

    def get_full_state(self) -> dict[str, Any]:
        wf = self.controller.workflow
        return {
            "public_metrics": self.controller.get_public_dashboard_metrics(),
            "karmahq_status": wf.mcp.karmahq.get_grant_milestones(),
            "mcp_tools": {
                "public": wf.mcp.list_tools_for_role(UserRole.PUBLIC),
                "admin": wf.mcp.list_tools_for_role(UserRole.ADMIN),
            },
            "audit_logs": wf.mcp.supabase.list_audit_logs(),
            "whatsapp_history": self.whatsapp_history,
            "emacs_history": self.emacs_history,
            "hermes_alerts": self.hermes.proactive_alerts_sent,
            "archon_tasks": [
                t.model_dump(mode="json") for t in wf.mcp.sysop._archon_tasks
            ],
            "karmahq_submissions": wf.mcp.karmahq._submitted_milestones,
            "readiness_matrix": [
                {
                    "component": "WhatsApp Connector (Baileys / Evolution API / WAHA)",
                    "current_mode": "SYNTHETIC_WEBHOOK_SIMULATOR",
                    "free_personal_whatsapp": True,
                    "requirement": "Container Docker WAHA ou Evolution API + pareamento QR Code no WhatsApp pessoal",
                },
                {
                    "component": "Fila de Debounce 3.5s (Redis -> Async Memory Fallback)",
                    "current_mode": "IN_MEMORY_ASYNC_BUFFER",
                    "free_personal_whatsapp": True,
                    "requirement": "Daemon Redis local (`redis-server`) conectado via REDIS_URL",
                },
                {
                    "component": "Transcrição Multimodal (Whisper Audio & Vision)",
                    "current_mode": "SYNTHETIC_TRANSCRIPT_ADAPTER",
                    "free_personal_whatsapp": True,
                    "requirement": "whisper.cpp / faster-whisper local ou chave Groq/OpenAI Whisper",
                },
                {
                    "component": "Banco Híbrido Supabase (PostgreSQL + pgvector)",
                    "current_mode": "IN_MEMORY_SEEDED_STORE",
                    "free_personal_whatsapp": True,
                    "requirement": "Executar sql/001_supabase_schema.sql no Supabase ou Postgres local",
                },
                {
                    "component": "Conectores MCP Web3 (GitHub, Neynar Farcaster, KarmaHQ)",
                    "current_mode": "SYNTHETIC_SNAPSHOT_SEED",
                    "free_personal_whatsapp": True,
                    "requirement": "Configurar GITHUB_TOKEN, NEYNAR_API_KEY e KARMAHQ_API_KEY no .env",
                },
            ],
        }


def create_http_server(host: str = "127.0.0.1", port: int = 8765) -> tuple[ThreadingHTTPServer, OmniBrainRuntimeState]:
    runtime = OmniBrainRuntimeState()

    class RequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return  # Silencia logs verbosos durante os testes E2E

        def _send_json(self, status_code: int, payload: Any) -> None:
            raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(raw)

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/index.html"):
                html_path = WEB_DIR / "dashboard.html"
                content = html_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

            if parsed.path == "/api/v1/state/full":
                self._send_json(200, runtime.get_full_state())
                return

            if parsed.path == "/api/v1/metrics/dashboard":
                self._send_json(200, runtime.controller.get_public_dashboard_metrics())
                return

            self._send_json(404, {"error": f"Rota não encontrada: {parsed.path}"})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            body = self._read_json_body()

            if parsed.path == "/webhooks/whatsapp/burst":
                # Simula o envio de múltiplos balões seguidos + áudio no WhatsApp passando pelo Debounce Buffer
                user_id = str(body.get("user_id", "+5521977776666"))
                bubbles: list[str] = list(
                    body.get(
                        "bubbles",
                        [
                            "Olá! Sou da comunidade.",
                            "Como posso integrar com o projeto Sovereign Omni Graph?",
                            "E qual foi o impacto recente no GitHub, Farcaster e KarmaHQ?",
                        ],
                    )
                )
                include_audio = bool(body.get("include_audio", True))

                async def _process_burst() -> Any:
                    resp = None
                    for i, text_bubble in enumerate(bubbles):
                        is_last = (i == len(bubbles) - 1) and not include_audio
                        msg = InboundMessage(
                            message_id=f"wamid.burst.{i+1}",
                            user_id=user_id,
                            channel=ChannelType.WHATSAPP,
                            text=text_bubble,
                        )
                        resp = await runtime.controller.receive_whatsapp_webhook(
                            msg, immediate_flush=is_last
                        )
                    if include_audio:
                        audio_msg = InboundMessage(
                            message_id="wamid.burst.audio",
                            user_id=user_id,
                            channel=ChannelType.WHATSAPP,
                            text="",
                            attachments=[
                                MultimodalAttachment(
                                    media_type=MediaType.AUDIO,
                                    media_url="https://cdn.whatsapp.net/voice_note_01.ogg",
                                    transcript_or_caption="Áudio transcrito via Whisper: também quero ver os milestones concluídos no KarmaHQ.",
                                )
                            ],
                        )
                        resp = await runtime.controller.receive_whatsapp_webhook(
                            audio_msg, immediate_flush=True
                        )
                    return resp

                final_resp = asyncio.run(_process_burst())
                resp_dict = final_resp.model_dump(mode="json") if final_resp else {}
                runtime.whatsapp_history.append(
                    {
                        "event": "Debounce Burst (3 balões + 1 Áudio Whisper -> 1 Execução LangGraph)",
                        "user_id": user_id,
                        "bubbles_count": len(bubbles) + (1 if include_audio else 0),
                        "response": resp_dict,
                    }
                )
                self._send_json(200, resp_dict)
                return

            if parsed.path == "/webhooks/whatsapp/single":
                user_id = str(body.get("user_id", "+5521900001111"))
                text = str(body.get("text", ""))
                msg = InboundMessage(
                    message_id="wamid.single.001",
                    user_id=user_id,
                    channel=ChannelType.WHATSAPP,
                    text=text,
                )
                resp = runtime.controller.workflow.process_message(msg)
                resp_dict = resp.model_dump(mode="json")
                runtime.whatsapp_history.append(
                    {
                        "event": "Mensagem WhatsApp Direta (Guardrail Check)",
                        "user_id": user_id,
                        "bubbles_count": 1,
                        "response": resp_dict,
                    }
                )
                self._send_json(200, resp_dict)
                return

            if parsed.path == "/api/v1/emacs/command":
                user_id = str(body.get("user_id", "sukata@emacs"))
                command_text = str(
                    body.get(
                        "command_text",
                        "Analise os commits da semana no GitHub e os casts com mais corações na Neynar, monte o JSON de atualização do KarmaHQ e me mande para revisar antes de enviar.",
                    )
                )
                thread_id = str(body.get("thread_id", "emacs:sukata-session-e2e"))
                signature = runtime.controller.workflow.harness.compute_emacs_signature(
                    user_id, command_text
                )
                resp = runtime.controller.receive_emacs_command(
                    user_id=user_id,
                    command_text=command_text,
                    auth_signature=signature,
                    buffer_name=str(body.get("buffer_name", "*Omni-Brain-Admin*")),
                    thread_id=thread_id,
                )
                resp_dict = resp.model_dump(mode="json")
                runtime.emacs_history.append(resp_dict)
                self._send_json(200, resp_dict)
                return

            if parsed.path == "/api/v1/hitl/decision":
                thread_id = str(body.get("thread_id", "emacs:sukata-session-e2e"))
                approval_id = str(body.get("approval_id", ""))
                decision_val = str(body.get("decision", "approved"))
                admin_user_id = str(body.get("admin_user_id", "sukata@emacs"))
                sig = runtime.controller.workflow.harness.compute_emacs_signature(
                    admin_user_id, decision_val
                )
                decision = HITLDecision(
                    thread_id=thread_id,
                    approval_id=approval_id,
                    decision="approved" if decision_val == "approved" else "rejected",
                    admin_user_id=admin_user_id,
                    channel=ChannelType.EMACS,
                    auth_signature=sig,
                )
                resp = runtime.controller.submit_hitl_decision(decision)
                resp_dict = resp.model_dump(mode="json")
                runtime.emacs_history.append(resp_dict)
                self._send_json(200, resp_dict)
                return

            if parsed.path == "/api/v1/hermes/trigger-anomaly":
                hb = runtime.hermes.run_metrics_heartbeat()
                alert = runtime.hermes.inspect_flow_anomalies(
                    [
                        {"flow": "agendamento", "error": "erro de formato de data ISO-8601"},
                        {"flow": "agendamento", "error": "erro de formato de data ISO-8601"},
                        {"flow": "agendamento", "error": "erro de formato de data ISO-8601"},
                    ]
                )
                self._send_json(200, {"heartbeat": hb, "alert": alert})
                return

            if parsed.path == "/api/v1/hermes/autofix":
                admin_phone = sorted(DEFAULT_CONFIG.admin_whatsapp_numbers)[0]
                reply_text = str(
                    body.get(
                        "reply_text",
                        "Corrija isso no fluxo de agendamento criando um git worktree isolado no Archon",
                    )
                )
                resp = runtime.hermes.handle_admin_autofix_reply(admin_phone, reply_text)
                self._send_json(200, resp.model_dump(mode="json"))
                return

            self._send_json(404, {"error": f"Rota POST não encontrada: {parsed.path}"})

    server = ThreadingHTTPServer((host, port), RequestHandler)
    return server, runtime
