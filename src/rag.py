from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
from typing import Any

import numpy as np
from pypdf import PdfReader
from rank_bm25 import BM25Okapi

from .config import settings
from .llm_client import GemmaClient

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".py"}

STOPWORDS_BUSCA = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas",
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
    "para", "por", "com", "sem", "sobre", "entre", "até", "ate",
    "que", "qual", "quais", "quem", "quando", "onde", "como", "porque", "porquê",
    "é", "e", "ou", "se", "ao", "aos", "à", "às",
    "me", "meu", "minha", "seu", "sua", "dele", "dela",
    "explique", "explica", "resuma", "resumo", "defina", "conceito", "conceitos",
    "funciona", "funcionam", "serve", "servem", "fale", "diga", "quero", "saber",
    "academico", "acadêmico", "faculdade", "disciplina", "conteudo", "conteúdo",
}


def tokenizar(texto: str) -> list[str]:
    return re.findall(r"\w+", texto.lower())


def termos_relevantes(texto: str) -> list[str]:
    return [t for t in tokenizar(texto) if len(t) >= 3 and t not in STOPWORDS_BUSCA]


def normalizar(v: np.ndarray) -> np.ndarray:
    v = np.array(v, dtype="float32")
    delta = float(v.max() - v.min()) if len(v) else 0.0
    if delta < 1e-9:
        return np.zeros_like(v)
    return (v - v.min()) / delta


def ler_arquivo(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".txt", ".md", ".py"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if ext == ".pdf":
        reader = PdfReader(str(path))
        partes = []
        for idx, page in enumerate(reader.pages, start=1):
            texto = page.extract_text() or ""
            if texto.strip():
                partes.append(f"\n\n[Página {idx}]\n{texto}")
        return "\n".join(partes)
    return ""


def carregar_documentos(data_dir: Path = settings.data_dir) -> list[dict]:
    docs: list[dict] = []
    for path in sorted(data_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            texto = ler_arquivo(path).strip()
            if texto:
                docs.append({
                    "id": path.stem,
                    "fonte": str(path.relative_to(settings.data_dir)),
                    "texto": texto,
                    "tipo": path.suffix.lower().replace(".", ""),
                })
    return docs


def chunk_texto(texto: str, tamanho: int = 700, sobreposicao: int = 80) -> list[str]:
    if sobreposicao >= tamanho:
        raise ValueError("A sobreposição deve ser menor que o tamanho do chunk.")

    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    paragrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]
    chunks: list[str] = []
    atual = ""

    for paragrafo in paragrafos:
        if len(atual) + len(paragrafo) + 2 <= tamanho:
            atual = (atual + "\n\n" + paragrafo).strip()
        else:
            if atual:
                chunks.append(atual)
            if len(paragrafo) <= tamanho:
                atual = paragrafo
            else:
                passo = tamanho - sobreposicao
                for inicio in range(0, len(paragrafo), passo):
                    parte = paragrafo[inicio:inicio + tamanho].strip()
                    if parte:
                        chunks.append(parte)
                atual = ""
    if atual:
        chunks.append(atual)
    return chunks


@dataclass
class RagConfig:
    tamanho_chunk: int = 700
    sobreposicao: int = 80
    alpha_hibrido: float = 0.6
    min_sobreposicao_termos: int = 1
    min_score_dense: float = 0.42


def modo_rag_lexical() -> bool:
    """Ativa um modo leve para deploy público.

    Em serviços gratuitos, carregar SentenceTransformer + FAISS pode consumir muita
    memória e derrubar o backend. Quando RAG_MODE=lexical, o sistema usa BM25
    para recuperação e mantém o fallback acadêmico funcionando sem baixar modelos
    pesados do HuggingFace.
    """
    return os.getenv("RAG_MODE", "").strip().lower() in {"lexical", "bm25", "light"}


def _carregar_sentence_transformer():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model)


def _criar_indice_faiss(dim: int):
    import faiss

    return faiss.IndexFlatIP(dim)


