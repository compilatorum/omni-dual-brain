"""Graphify (Mapa de Código e Documentação) + RAG Semântico com Decaimento Cognitivo."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


@dataclass
class KnowledgeGraphNode:
    """Nó do grafo de conhecimento (documento técnico, função de código ou tutorial)."""

    node_id: str
    node_type: str
    title: str
    file_path: str
    content: str
    tags: list[str] = field(default_factory=list)
    outbound_links: list[str] = field(default_factory=list)
    hours_since_last_access: float = 1.0


class GraphifyKnowledgeIndex:
    """Indexador de código e documentação com busca híbrida (Grafo + Cosseno Ponderado)."""

    def __init__(self, decay_lambda: float = 0.01) -> None:
        self.decay_lambda = decay_lambda
        self._nodes: dict[str, KnowledgeGraphNode] = {}
        self._seed_default_corpus()

    def _seed_default_corpus(self) -> None:
        """Popula o índice com guias de integração, especificações Web3 e arquitetura Omni."""
        self.index_node(
            KnowledgeGraphNode(
                node_id="doc_sdk_integration",
                node_type="tutorial",
                title="Guia de Integração Pública com o Ecossistema Sovereign & Omni Graph",
                file_path="docs/integration_guide.md",
                content=(
                    "Para integrar com o projeto Sovereign Omni Graph:\n"
                    "1. Conecte-se ao endpoint WebSocket/REST público (`/api/v1/public/query`).\n"
                    "2. Utilize o schema JSON `OmniGraph-Sovereign v1.0.0` contendo `meta` e `graph.nodes`.\n"
                    "3. Para consultar métricas on-chain e milestones verificados, utilize o módulo read-only "
                    "do KarmaHQ (`project_uid: 0xabc123def4567890`)."
                ),
                tags=["integrar", "integração", "sdk", "tutorial", "websocket", "api", "comunidade"],
                outbound_links=["spec_karmahq_schema", "code_omni_state"],
                hours_since_last_access=0.5,
            )
        )
        self.index_node(
            KnowledgeGraphNode(
                node_id="spec_karmahq_schema",
                node_type="spec",
                title="Especificação de Relatórios de Impacto KarmaHQ & Farcaster",
                file_path="docs/karmahq_impact_spec.md",
                content=(
                    "Os relatórios de impacto consolidam commits semanais do GitHub e engajamento social "
                    "verificado via Neynar (Farcaster likes/corações e recasts) em um payload JSON validado "
                    "pelo schema `KarmaHQMilestonePayload`."
                ),
                tags=["karmahq", "impacto", "farcaster", "neynar", "grants", "milestone"],
                outbound_links=["doc_sdk_integration"],
                hours_since_last_access=1.2,
            )
        )
        self.index_node(
            KnowledgeGraphNode(
                node_id="code_omni_state",
                node_type="code_symbol",
                title="Controlador OmniState e Dual-Boundary LangGraph Router",
                file_path="src/omni_brain/graph/workflow.py",
                content=(
                    "O roteador LangGraph (`router_guardrail_node`) separa estritamente `role='public'` "
                    "(Fronteira Externa Read-Only) de `role='admin'` (Fronteira Interna SysOp/Web3 com "
                    "pausa obrigatória em `human_in_the_loop_node`)."
                ),
                tags=["langgraph", "rbac", "router", "arquitetura", "segurança"],
                outbound_links=["doc_sdk_integration"],
                hours_since_last_access=0.2,
            )
        )

    def index_node(self, node: KnowledgeGraphNode) -> None:
        self._nodes[node.node_id] = node

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [tok for tok in re.findall(r"[a-zA-ZÀ-ÿ0-9_]+", text.lower()) if len(tok) > 2]

    def _compute_recall_score(self, query_tokens: list[str], node: KnowledgeGraphNode) -> float:
        """Calcula Recall(P, M_i) = CosineSimilarity(V_P, V_Mi) * exp(-lambda * dt)."""
        if not query_tokens:
            return 0.0
        doc_tokens = self._tokenize(f"{node.title} {node.content} {' '.join(node.tags)}")
        vocab = set(query_tokens) | set(doc_tokens)
        if not vocab:
            return 0.0

        vec_q = [query_tokens.count(term) for term in vocab]
        vec_d = [doc_tokens.count(term) for term in vocab]

        dot = sum(q * d for q, d in zip(vec_q, vec_d))
        norm_q = math.sqrt(sum(q * q for q in vec_q))
        norm_d = math.sqrt(sum(d * d for d in vec_d))
        if norm_q == 0.0 or norm_d == 0.0:
            return 0.0

        cosine = dot / (norm_q * norm_d)
        decay = math.exp(-self.decay_lambda * max(0.0, node.hours_since_last_access))
        return round(cosine * decay, 4)

    def search(self, query: str, top_k: int = 2) -> list[dict[str, object]]:
        """Retorna os nós mais relevantes do Graphify + vizinhos diretos no grafo."""
        q_tokens = self._tokenize(query)
        scored: list[tuple[float, KnowledgeGraphNode]] = []
        for node in self._nodes.values():
            score = self._compute_recall_score(q_tokens, node)
            if score > 0:
                scored.append((score, node))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[:top_k] if scored else [(0.5, self._nodes["doc_sdk_integration"])]

        results: list[dict[str, object]] = []
        for score, node in selected:
            node.hours_since_last_access = 0.0
            results.append(
                {
                    "node_id": node.node_id,
                    "title": node.title,
                    "file_path": node.file_path,
                    "recall_score": score,
                    "content": node.content,
                    "linked_nodes": node.outbound_links,
                }
            )
        return results
