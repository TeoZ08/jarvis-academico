import src.learning as learning_module
from src.learning import LearningService
from src.rag import RagEngine
from src.storage import Dificuldade, Revisao
from src.tools import TOOL_SPECS, ToolRegistry


def test_dificuldade_cria_id_e_timestamp():
    dificuldade = Dificuldade(disciplina="IA", topico="RAG")
    assert dificuldade.id
    assert dificuldade.criado_em
    assert dificuldade.origem == "manual"


def test_revisao_cria_id_e_status_pendente():
    revisao = Revisao(
        disciplina="IA",
        tema="RAG",
        pergunta="O que é RAG?",
        contexto="RAG combina recuperação e geração.",
        fontes=[],
    )
    assert revisao.id
    assert revisao.status == "pendente"
    assert revisao.avaliacao == {}


def test_tool_specs_incluem_revisao_e_dificuldades():
    nomes = {tool["name"] for tool in TOOL_SPECS}
    assert "iniciar_revisao" in nomes
    assert "avaliar_resposta_revisao" in nomes
    assert "registrar_dificuldade" in nomes
    assert "adicionar_evento" in nomes


def test_tool_registry_expoe_funcoes_novas_sem_executar_llm():
    registry = ToolRegistry(rag=RagEngine(carregar_agora=False))
    for nome in ["iniciar_revisao", "avaliar_resposta_revisao", "registrar_dificuldade", "listar_dificuldades", "adicionar_evento"]:
        assert nome in registry.funcoes


def test_learning_service_adia_inicializacao_da_llm(monkeypatch):
    def falhar_inicializacao():
        raise RuntimeError("LLM indisponível")

    monkeypatch.setattr(learning_module, "GemmaClient", falhar_inicializacao)

    service = LearningService(rag=RagEngine(carregar_agora=False))

    assert service.llm is None
