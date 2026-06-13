from fastapi.testclient import TestClient

import src.storage as storage
import web_api.main as api_module
from src.agent import JarvisAgent


class LlmApiComFalha:
    provider = "openai-compatible"
    provider_label = "Qwen teste"

    def chat(self, *_args, **_kwargs):
        raise ConnectionError("endpoint externo indisponível")


class ToolsApiStub:
    def executar(self, nome, argumentos, metadados_saida=None):
        assert nome == "buscar_material_rag"
        saida = {
            "resposta": "Resposta local baseada no material de RAG.",
            "resultado_vazio": False,
            "documentos_recuperados": [
                {"id": "doc-1", "fonte": "01_rag.md", "score": 0.88, "texto": "Contexto local."}
            ],
        }
        saida.update(metadados_saida or {})
        return saida


def test_api_chat_retorna_200_com_llm_indisponivel(monkeypatch):
    agente = object.__new__(JarvisAgent)
    agente.llm = LlmApiComFalha()
    agente.tools = ToolsApiStub()
    monkeypatch.setattr(api_module, "_get_agent", lambda: agente)
    client = TestClient(api_module.app)

    response = client.post("/api/chat", json={"mensagem": "O que é RAG?"})

    assert response.status_code == 200
    data = response.json()
    assert data["tool_calls"][0]["tool"] == "buscar_material_rag"
    assert data["tool_calls"][0]["saida"]["fallback_sem_llm"] is True


def test_api_agenda_adiciona_lista_e_valida_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "AGENDA_PATH", tmp_path / "agenda.json")
    client = TestClient(api_module.app)
    payload = {
        "titulo": "Revisão de RAG",
        "data": "2026-06-15",
        "hora_inicio": "19:00",
        "hora_fim": "20:30",
        "tipo": "revisão",
        "observacao": "Revisar BM25 e embeddings.",
    }

    created = client.post("/api/agenda", json=payload)
    listed = client.get("/api/agenda")
    invalid = client.post("/api/agenda", json={"titulo": "", "data": "15/06/2026"})
    invalid_time = client.post("/api/agenda", json={
        "titulo": "Horário inválido",
        "data": "2026-06-15",
        "hora_inicio": "21:00",
        "hora_fim": "20:00",
    })

    assert created.status_code == 200
    assert created.json()["titulo"] == "Revisão de RAG"
    assert listed.status_code == 200
    assert listed.json() == [payload]
    assert invalid.status_code == 422
    assert invalid_time.status_code == 422
