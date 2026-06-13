import src.agent as agent_module
from src.agent import JarvisAgent
from src.rag import RagEngine


class LlmComFalha:
    provider = "openai-compatible"
    provider_label = "Qwen teste"

    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    def chat(self, *_args, **_kwargs) -> str:
        self.calls += 1
        raise self.exc


class ToolsStub:
    def __init__(self, saida_rag: dict) -> None:
        self.saida_rag = saida_rag
        self.chamadas = []

    def executar(self, nome, argumentos, metadados_saida=None):
        self.chamadas.append((nome, argumentos))
        saida = dict(self.saida_rag)
        if metadados_saida:
            saida.update(metadados_saida)
        return saida


def criar_agente(tools: ToolsStub, exc: Exception | None = None) -> JarvisAgent:
    agente = object.__new__(JarvisAgent)
    agente.tools = tools
    agente.llm = LlmComFalha(exc or PermissionError("token secreto recusado"))
    return agente


def test_llm_falha_e_pergunta_academica_executa_rag_sem_nova_chamada():
    tools = ToolsStub({
        "resposta": "RAG combina recuperação e geração.",
        "resultado_vazio": False,
        "documentos_recuperados": [
            {"id": "rag-1", "fonte": "01_rag.md", "score": 0.91, "texto": "RAG usa contexto."}
        ],
    })
    agente = criar_agente(tools)

    resultado = agente.responder("O que é RAG?")

    assert tools.chamadas[0][0] == "buscar_material_rag"
    assert tools.chamadas[0][1]["sem_llm"] is True
    assert resultado["tool_calls"][0]["saida"]["fallback_sem_llm"] is True
    assert "RAG combina recuperação e geração." in resultado["resposta"]
    assert "01_rag.md" in resultado["resposta"]
    assert agente.llm.calls == 1


def test_llm_falha_e_mensagem_casual_nao_executa_rag():
    tools = ToolsStub({})
    agente = criar_agente(tools)

    resultado = agente.responder("oi")

    assert tools.chamadas == []
    assert resultado["tool_calls"] == []
    assert "LLM remota está indisponível" in resultado["resposta"]
    assert agente.llm.calls == 1


def test_llm_falha_e_rag_vazio_retorna_aviso_transparente():
    tools = ToolsStub({
        "resposta": "RESULTADO_VAZIO",
        "resultado_vazio": True,
        "documentos_recuperados": [],
    })
    agente = criar_agente(tools, TimeoutError("timeout"))

    resultado = agente.responder("Explique árvores de decisão.")

    assert resultado["tool_calls"][0]["tool"] == "buscar_material_rag"
    assert resultado["tool_calls"][0]["saida"]["resultado_vazio"] is True
    assert "Não encontrei esse tema nos materiais cadastrados" in resultado["resposta"]
    assert "LLM remota está indisponível" in resultado["resposta"]
    assert agente.llm.calls == 1


def test_resposta_invalida_da_llm_tambem_aciona_fallback():
    tools = ToolsStub({
        "resposta": "Trecho local sobre embeddings.",
        "resultado_vazio": False,
        "documentos_recuperados": [],
    })
    agente = criar_agente(tools)
    agente.llm.chat = lambda *_args, **_kwargs: "não é JSON"

    resultado = agente.responder("Explique embeddings.")

    assert resultado["tool_calls"][0]["saida"]["erro_llm_tipo"] == "ValueError"
    assert "Trecho local sobre embeddings." in resultado["resposta"]


def test_rag_extrativo_nao_instancia_llm(monkeypatch):
    rag = RagEngine(carregar_agora=False)
    docs = [{
        "id": "rag_chunk_0001",
        "fonte": "01_rag.md",
        "score": 0.8,
        "texto": "RAG combina recuperação de documentos e geração de respostas.",
    }]
    monkeypatch.setattr(rag, "buscar", lambda *_args, **_kwargs: docs)
    monkeypatch.setattr(
        rag,
        "_diagnosticar_relevancia",
        lambda *_args, **_kwargs: {
            "qtd_termos_encontrados": 1,
            "score_dense_top": 0.0,
            "modo_recuperacao": "lexical_bm25",
        },
    )

    resultado = rag.responder("O que é RAG?", usar_llm=False)

    assert resultado["resultado_vazio"] is False
    assert resultado["fallback_sem_llm"] is True
    assert resultado["modo_resposta"] == "rag_extrativo_sem_llm"
    assert "01_rag.md" in resultado["resposta"]


def test_falha_ao_inicializar_cliente_llm_nao_impede_fallback(monkeypatch):
    tools = ToolsStub({
        "resposta": "Material local disponível.",
        "resultado_vazio": False,
        "documentos_recuperados": [],
    })

    def falhar_inicializacao():
        raise RuntimeError("GEMMA_API_KEY ausente")

    monkeypatch.setattr(agent_module, "GemmaClient", falhar_inicializacao)
    agente = JarvisAgent(tools=tools)

    resultado = agente.responder("Explique RAG.")

    assert resultado["fallback_sem_llm"] is True
    assert resultado["tool_calls"][0]["tool"] == "buscar_material_rag"
    assert resultado["tool_calls"][0]["saida"]["erro_llm_tipo"] == "RuntimeError"
