---
name: web3-karmahq-reporter
description: Consolida commits semanais do GitHub e métricas sociais do Farcaster (Neynar) em payloads JSON determinísticos para o KarmaHQ com pausa obrigatória Human-in-the-Loop.
role_required: admin
---

# Skill: Relatórios de Impacto Web3 (GitHub + Neynar -> KarmaHQ)

1. **Coleta Paralela via MCP**:
   - Invocar `github_list_weekly_commits` para obter os commits da semana (`sha`, `message`, `files_changed`).
   - Invocar `neynar_get_top_casts` para obter os casts com mais corações (`likes_count`) e recasts.
2. **Tradução Determinística (Pydantic)**:
   - Invocar `karmahq_build_milestone_payload` para validar o schema `KarmaHQMilestonePayload` e garantir ausência de segredos no markdown.
3. **Aprovação Humana Obrigatória (HITL)**:
   - Pausar no nó `human_in_the_loop_node` e exibir o JSON formatado no Emacs (`*Omni-Brain-Admin*`) ou no WhatsApp Admin.
   - Somente disparar `karmahq_submit_milestone` após receber `"Aprovado"`.