class RagEngine:
    def __init__(self, config: RagConfig | None = None, carregar_agora: bool = True) -> None:
        self.config = config or RagConfig()
        self.docs: list[dict] = []
        self.chunks: list[dict] = []
        self.modelo_embed: Any | None = None
        self.matriz_emb: np.ndarray | None = None
        self.indice_faiss = None
        self.indice_bm25 = None
        self.modo_recuperacao_atual = "nao_indexado"
        if carregar_agora:
            self.reindexar()

    def reindexar(self) -> dict:
        self.docs = carregar_documentos()
        self.chunks = []
        for doc in self.docs:
            partes = chunk_texto(
                doc["texto"],
                tamanho=self.config.tamanho_chunk,
                sobreposicao=self.config.sobreposicao,
            )
            for i, parte in enumerate(partes):
                self.chunks.append({
                    "id": f"{doc['id']}_chunk_{i:04d}",
                    "doc_id": doc["id"],
                    "fonte": doc["fonte"],
                    "texto": parte,
                })

        if not self.chunks:
            self.indice_bm25 = None
            self.indice_faiss = None
            self.matriz_emb = None
            self.modo_recuperacao_atual = "vazio"
            return {"documentos": 0, "chunks": 0}

        corpus_tokenizado = [tokenizar(c["texto"]) for c in self.chunks]
        self.indice_bm25 = BM25Okapi(corpus_tokenizado)

        # Modo leve para deploy público: evita baixar/carregar modelos densos.
        # O RAG continua funcional via BM25 e o fallback acadêmico continua ativo.
        if modo_rag_lexical():
            self.modelo_embed = None
            self.matriz_emb = None
            self.indice_faiss = None
            self.modo_recuperacao_atual = "lexical_bm25"
            return {
                "documentos": len(self.docs),
                "chunks": len(self.chunks),
                "modo_recuperacao": self.modo_recuperacao_atual,
            }

        try:
            self.modelo_embed = _carregar_sentence_transformer()
            textos = [c["texto"] for c in self.chunks]
            self.matriz_emb = self.modelo_embed.encode(
                textos,
                normalize_embeddings=True,
                show_progress_bar=False,
            ).astype("float32")

            self.indice_faiss = _criar_indice_faiss(self.matriz_emb.shape[1])
            self.indice_faiss.add(self.matriz_emb)
        except (ImportError, ModuleNotFoundError) as exc:
            self.modelo_embed = None
            self.matriz_emb = None
            self.indice_faiss = None
            self.modo_recuperacao_atual = "lexical_bm25_fallback"
            return {
                "documentos": len(self.docs),
                "chunks": len(self.chunks),
                "modo_recuperacao": self.modo_recuperacao_atual,
                "aviso": f"Busca densa indisponível: {exc.__class__.__name__}. Usando BM25.",
            }

        self.modo_recuperacao_atual = "hibrido_dense_bm25"
        return {
            "documentos": len(self.docs),
            "chunks": len(self.chunks),
            "modo_recuperacao": self.modo_recuperacao_atual,
        }

    def _garantir_indice(self) -> None:
        if not self.chunks or self.indice_bm25 is None:
            raise RuntimeError("Índice RAG vazio. Coloque documentos na pasta /data e rode reindexar().")

    def recuperar_bm25(self, pergunta: str, k: int = 3) -> list[dict]:
        self._garantir_indice()
        termos_consulta = termos_relevantes(pergunta) or tokenizar(pergunta)
        scores = self.indice_bm25.get_scores(termos_consulta)
        idx = np.argsort(scores)[::-1][:k]
        return [self._formatar_resultado(i, float(scores[i])) for i in idx]

    def recuperar_dense(self, pergunta: str, k: int = 3) -> list[dict]:
        self._garantir_indice()
        if self.modelo_embed is None or self.indice_faiss is None:
            return self.recuperar_bm25(pergunta, k=k)
        q = self.modelo_embed.encode([pergunta], normalize_embeddings=True).astype("float32")
        scores, idx = self.indice_faiss.search(q, min(k, len(self.chunks)))
        return [self._formatar_resultado(int(i), float(scores[0][j])) for j, i in enumerate(idx[0]) if i >= 0]

    def recuperar_hibrido(self, pergunta: str, k: int = 3, alpha: float | None = None) -> list[dict]:
        self._garantir_indice()
        if self.modelo_embed is None or self.matriz_emb is None:
            return self.recuperar_bm25(pergunta, k=k)
        alpha = self.config.alpha_hibrido if alpha is None else alpha
        termos_consulta = termos_relevantes(pergunta) or tokenizar(pergunta)
        score_bm25 = np.array(self.indice_bm25.get_scores(termos_consulta), dtype="float32")
        q = self.modelo_embed.encode([pergunta], normalize_embeddings=True).astype("float32")
        score_dense = np.dot(self.matriz_emb, q[0])
        score_final = alpha * normalizar(score_dense) + (1.0 - alpha) * normalizar(score_bm25)
        idx = np.argsort(score_final)[::-1][:k]
        return [self._formatar_resultado(int(i), float(score_final[i])) for i in idx]

    def _formatar_resultado(self, idx: int, score: float) -> dict:
        item = self.chunks[idx]
        return {
            "id": item["id"],
            "fonte": item["fonte"],
            "score": round(score, 4),
            "texto": item["texto"],
        }

    def buscar(self, pergunta: str, metodo: str = "hibrido", k: int = 3) -> list[dict]:
        if not self.chunks or self.indice_bm25 is None:
            return []
        metodo = metodo.lower().strip()
        if metodo == "bm25":
            return self.recuperar_bm25(pergunta, k=k)
        if metodo == "dense":
            return self.recuperar_dense(pergunta, k=k)
        return self.recuperar_hibrido(pergunta, k=k)

    def _diagnosticar_relevancia(self, pergunta: str, docs: list[dict]) -> dict:
        termos_pergunta = set(termos_relevantes(pergunta))
        texto_contexto = " ".join(d.get("texto", "") for d in docs)
        termos_contexto = set(termos_relevantes(texto_contexto))
        termos_encontrados = sorted(termos_pergunta.intersection(termos_contexto))

        score_dense_top = 0.0
        if self.modelo_embed is not None and self.matriz_emb is not None and len(self.matriz_emb):
            q = self.modelo_embed.encode([pergunta], normalize_embeddings=True).astype("float32")
            score_dense_top = float(np.max(np.dot(self.matriz_emb, q[0])))

        return {
            "termos_relevantes_pergunta": sorted(termos_pergunta),
            "termos_encontrados_no_contexto": termos_encontrados,
            "qtd_termos_encontrados": len(termos_encontrados),
            "score_dense_top": round(score_dense_top, 4),
            "modo_recuperacao": self.modo_recuperacao_atual,
        }

    def _resultado_vazio(self, diagnostico: dict) -> bool:
        """Detecta quando o RAG recuperou apenas vizinhos fracos/indiretos.

        O score híbrido é normalizado e pode parecer alto mesmo para tema fora da base.
        Por isso usamos sinais mais confiáveis: sobreposição de termos relevantes
        e similaridade densa bruta mínima.
        """
        tem_termo_no_contexto = diagnostico["qtd_termos_encontrados"] >= self.config.min_sobreposicao_termos
        tem_similaridade_minima = diagnostico["score_dense_top"] >= self.config.min_score_dense
        return not (tem_termo_no_contexto or tem_similaridade_minima)

    def _resposta_extrativa(self, docs: list[dict]) -> str:
        trechos = []
        for indice, doc in enumerate(docs[:3], start=1):
            texto = re.sub(r"\s+", " ", str(doc.get("texto", ""))).strip()
            if len(texto) > 520:
                texto = texto[:517].rstrip() + "..."
            trechos.append(
                f"{indice}. **{doc.get('fonte', 'material local')}**\n{texto}"
            )
        return (
            "Encontrei evidências nos materiais cadastrados. Como a LLM remota está "
            "indisponível, apresento os trechos recuperados sem reescrita:\n\n"
            + "\n\n".join(trechos)
        )

    def responder(
        self,
        pergunta: str,
        metodo: str = "hibrido",
        k: int = 3,
        usar_llm: bool = True,
    ) -> dict:
        docs = self.buscar(pergunta, metodo=metodo, k=k)
        diagnostico = self._diagnosticar_relevancia(pergunta, docs)

        if not docs or self._resultado_vazio(diagnostico):
            return {
                "resposta": "RESULTADO_VAZIO: O tema não foi encontrado nos materiais cadastrados.",
                "resultado_vazio": True,
                "fonte_resposta": "sem_material_cadastrado",
                "documentos_recuperados": docs,
                "diagnostico_recuperacao": diagnostico,
            }

        resposta_base = {
            "resultado_vazio": False,
            "fonte_resposta": "materiais_rag",
            "documentos_recuperados": docs,
            "diagnostico_recuperacao": diagnostico,
        }
        if not usar_llm:
            return {
                **resposta_base,
                "resposta": self._resposta_extrativa(docs),
                "modo_resposta": "rag_extrativo_sem_llm",
                "fallback_sem_llm": True,
            }

        contexto = "\n\n".join(
            f"Trecho {i+1} | Fonte: {d['fonte']} | ID: {d['id']}\n{d['texto']}"
            for i, d in enumerate(docs)
        )
        prompt = (
            "Você é o JARVIS Acadêmico. Responda em português, de forma didática e objetiva.\n"
            "Use apenas o contexto recuperado. Se a resposta não estiver no contexto, diga claramente "
            "que não encontrou evidência suficiente.\n\n"
            f"Contexto:\n{contexto}\n\nPergunta: {pergunta}"
        )
        llm = GemmaClient()
        try:
            resposta = llm.chat([
                {"role": "system", "content": "Você responde perguntas acadêmicas com base em evidências recuperadas."},
                {"role": "user", "content": prompt},
            ])
        except Exception as exc:
            return {
                **resposta_base,
                "resposta": self._resposta_extrativa(docs),
                "modo_resposta": "rag_extrativo_sem_llm",
                "fallback_sem_llm": True,
                "fallback_origem": "geracao_resposta_rag",
                "erro_llm_etapa": "geracao_resposta_rag",
                "erro_llm_tipo": type(exc).__name__,
                "erro_llm_mensagem": (
                    "A LLM remota falhou ao redigir a resposta. "
                    "Os trechos locais foram preservados sem reescrita."
                ),
            }
        return {
            **resposta_base,
            "resposta": resposta,
            "modo_resposta": "rag_gerado_com_llm",
        }
