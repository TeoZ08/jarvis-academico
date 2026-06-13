from __future__ import annotations

import json
import os
import re
import time
from datetime import date as DateValue, time as TimeValue
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

from src.agent import JarvisAgent
from src.config import settings
from src.llm_client import GemmaClient
from src.rag import RagEngine, SUPPORTED_EXTENSIONS
from src.learning import LearningService
from src.storage import (
    AgendaStore,
    Dificuldade,
    DificuldadeStore,
    EventoAgenda,
    Revisao,
    RevisaoStore,
    Tarefa,
    TarefaStore,
    inicializar_dados_demo,
)
from src.tools import ToolRegistry

ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"
FRONTEND_DIST_INDEX = FRONTEND_DIST_DIR / "index.html"
FRONTEND_DIST_ASSETS = FRONTEND_DIST_DIR / "assets"
FRONTEND_DIST_BRAND = FRONTEND_DIST_DIR / "brand"
UPLOADS_DIR = settings.data_dir / "uploads"
LOG_PATH = settings.log_dir / "tool_calls.jsonl"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
inicializar_dados_demo()

app = FastAPI(
    title="JARVIS Acadêmico API",
    version="2.0.0",
    description="API web para o assistente acadêmico com RAG, tool calling, agenda, tarefas e interface React.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_DIST_ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST_ASSETS)), name="assets")
if FRONTEND_DIST_BRAND.exists():
    app.mount("/brand", StaticFiles(directory=str(FRONTEND_DIST_BRAND)), name="brand")

_rag_engine: RagEngine | None = None
_agent: JarvisAgent | None = None


def _get_rag() -> RagEngine:
    global _rag_engine
    if _rag_engine is None:
        _rag_engine = RagEngine(carregar_agora=True)
    return _rag_engine


def _get_agent() -> JarvisAgent:
    global _agent
    if _agent is None:
        rag = _get_rag()
        _agent = JarvisAgent(tools=ToolRegistry(rag=rag))
    return _agent


def _rebuild_agent() -> None:
    """Reconstrói RAG e agente após upload/reindexação."""
    global _rag_engine, _agent
    _rag_engine = RagEngine(carregar_agora=True)
    _agent = JarvisAgent(tools=ToolRegistry(rag=_rag_engine))


def _nome_arquivo_seguro(nome: str) -> str:
    nome = Path(nome).name.strip()
    nome = re.sub(r"[^A-Za-z0-9_.\-áàâãéèêíïóôõöúçÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇ ]", "_", nome)
    nome = re.sub(r"\s+", "_", nome)
    return nome or "documento_importado.txt"


def _resumo_base() -> dict[str, Any]:
    try:
        rag = _get_rag()
        return {
            "documentos": len(rag.docs),
            "chunks": len(rag.chunks),
            "arquivos": sorted({doc.get("fonte", "") for doc in rag.docs if doc.get("fonte")}),
            "modo_recuperacao": getattr(
                rag,
                "modo_recuperacao_atual",
                os.getenv("RAG_MODE", "hibrido").strip().lower() or "hibrido",
            ),
        }
    except Exception as exc:
        return {
            "documentos": 0,
            "chunks": 0,
            "arquivos": [],
            "erro": str(exc),
            "modo_recuperacao": os.getenv("RAG_MODE", "hibrido").strip().lower() or "hibrido",
        }


def _frontend_setup_html() -> HTMLResponse:
    return HTMLResponse(
        """
        <!doctype html>
        <html lang="pt-BR">
          <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>JARVIS Acadêmico — frontend não compilado</title>
            <style>
              body{margin:0;min-height:100vh;display:grid;place-items:center;background:#111217;color:#f4f2f6;font-family:Inter,system-ui,sans-serif}
              main{max-width:780px;padding:36px;border:1px solid rgba(255,255,255,.1);border-radius:28px;background:#1c1d25;box-shadow:0 30px 90px rgba(0,0,0,.35)}
              code{background:#0d0e13;border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:3px 7px;color:#67e8f9}
              pre{background:#0d0e13;border:1px solid rgba(255,255,255,.1);border-radius:16px;padding:16px;overflow:auto;color:#c7c8d2}
              p{color:#a7a8b4;line-height:1.65}
            </style>
          </head>
          <body>
            <main>
              <h1>JARVIS Acadêmico</h1>
              <p>O backend FastAPI está rodando, mas o frontend React ainda não foi compilado.</p>
              <p>Para desenvolvimento, rode em dois terminais:</p>
              <pre>python -m uvicorn web_api.main:app --reload
cd frontend
npm install
npm run dev</pre>
              <p>Para produção/local integrado, gere o build:</p>
              <pre>cd frontend
npm install
npm run build
cd ..
python -m uvicorn web_api.main:app --reload</pre>
            </main>
          </body>
        </html>
        """.strip()
    )


class ChatRequest(BaseModel):
    mensagem: str = Field(..., min_length=1, description="Mensagem do usuário para o JARVIS.")


class TarefaRequest(BaseModel):
    titulo: str = Field(..., min_length=1)
    prazo: str = ""
    disciplina: str = ""
    prioridade: str = "média"


class AgendaRequest(BaseModel):
    data: str = Field(..., min_length=10, max_length=10)
    titulo: str = Field(..., min_length=1)
    hora_inicio: str = ""
    hora_fim: str = ""
    tipo: str = "aula"
    observacao: str = ""

    @field_validator("titulo")
    @classmethod
    def validar_titulo(cls, valor: str) -> str:
        titulo = valor.strip()
        if not titulo:
            raise ValueError("O título do evento é obrigatório.")
        return titulo

    @field_validator("data")
    @classmethod
    def validar_data(cls, valor: str) -> str:
        try:
            DateValue.fromisoformat(valor)
        except ValueError as exc:
            raise ValueError("A data deve estar no formato AAAA-MM-DD.") from exc
        return valor

    @field_validator("hora_inicio", "hora_fim")
    @classmethod
    def validar_hora(cls, valor: str) -> str:
        if not valor:
            return ""
        if not re.fullmatch(r"\d{2}:\d{2}", valor):
            raise ValueError("O horário deve estar no formato HH:MM.")
        try:
            TimeValue.fromisoformat(valor)
        except ValueError as exc:
            raise ValueError("Informe um horário válido.") from exc
        return valor

    @field_validator("tipo", "observacao")
    @classmethod
    def limpar_texto_opcional(cls, valor: str) -> str:
        return valor.strip()

    @model_validator(mode="after")
    def validar_intervalo(self) -> "AgendaRequest":
        if self.hora_inicio and self.hora_fim and self.hora_fim < self.hora_inicio:
            raise ValueError("A hora final não pode ser anterior à hora inicial.")
        return self


class DificuldadeRequest(BaseModel):
    disciplina: str = "Inteligência Artificial"
    topico: str = Field(..., min_length=1)
    observacao: str = ""


class RevisaoRequest(BaseModel):
    disciplina: str = "Inteligência Artificial"
    tema: str = ""


class AvaliacaoRevisaoRequest(BaseModel):
    resposta_aluno: str = Field(..., min_length=1)
    review_id: str = ""


@app.get("/api/health")
def health() -> dict[str, Any]:
    base = _resumo_base()
    return {
        "ok": True,
        "modo_llm": settings.llm_mode,
        "llm_mode": settings.llm_mode,
        "llm_provider": settings.llm_provider,
        "llm_provider_label": settings.llm_provider_label,
        "embedding_model": settings.embedding_model,
        "base": {"documentos": base["documentos"], "chunks": base["chunks"]},
    }


@app.get("/api/status")
def status() -> dict[str, Any]:
    base = _resumo_base()
    return {
        "modo_llm": settings.llm_mode,
        "llm_mode": settings.llm_mode,
        "llm_provider": settings.llm_provider,
        "llm_provider_label": settings.llm_provider_label,
        "llm_model": str(settings.gemma_model or "").strip(),
        "usando_mock": settings.usando_mock,
        "rag_mode": base.get("modo_recuperacao"),
        "docs": base.get("documentos", 0),
        "chunks": base.get("chunks", 0),
        "base_rag": base,
        "uploads_dir": str(UPLOADS_DIR.relative_to(ROOT_DIR)),
    }


@app.get("/api/debug/gemma-ping")
def debug_gemma_ping(prompt: str = Query("Responda apenas: OK", min_length=1, max_length=200)) -> dict[str, Any]:
    """Diagnóstico direto da LLM remota: não usa RAG, agente nem tool calling.

    O caminho mantém "gemma" por compatibilidade com versões anteriores.
    """
    inicio = time.perf_counter()
    try:
        resultado = GemmaClient().ping(prompt=prompt)
        resultado["elapsed_total_seconds"] = round(time.perf_counter() - inicio, 3)
        return resultado
    except Exception as exc:
        return {
            "ok": False,
            "tipo_erro": exc.__class__.__name__,
            "error_type": exc.__class__.__name__,
            "mensagem": str(exc),
            "error_message": str(exc),
            "elapsed_total_seconds": round(time.perf_counter() - inicio, 3),
            "modo_llm": settings.llm_mode,
            "llm_mode": settings.llm_mode,
            "provider": settings.llm_provider,
            "llm_provider_label": settings.llm_provider_label,
            "base_url_configurada": bool(str(settings.gemma_base_url or "").strip()),
            "base_url": str(settings.gemma_base_url or "").strip(),
            "model": str(settings.gemma_model or "").strip(),
            "api_key_presente": bool(str(settings.gemma_api_key or "").strip()),
            "timeout_seconds": os.getenv("GEMMA_TIMEOUT_SECONDS", "180"),
            "max_tokens": os.getenv("GEMMA_MAX_TOKENS", "512"),
        }


@app.get("/api/debug/config")
def debug_config() -> dict[str, Any]:
    """Mostra configuração efetiva sem expor segredos."""
    return {
        "modo_llm": settings.llm_mode,
        "llm_mode": settings.llm_mode,
        "llm_provider": settings.llm_provider,
        "llm_provider_label": settings.llm_provider_label,
        "usando_mock": settings.usando_mock,
        "gemma_base_url_presente": bool(str(settings.gemma_base_url or "").strip()),
        "gemma_base_url": str(settings.gemma_base_url or "").strip(),
        "gemma_model": str(settings.gemma_model or "").strip(),
        "gemma_api_key_presente": bool(str(settings.gemma_api_key or "").strip()),
        "gemma_timeout_seconds": os.getenv("GEMMA_TIMEOUT_SECONDS", "180"),
        "gemma_max_tokens": os.getenv("GEMMA_MAX_TOKENS", "512"),
        "rag_mode": os.getenv("RAG_MODE", "hibrido"),
        "base_rag": _resumo_base(),
    }


@app.post("/api/chat")
def chat(payload: ChatRequest) -> dict[str, Any]:
    try:
        resultado = _get_agent().responder(payload.mensagem)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return resultado


@app.post("/api/upload")
async def upload_documentos(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    if not files:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")

    salvos: list[str] = []
    rejeitados: list[dict[str, str]] = []

    for arquivo in files:
        nome = _nome_arquivo_seguro(arquivo.filename or "documento")
        ext = Path(nome).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            rejeitados.append({"arquivo": nome, "motivo": f"Extensão {ext or '(sem extensão)'} não suportada."})
            continue

        conteudo = await arquivo.read()
        destino = UPLOADS_DIR / nome
        destino.write_bytes(conteudo)
        salvos.append(str(destino.relative_to(settings.data_dir)))

    if salvos:
        _rebuild_agent()

    return {
        "salvos": salvos,
        "rejeitados": rejeitados,
        "base_rag": _resumo_base(),
    }


@app.post("/api/reindex")
def reindexar() -> dict[str, Any]:
    _rebuild_agent()
    return _resumo_base()


@app.get("/api/tasks")
def listar_tarefas(incluir_concluidas: bool = Query(False)) -> list[dict[str, Any]]:
    return TarefaStore().listar(incluir_concluidas=incluir_concluidas)


@app.post("/api/tasks")
def adicionar_tarefa(payload: TarefaRequest) -> dict[str, Any]:
    return TarefaStore().adicionar(
        Tarefa(
            titulo=payload.titulo,
            prazo=payload.prazo,
            disciplina=payload.disciplina,
            prioridade=payload.prioridade,
        )
    )


@app.patch("/api/tasks/{identificador}/complete")
def concluir_tarefa(identificador: str) -> dict[str, Any]:
    try:
        return TarefaStore().concluir(identificador)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/agenda")
def consultar_agenda(
    inicio: str | None = None,
    fim: str | None = None,
    termo: str | None = None,
) -> list[dict[str, Any]]:
    return AgendaStore().consultar(inicio=inicio, fim=fim, termo=termo)


@app.post("/api/agenda")
def adicionar_evento(payload: AgendaRequest) -> dict[str, Any]:
    return AgendaStore().adicionar(
        EventoAgenda(
            data=payload.data,
            titulo=payload.titulo,
            hora_inicio=payload.hora_inicio,
            hora_fim=payload.hora_fim,
            tipo=payload.tipo,
            observacao=payload.observacao,
        )
    )


@app.get("/api/dificuldades")
def listar_dificuldades(
    disciplina: str | None = None,
    limite: int = Query(20, ge=1, le=200),
) -> list[dict[str, Any]]:
    return DificuldadeStore().listar(disciplina=disciplina, limite=limite)


@app.post("/api/dificuldades")
def registrar_dificuldade(payload: DificuldadeRequest) -> dict[str, Any]:
    return DificuldadeStore().adicionar(
        Dificuldade(
            disciplina=payload.disciplina,
            topico=payload.topico,
            origem="api",
            observacao=payload.observacao,
        )
    )


@app.get("/api/revisoes")
def listar_revisoes(incluir_avaliadas: bool = Query(True)) -> list[dict[str, Any]]:
    return RevisaoStore().listar(incluir_avaliadas=incluir_avaliadas)


@app.post("/api/revisoes/iniciar")
def iniciar_revisao(payload: RevisaoRequest) -> dict[str, Any]:
    agent = _get_agent()
    gerada = LearningService(agent.tools.rag).gerar_pergunta_revisao(
        disciplina=payload.disciplina,
        tema=payload.tema,
    )
    if not gerada.get("ok"):
        return gerada
    revisao = RevisaoStore().criar(
        Revisao(
            disciplina=payload.disciplina,
            tema=gerada.get("tema", payload.tema or payload.disciplina),
            pergunta=gerada["pergunta"],
            contexto=gerada["contexto"],
            fontes=gerada.get("documentos_recuperados", []),
        )
    )
    return {
        "ok": True,
        "review_id": revisao["id"],
        "disciplina": revisao["disciplina"],
        "tema": revisao["tema"],
        "pergunta": revisao["pergunta"],
        "fontes": revisao["fontes"],
    }


@app.post("/api/revisoes/avaliar")
def avaliar_revisao(payload: AvaliacaoRevisaoRequest) -> dict[str, Any]:
    try:
        revisao = RevisaoStore().obter(payload.review_id or None)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    agent = _get_agent()
    avaliacao = LearningService(agent.tools.rag).avaliar_resposta(
        pergunta=revisao["pergunta"],
        contexto=revisao["contexto"],
        resposta_aluno=payload.resposta_aluno,
    )
    atualizada = RevisaoStore().registrar_avaliacao(revisao["id"], avaliacao)
    if avaliacao.get("status") in {"PARTIAL", "INCORRECT"}:
        DificuldadeStore().adicionar(
            Dificuldade(
                disciplina=revisao.get("disciplina", "Inteligência Artificial"),
                topico=str(avaliacao.get("topic", "Revisão geral")),
                origem="avaliacao_revisao_api",
                observacao=str(avaliacao.get("feedback", "")),
            )
        )
    return {"ok": True, "review_id": revisao["id"], "avaliacao": avaliacao, "revisao": atualizada}


@app.get("/api/logs")
def logs(limit: int = Query(20, ge=1, le=200)) -> dict[str, Any]:
    if not LOG_PATH.exists():
        return {"items": []}

    linhas = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    itens: list[dict[str, Any]] = []
    for linha in linhas:
        try:
            itens.append(json.loads(linha))
        except json.JSONDecodeError:
            itens.append({"raw": linha})
    return {"items": itens[::-1]}


@app.get("/", include_in_schema=False, response_model=None)
def index() -> Response:
    if FRONTEND_DIST_INDEX.exists():
        return FileResponse(str(FRONTEND_DIST_INDEX))
    return _frontend_setup_html()


@app.get("/{full_path:path}", include_in_schema=False, response_model=None)
def spa_fallback(full_path: str) -> Response:
    # FastAPI já trata /api acima. Este fallback permite rotas internas do React.
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Endpoint não encontrado.")
    if FRONTEND_DIST_INDEX.exists():
        return FileResponse(str(FRONTEND_DIST_INDEX))
    return _frontend_setup_html()


@app.exception_handler(Exception)
def erro_generico(_, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})
