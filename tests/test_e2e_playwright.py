"""Teste End-to-End Automatizado com Playwright + Captura de Screenshots de Todas as Telas."""

from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from omni_brain.api.http_server import create_http_server

REPO_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = REPO_ROOT / "docs" / "screenshots"
ARTIFACT_DIR = Path(
    "/home/sukata/.gemini/antigravity-cli/brain/541ed0e4-3b06-479a-9fcf-53906d49a401"
)

CHROMIUM_CANDIDATES = (
    "/data/data/com.termux/files/usr/bin/headless_shell",
    "/data/data/com.termux/files/usr/bin/chromium-browser",
    "/data/data/com.termux/files/usr/lib/chromium/chrome",
    "/root/.cache/ms-playwright/chromium_headless_shell-1208/chrome-linux/headless_shell",
    "/root/.cache/ms-playwright/chromium-1208/chrome-linux/chrome",
)


def _find_chromium_executable() -> str | None:
    for candidate in CHROMIUM_CANDIDATES:
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _save_and_mirror_screenshot(page, filename: str) -> Path:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    target = SCREENSHOTS_DIR / filename
    page.screenshot(path=str(target), full_page=True)
    if ARTIFACT_DIR.exists():
        shutil.copy2(target, ARTIFACT_DIR / filename)
    return target


def test_playwright_end_to_end_all_screens_and_flows() -> None:
    """Executa o fluxo completo E2E no navegador headless via Playwright e captura todas as 7 telas."""
    server, _runtime = create_http_server(host="127.0.0.1", port=8765)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.3)

    executable_path = _find_chromium_executable()
    launch_kwargs = {
        "headless": True,
        "args": ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    }
    if executable_path:
        launch_kwargs["executable_path"] = executable_path

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs)
            context = browser.new_context(viewport={"width": 1440, "height": 920})
            page = context.new_page()

            # 1. Tela 1: Command Center & Topologia RBAC (Fronteira Externa vs Fronteira Interna)
            page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
            page.wait_for_selector("#public-tools-list .tool-pill")
            assert "graphify_search_docs" in page.inner_text("#public-tools-list")
            assert "sysop_check_server_health" in page.inner_text("#admin-tools-list")
            s1 = _save_and_mirror_screenshot(page, "01_command_center_rbac_frontiers.png")
            assert s1.exists() and s1.stat().st_size > 10_000

            # 2. Tela 2 (Parte A): WhatsApp Público — Debounce Burst (3 balões + 1 Áudio Whisper)
            page.click("#tab-whatsapp")
            page.wait_for_selector("#screen-whatsapp.active")
            page.click("#btn-wa-burst")
            page.wait_for_function(
                "document.getElementById('wa-status-badge').innerText.includes('ROLE: PUBLIC')"
            )
            wa_json_text = page.inner_text("#wa-response-json")
            assert "graphify_search_docs" in wa_json_text
            assert "Guia de Integração Pública" in wa_json_text
            s2 = _save_and_mirror_screenshot(page, "02_whatsapp_public_debounce_whisper.png")
            assert s2.exists()

            # 3. Tela 2 (Parte B): WhatsApp Público — Bloqueio de Prompt Injection pelo Guardrail
            page.click("#btn-wa-injection")
            page.wait_for_function(
                "document.getElementById('wa-status-badge').innerText.includes('BLOQUEADO')"
            )
            assert "blocked_by_guardrail" in page.inner_text("#wa-response-json")
            s3 = _save_and_mirror_screenshot(page, "03_whatsapp_guardrail_injection_blocked.png")
            assert s3.exists()

            # 4. Tela 3 (Parte A): Emacs Admin — Geração do JSON KarmaHQ e Pausa Human-in-the-Loop
            page.click("#tab-emacs")
            page.wait_for_selector("#screen-emacs.active")
            page.click("#btn-emacs-generate")
            page.wait_for_function(
                "document.getElementById('emacs-hitl-badge').innerText.includes('PAUSADO HITL')"
            )
            emacs_buf_text = page.inner_text("#emacs-buffer-output")
            assert "HUMAN-IN-THE-LOOP: APROVAÇÃO NECESSÁRIA" in emacs_buf_text
            assert "karmahq_submit_milestone" in emacs_buf_text
            s4 = _save_and_mirror_screenshot(page, "04_emacs_admin_karmahq_hitl_paused.png")
            assert s4.exists()

            # 5. Tela 3 (Parte B): Emacs Admin — Aprovação HITL, Envio ao KarmaHQ e Auditoria Supabase
            page.click("#btn-emacs-approve")
            page.wait_for_function(
                "document.getElementById('emacs-hitl-badge').innerText.includes('APROVADO')"
            )
            emacs_approved_text = page.inner_text("#emacs-buffer-output")
            assert "APROVADO E EXECUTADO COM SUCESSO" in emacs_approved_text
            assert "submitted_to_karmahq" in emacs_approved_text
            s5 = _save_and_mirror_screenshot(page, "05_emacs_admin_karmahq_hitl_approved_audit.png")
            assert s5.exists()

            # 6. Tela 4: Worker Proativo Hermes & Esteira Autônoma Archon (Git Worktree)
            page.click("#tab-hermes")
            page.wait_for_selector("#screen-hermes.active")
            page.click("#btn-hermes-anomaly")
            page.wait_for_function(
                "document.getElementById('hermes-output').innerText.includes('falhou 3 vezes hoje')"
            )
            page.click("#btn-archon-fix")
            page.wait_for_function(
                "document.getElementById('archon-status-badge').innerText.includes('PR READY')"
            )
            archon_text = page.inner_text("#archon-output")
            assert "archon_spawn_worktree_fix" in archon_text
            assert "worktree-fix-001" in archon_text
            s6 = _save_and_mirror_screenshot(page, "06_hermes_heartbeat_and_archon_worktree.png")
            assert s6.exists()

            # 7. Tela 5: Conexão WhatsApp Sem Custo (QR Baileys/WAHA) & Matriz de Mocks vs Produção
            page.click("#tab-waha")
            page.wait_for_selector("#screen-waha.active")
            assert "SYNTHETIC_WEBHOOK_SIMULATOR" in page.inner_text("#readiness-table-body")
            s7 = _save_and_mirror_screenshot(page, "07_whatsapp_free_qr_baileys_and_mock_matrix.png")
            assert s7.exists()

            browser.close()
    finally:
        server.shutdown()
        server.server_close()
