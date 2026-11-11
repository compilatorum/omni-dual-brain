"""Script de Inicialização do Servidor HTTP Omni Dual-Brain em Tempo Real (Porta 8765)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from omni_brain.api.http_server import create_http_server


def main() -> None:
    server, _runtime = create_http_server(host="127.0.0.1", port=8765)
    print("🚀 [OMNI DUAL-BRAIN] Servidor HTTP & Webhook Gateway ativo em http://127.0.0.1:8765", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
