from __future__ import annotations

import json
import re
from typing import Any

from .llm_client import GemmaClient, compactar_texto
from .rag import RagEngine


def extrair_json_objeto(texto: str) -> dict[str, Any] | None:
    """Extrai um objeto JSON mesmo quando a LLM devolve bloco markdown."""
    if not texto:
        return None

    candidato = texto.strip()
    if candidato.startswith("```json"):
        candidato = candidato[7:].strip()
        if candidato.endswith("```"):
            candidato = candidato[:-3].strip()
    elif candidato.startswith("```"):
        candidato = candidato[3:].strip()
        if candidato.endswith("```"):
            candidato = candidato[:-3].strip()

    try:
        data = json.loads(candidato)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", candidato)
    if match:
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


class LearningService:
    """Serviços de aprendizado ativo integrados ao RAG atual.

    Esta camada importa as ideias úteis do projeto complementar sem alterar o
    frontend React: geração de pergunta de revisão, avaliação de resposta e
    uso de dificuldades registradas para personalizar planos de estudo.
    """

    def __init__(self, rag: RagEngine | None = None, llm: GemmaClient | None = None) -> None:
        self.rag = rag or RagEngine(carregar_agora=True)
        self.llm = llm

    def _get_llm(self) -> GemmaClient:
        if self.llm is None:
            self.llm = GemmaClient()
        return self.llm

    def gerar_pergunta_revisao(self, disciplina: str = "Inteligência Artificial", tema: str = "", k: int = 3) -> dict[str, Any]:
        query = (tema or disciplina or "Inteligência Artificial").strip()
        docs = self.rag.buscar(query, metodo="hibrido", k=k)

        if not docs:
            return {
                "ok": False,
                "mensagem": f"Não encontrei materiais sobre {query} para gerar uma pergunta de revisão.",
                "disciplina": disciplina,
                "tema": tema,
                "documentos_recuperados": [],
            }

        contexto = "\n\n---\n\n".join(
            f"Fonte: {doc.get('fonte', '')} | ID: {doc.get('id', '')}\n{doc.get('texto', '')}"
            for doc in docs
        )
        contexto_compacto = compactar_texto(contexto, limite=3200)

        prompt = f"""
Você é o JARVIS Acadêmico, um tutor de Inteligência Artificial.
Com base EXCLUSIVAMENTE no contexto abaixo, crie UMA pergunta objetiva de active recall para testar o aluno.

Regras:
- Não responda à pergunta.
- A pergunta deve ser clara, curta e avaliável.
- Use português.
- Retorne apenas a pergunta, sem listas e sem explicações.

Disciplina: {disciplina}
Tema: {tema or query}

Contexto:
{contexto_compacto}
""".strip()

        pergunta = self._get_llm().chat([
            {"role": "system", "content": "Você gera perguntas acadêmicas objetivas com base no contexto."},
            {"role": "user", "content": prompt},
        ], temperature=0.2, max_tokens=180)

        return {
            "ok": True,
            "disciplina": disciplina,
            "tema": tema or query,
            "pergunta": pergunta.strip(),
            "contexto": contexto_compacto,
            "documentos_recuperados": docs,
        }

    def avaliar_resposta(self, pergunta: str, contexto: str, resposta_aluno: str) -> dict[str, Any]:
        prompt = f"""
Você é o JARVIS Acadêmico. Avalie a resposta do aluno usando o contexto como referência principal.

CONTEXTO:
{compactar_texto(contexto, limite=3000)}

PERGUNTA:
{pergunta}

RESPOSTA DO ALUNO:
{resposta_aluno}

Responda EXCLUSIVAMENTE com JSON válido neste formato:
{{
  "status": "CORRECT" | "PARTIAL" | "INCORRECT",
  "nota_0_10": número,
  "feedback": "feedback curto, construtivo e objetivo",
  "topic": "tópico curto para revisão",
  "sugestao_revisao": "ação prática para melhorar"
}}
""".strip()

        texto = self._get_llm().chat([
            {"role": "system", "content": "Você avalia respostas e devolve apenas JSON válido."},
            {"role": "user", "content": prompt},
        ], temperature=0.0, max_tokens=320)

        data = extrair_json_objeto(texto)
        if data is None:
            return {
                "status": "PARTIAL",
                "nota_0_10": 5,
                "feedback": texto.strip() or "A LLM não retornou JSON estruturado, mas a avaliação foi registrada.",
                "topic": "Revisão geral",
                "sugestao_revisao": "Revisar o tema com base nos materiais recuperados e tentar responder novamente.",
                "raw": texto,
            }

        status = str(data.get("status", "PARTIAL")).upper().strip()
        if status not in {"CORRECT", "PARTIAL", "INCORRECT"}:
            status = "PARTIAL"
        data["status"] = status
        try:
            data["nota_0_10"] = max(0.0, min(10.0, float(data.get("nota_0_10", 5))))
        except (TypeError, ValueError):
            data["nota_0_10"] = 5.0
        data.setdefault("feedback", "Avaliação registrada.")
        data.setdefault("topic", "Revisão geral")
        data.setdefault("sugestao_revisao", "Revisar o conceito e responder novamente.")
        return data
