"""Adaptador 100% Oficial e Autorizado: Meta WhatsApp Cloud API (Graph API v21.0 - Zero Risco de Ban)."""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

import httpx

from omni_brain.schemas.models import (
    ChannelType,
    InboundMessage,
    MediaType,
    MultimodalAttachment,
)


class MetaWhatsAppCloudAdapter:
    """Conector oficial da Meta Cloud API (`graph.facebook.com`).

    Vantagens:
    - 100% autorizado pela Meta (zero risco de banimento do seu número pessoal).
    - Fornece um número de teste gratuito oficial da Meta (+1 555...) no painel developers.facebook.com.
    - Conversas de Serviço (iniciadas pelo usuário dentro da janela de 24h) são gratuitas na Cloud API.
    """

    def __init__(
        self,
        *,
        access_token: str | None = None,
        phone_number_id: str | None = None,
        verify_token: str | None = None,
        app_secret: str | None = None,
        graph_api_version: str = "v21.0",
    ) -> None:
        self.access_token = access_token or os.getenv("META_CLOUD_API_TOKEN", "")
        self.phone_number_id = phone_number_id or os.getenv("META_PHONE_NUMBER_ID", "")
        self.verify_token = verify_token or os.getenv("META_WEBHOOK_VERIFY_TOKEN", "omni_meta_verify_token")
        self.app_secret = app_secret or os.getenv("META_APP_SECRET", "")
        self.graph_api_version = graph_api_version

    def verify_webhook_challenge(
        self,
        mode: str | None,
        token: str | None,
        challenge: str | None,
    ) -> str:
        """Valida o GET `hub.challenge` exigido pelo painel oficial da Meta Cloud API."""
        if mode == "subscribe" and token == self.verify_token and challenge is not None:
            return challenge
        raise PermissionError("Falha na verificação do Webhook Oficial da Meta (`hub.verify_token` inválido).")

    def verify_hub_signature(self, raw_body: bytes, signature_header: str | None) -> bool:
        """Valida o header `X-Hub-Signature-256` enviado pela Meta em cada webhook POST."""
        if not self.app_secret:
            return True
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        expected = "sha256=" + hmac.new(
            self.app_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature_header, expected)

    @staticmethod
    def parse_webhook_payload(payload: dict[str, Any]) -> list[InboundMessage]:
        """Extrai mensagens normalizadas do formato JSON oficial `whatsapp_business_account` da Meta."""
        extracted: list[InboundMessage] = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    msg_id = str(msg.get("id", "wamid.unknown"))
                    from_number = str(msg.get("from", ""))
                    if from_number and not from_number.startswith("+"):
                        from_number = f"+{from_number}"

                    msg_type = msg.get("type", "text")
                    text_body = ""
                    attachments: list[MultimodalAttachment] = []

                    if msg_type == "text":
                        text_body = str(msg.get("text", {}).get("body", ""))
                    elif msg_type == "audio":
                        audio_id = msg.get("audio", {}).get("id", "")
                        attachments.append(
                            MultimodalAttachment(
                                media_type=MediaType.AUDIO,
                                media_url=f"meta_media_id://{audio_id}",
                                mime_type=msg.get("audio", {}).get("mime_type", "audio/ogg"),
                            )
                        )
                    elif msg_type == "image":
                        image_id = msg.get("image", {}).get("id", "")
                        text_body = str(msg.get("image", {}).get("caption", ""))
                        attachments.append(
                            MultimodalAttachment(
                                media_type=MediaType.IMAGE,
                                media_url=f"meta_media_id://{image_id}",
                                mime_type=msg.get("image", {}).get("mime_type", "image/jpeg"),
                            )
                        )

                    extracted.append(
                        InboundMessage(
                            message_id=msg_id,
                            user_id=from_number,
                            channel=ChannelType.WHATSAPP,
                            text=text_body,
                            attachments=attachments,
                        )
                    )
        return extracted

    def send_text_message(self, to_phone_e164: str, text: str) -> dict[str, Any]:
        """Envia resposta pelo endpoint oficial `POST /{Phone-Number-ID}/messages` da Meta."""
        clean_recipient = to_phone_e164.lstrip("+")
        url = f"https://graph.facebook.com/{self.graph_api_version}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_recipient,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        if not self.access_token or not self.phone_number_id:
            return {
                "status": "dry_run_meta_cloud_api",
                "endpoint": url,
                "payload": payload,
            }

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()
