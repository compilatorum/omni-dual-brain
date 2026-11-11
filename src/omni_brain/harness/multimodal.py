"""Pré-processador Multimodal do Harness (Transcrição de Áudio Whisper e Visão para Imagens)."""

from __future__ import annotations

from omni_brain.schemas.models import InboundMessage, MediaType, MultimodalAttachment


class MultimodalPreprocessor:
    """Converte áudios de WhatsApp e imagens anexadas em texto estruturado antes de entrar no grafo."""

    def __init__(self, whisper_transcriber=None, vision_describer=None) -> None:
        self._whisper = whisper_transcriber
        self._vision = vision_describer

    def process_message(self, message: InboundMessage) -> InboundMessage:
        """Enriquece o texto da mensagem com transcrições de áudio e descrições visuais."""
        if not message.attachments:
            return message

        enriched_segments: list[str] = []
        if message.text.strip():
            enriched_segments.append(message.text.strip())

        processed_attachments: list[MultimodalAttachment] = []
        for attachment in message.attachments:
            transcript = attachment.transcript_or_caption
            if attachment.media_type == MediaType.AUDIO and not transcript:
                transcript = (
                    self._whisper(attachment)
                    if callable(self._whisper)
                    else f"[Transcrição Whisper de Áudio ({attachment.media_url or 'inline'})]"
                )
            elif attachment.media_type == MediaType.IMAGE and not transcript:
                transcript = (
                    self._vision(attachment)
                    if callable(self._vision)
                    else f"[Descrição Visual de Imagem ({attachment.media_url or 'inline'})]"
                )

            updated = attachment.model_copy(update={"transcript_or_caption": transcript})
            processed_attachments.append(updated)
            if transcript:
                tag = "ÁUDIO TRANSCRITO" if attachment.media_type == MediaType.AUDIO else "IMAGEM ANALISADA"
                enriched_segments.append(f"[{tag}]: {transcript}")

        return message.model_copy(
            update={
                "text": "\n".join(enriched_segments),
                "attachments": processed_attachments,
            }
        )
