"""Fila de Debounce / Buffer para o WhatsApp (agrupa balões consecutivos em janela de 3-5s)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Awaitable, Callable

from omni_brain.schemas.models import InboundMessage, MultimodalAttachment


class WhatsAppDebounceBuffer:
    """Agrupa múltiplas mensagens enviadas em sequência rápida pelo mesmo usuário no WhatsApp.

    Em produção pode usar listas do Redis (`RPUSH` + `EXPIRE`) ou o buffer assíncrono em memória
    abaixo, evitando que 5 balões seguidos disparem 5 execuções paralelas do LangGraph.
    """

    def __init__(self, debounce_seconds: float = 3.5) -> None:
        self.debounce_seconds = debounce_seconds
        self._buffers: dict[str, list[InboundMessage]] = defaultdict(list)
        self._timers: dict[str, asyncio.Task[None]] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def enqueue(
        self,
        message: InboundMessage,
        on_flush: Callable[[InboundMessage], Awaitable[None]],
    ) -> None:
        """Adiciona uma mensagem ao buffer do usuário e reinicia o timer de debounce."""
        user_key = f"{message.channel.value}:{message.user_id}"
        async with self._locks[user_key]:
            self._buffers[user_key].append(message)
            existing_timer = self._timers.get(user_key)
            if existing_timer and not existing_timer.done():
                existing_timer.cancel()

            self._timers[user_key] = asyncio.create_task(
                self._wait_and_flush(user_key, on_flush)
            )

    async def _wait_and_flush(
        self,
        user_key: str,
        on_flush: Callable[[InboundMessage], Awaitable[None]],
    ) -> None:
        try:
            await asyncio.sleep(self.debounce_seconds)
        except asyncio.CancelledError:
            return

        merged = await self.flush_now(user_key)
        if merged is not None:
            await on_flush(merged)

    async def flush_now(self, user_key: str) -> InboundMessage | None:
        """Consolida todas as mensagens pendentes do usuário em um único InboundMessage."""
        async with self._locks[user_key]:
            messages = self._buffers.pop(user_key, [])
            timer = self._timers.pop(user_key, None)
            if timer and not timer.done() and timer is not asyncio.current_task():
                timer.cancel()

            if not messages:
                return None

            first = messages[0]
            last = messages[-1]
            combined_text = "\n".join(m.text.strip() for m in messages if m.text.strip())
            combined_attachments: list[MultimodalAttachment] = []
            for m in messages:
                combined_attachments.extend(m.attachments)

            return InboundMessage(
                message_id=f"{first.message_id}..{last.message_id}" if len(messages) > 1 else first.message_id,
                user_id=first.user_id,
                channel=first.channel,
                text=combined_text,
                attachments=combined_attachments,
                auth_signature=last.auth_signature or first.auth_signature,
                pin_2fa=last.pin_2fa or first.pin_2fa,
                emacs_buffer_name=last.emacs_buffer_name,
                emacs_buffer_content=last.emacs_buffer_content,
                timestamp=last.timestamp,
            )
