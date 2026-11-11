---
name: sysop-archon-autofix
description: Operação autônoma de servidores e esteira de auto-correção Archon em git worktree isolado.
role_required: admin
---

# Skill: SysOp & Esteira de Auto-Correção Archon

1. **Isolamento de Fronteira**:
   - Exclusivo para `role == "admin"`. Jamais expor comandos ou caminhos internos para `role == "public"`.
2. **Fluxo de Auto-Correção (Hermes -> Admin -> Archon)**:
   - Quando o worker Hermes detectar falhas repetidas em um nó do grafo (ex: erro de formato de data no agendamento) e o Admin responder `"Corrija isso"`, acionar `archon_spawn_worktree_fix`.
   - O Archon cria um `git worktree` isolado, executa o agente de código sobre o módulo afetado, roda `pytest` e prepara o Pull Request sem tocar na árvore em produção.
