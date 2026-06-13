from __future__ import annotations

from datetime import date
import json
import re
import unicodedata
from typing import Any

from .llm_client import GemmaClient, compactar_texto
from .tools import TOOL_SPECS, ToolRegistry


class _LlmIndisponivel:
    provider = "openai-compatible"
    provider_label = "LLM remota"

    def __init__(self, erro: Exception) -> None:
        self.erro = erro

    def chat(self, *_args, **_kwargs) -> str:
        raise self.erro


class JarvisAgent:
    """Agente com tool calling decidido pela LLM.

    Estratégia usada:
    1. A LLM recebe a pergunta e a lista de ferramentas.
    2. A LLM deve devolver JSON com as chamadas necessárias.
    3. O Python executa as ferramentas e registra logs.
    4. A LLM gera a resposta final usando os resultados.
    """

    def __init__(self, tools: ToolRegistry | None = None) -> None:
        try:
            self.llm = GemmaClient()
        except Exception as exc:
            self.llm = _LlmIndisponivel(exc)
        self.tools = tools or ToolRegistry()

    def responder(self, mensagem_usuario: str) -> dict[str, Any]:
        erro_decisao: Exception | None = None
        try:
            decisoes = self._decidir_ferramentas(mensagem_usuario)
        except Exception as exc:
            erro_decisao = exc
            decisoes = self._decisoes_fallback_sem_llm(mensagem_usuario)

        resultados = []
        metadados_fallback = self._metadados_erro_llm(erro_decisao) if erro_decisao else None

        for chamada in decisoes:
            nome = chamada.get("tool") or chamada.get("name")
            args = chamada.get("args", {}) or {}
            if not nome:
                continue
            saida = self.tools.executar(nome, args, metadados_saida=metadados_fallback)
            resultados.append({"tool": nome, "args": args, "saida": saida})

        fallback_sem_llm = erro_decisao is not None
        try:
            resposta_final = self._responder_final(
                mensagem_usuario,
                resultados,
                erro_llm=erro_decisao,
            )
        except Exception as exc:
            fallback_sem_llm = True
            resposta_final = self._responder_final(
                mensagem_usuario,
                resultados,
                erro_llm=exc,
            )

        return {
            "resposta": resposta_final,
            "tool_calls": resultados,
            "fallback_sem_llm": fallback_sem_llm,
        }

    def _decidir_ferramentas(self, mensagem_usuario: str) -> list[dict[str, Any]]:
        prompt = f"""
Hoje é {date.today().isoformat()}.
Você é o planejador de ferramentas do JARVIS Acadêmico.
Decida quais ferramentas devem ser chamadas para responder ao usuário.

Ferramentas disponíveis:
{json.dumps(TOOL_SPECS, ensure_ascii=False, indent=2)}

Regras obrigatórias:
- A decisão deve ser sua, não use lógica fixa.
- Responda SOMENTE com JSON válido.
- Se nenhuma ferramenta for necessária, responda: []
- Formato: [{{"tool": "nome_da_ferramenta", "args": {{...}}}}]
- Para consultar agenda, use consultar_agenda.
- Para adicionar prova, aula, entrega ou evento, use adicionar_evento.
- Para tarefas, use listar_tarefas, adicionar_tarefa ou concluir_tarefa.
- Para plano/prioridade de estudos, use planejar_estudos; ele já considera dificuldades registradas.
- Para exercícios ou prática, use gerar_exercicios.
- Para iniciar revisão ativa/active recall, use iniciar_revisao.
- Para avaliar a resposta do aluno a uma revisão, use avaliar_resposta_revisao.
- Para registrar ou consultar dificuldades, use registrar_dificuldade ou listar_dificuldades.
- Para dúvidas acadêmicas, explicações, resumos e conceitos de estudo, chame buscar_material_rag primeiro.
- Mesmo que o tema pareça amplo ou não esteja claramente nos materiais, use buscar_material_rag para verificar a base local.
- Se for apenas conversa casual, saudação ou pedido não acadêmico, responda [].

Mensagem do usuário: {mensagem_usuario}
""".strip()
        resposta = self.llm.chat([
            {"role": "system", "content": "Você escolhe ferramentas e responde apenas JSON."},
            {"role": "user", "content": prompt},
        ], temperature=0.0, max_tokens=250)
        return self._extrair_json_lista(resposta)

    def _extrair_json_lista(self, texto: str) -> list[dict[str, Any]]:
        texto = texto.strip()
        if not texto:
            raise ValueError("A LLM retornou uma decisão de ferramentas vazia.")

        try:
            data = json.loads(texto)
            if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
                raise ValueError("A decisão de ferramentas da LLM não é uma lista JSON válida.")
            return data
        except json.JSONDecodeError:
            pass

        match = re.search(r"\[[\s\S]*\]", texto)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, list) and all(isinstance(item, dict) for item in data):
                    return data
            except json.JSONDecodeError:
                pass
        raise ValueError("A LLM retornou uma decisão de ferramentas em formato inválido.")

    def _normalizar_heuristica(self, texto: str) -> str:
        sem_acentos = "".join(
            char
            for char in unicodedata.normalize("NFKD", texto)
            if not unicodedata.combining(char)
        )
        return re.sub(r"\s+", " ", sem_acentos.strip().lower())

    def _parece_pergunta_academica(self, texto: str) -> bool:
        normalizado = self._normalizar_heuristica(texto)
        if not normalizado:
            return False

        frase_simples = normalizado.strip(" ?!.")
        mensagens_casuais = {
            "oi",
            "ola",
            "bom dia",
            "boa tarde",
            "boa noite",
            "obrigado",
            "obrigada",
            "valeu",
            "teste",
            "tudo bem",
            "quem e voce",
            "qual e o seu nome",
            "qual seu nome",
            "como voce esta",
        }
        comandos_interface = (
            "mude a cor",
            "troque a cor",
            "clique aqui",
            "abra a aba",
            "feche a aba",
        )
        if frase_simples in mensagens_casuais or any(
            frase_simples.startswith(comando) for comando in comandos_interface
        ):
            return False

        gatilhos = (
            "o que ",
            "explique",
            "explica",
            "resuma",
            "como funciona",
            "qual a diferenca",
            "quais ",
            "defina",
            "conceitue",
            "me explique",
            "fale sobre",
        )
        termos_academicos = (
            "rag",
            "embedding",
            "embeddings",
            "knn",
            "regressao",
            "logistica",
            "gradiente",
            "heap",
            "busca densa",
            "busca lexical",
            "bm25",
            "faiss",
            "dataset",
            "treinamento",
            "inteligencia artificial",
            "classificacao",
            "similaridade",
            "normalizacao",
            "tool calling",
        )
        tem_gatilho = any(normalizado.startswith(gatilho) for gatilho in gatilhos)
        tem_termo = any(
            re.search(rf"\b{re.escape(termo)}\b", normalizado)
            for termo in termos_academicos
        )
        palavras = re.findall(r"\w+", normalizado)
        return tem_gatilho or tem_termo or (normalizado.endswith("?") and len(palavras) >= 3)

    def _decisoes_fallback_sem_llm(self, mensagem_usuario: str) -> list[dict[str, Any]]:
        if not self._parece_pergunta_academica(mensagem_usuario):
            return []
        return [{
            "tool": "buscar_material_rag",
            "args": {
                "pergunta": mensagem_usuario,
                "metodo": "hibrido",
                "k": 4,
                "sem_llm": True,
            },
        }]

    def _mensagem_erro_segura(self, exc: Exception) -> str:
        texto = str(exc).lower()
        if isinstance(exc, PermissionError):
            return "A autenticação da LLM remota foi recusada. Verifique o Secret GEMMA_API_KEY."
        if isinstance(exc, TimeoutError):
            return "A LLM remota excedeu o tempo limite. Tente novamente em alguns instantes."
        if isinstance(exc, ConnectionError) and ("ssl" in texto or "certif" in texto):
            return "A conexão segura com a LLM remota falhou por SSL ou certificado."
        if isinstance(exc, ConnectionError):
            return "Não foi possível conectar à LLM remota."
        if isinstance(exc, ValueError):
            return "A LLM remota retornou uma decisão de ferramentas inválida."
        return "A LLM remota está indisponível no momento."

    def _metadados_erro_llm(self, exc: Exception) -> dict[str, Any]:
        return {
            "fallback_sem_llm": True,
            "fallback_origem": "decisao_de_ferramentas",
            "erro_llm_etapa": "decisao_de_ferramentas",
            "erro_llm_tipo": type(exc).__name__,
            "erro_llm_mensagem": self._mensagem_erro_segura(exc),
            "llm_provider": getattr(self.llm, "provider", "openai-compatible"),
            "llm_provider_label": getattr(self.llm, "provider_label", ""),
        }

    def _formatar_resposta_rag(self, saida: dict[str, Any]) -> str:
        fontes = sorted({
            d.get("fonte", "")
            for d in saida.get("documentos_recuperados", [])
            if d.get("fonte")
        })
        sufixo = ("\n\nFontes recuperadas: " + ", ".join(fontes)) if fontes else ""
        return str(saida["resposta"]) + sufixo

    def _responder_final(
        self,
        mensagem_usuario: str,
        resultados: list[dict[str, Any]],
        erro_llm: Exception | None = None,
    ) -> str:
        if erro_llm is not None:
            rag = next(
                (
                    item.get("saida")
                    for item in resultados
                    if item.get("tool") == "buscar_material_rag"
                    and isinstance(item.get("saida"), dict)
                ),
                None,
            )
            if rag and not rag.get("resultado_vazio", False) and rag.get("resposta"):
                return self._formatar_resposta_rag(rag)
            if rag:
                return (
                    "Não encontrei esse tema nos materiais cadastrados e a LLM remota está "
                    "indisponível no momento. Importe ou revise materiais sobre esse tema, "
                    "ou tente novamente quando a API LLM estiver disponível."
                )
            return (
                "A LLM remota está indisponível no momento. Posso continuar consultando "
                "materiais acadêmicos quando sua pergunta for sobre o conteúdo da disciplina."
            )

        if not resultados:
            return self.llm.chat([
                {"role": "system", "content": "Você é o JARVIS Acadêmico, um assistente objetivo para estudantes."},
                {"role": "user", "content": mensagem_usuario},
            ])

        # Economia de tokens: se a única ferramenta foi RAG e ela encontrou evidência,
        # devolvemos direto sem chamar a LLM novamente apenas para reescrever.
        # Se o RAG marcou resultado_vazio=True, deixamos a LLM gerar o fallback acadêmico
        # com aviso de fonte, pois nesse caso a resposta vem do conhecimento geral do modelo.
        if (
            len(resultados) == 1
            and resultados[0].get("tool") == "buscar_material_rag"
            and isinstance(resultados[0].get("saida"), dict)
            and resultados[0]["saida"].get("resposta")
            and not resultados[0]["saida"].get("resultado_vazio", False)
        ):
            return self._formatar_resposta_rag(resultados[0]["saida"])

        resultados_compactos = compactar_texto(json.dumps(resultados, ensure_ascii=False), limite=4500)
        prompt = f"""
Responda ao usuário de forma objetiva, acadêmica e útil.
Use os resultados das ferramentas abaixo. Quando houver documentos recuperados, cite o nome da fonte.

Regra de transparência e governança:
- Se a ferramenta buscar_material_rag retornar resultado_vazio=true ou a mensagem "RESULTADO_VAZIO",
  você DEVE iniciar a resposta exatamente com:
  "Não encontrei esse tema nos materiais cadastrados. Vou responder com meu conhecimento geral da base de dados do modelo."
- Depois do aviso, explique o conceito de forma didática usando conhecimento geral da LLM.
- Ao final, sugira que o aluno importe um PDF, anotação ou material sobre o tema para que respostas futuras sejam baseadas no RAG.
- Se houver documentos recuperados com evidência suficiente, baseie a resposta neles e cite as fontes.

Pergunta do usuário:
{mensagem_usuario}

Resultados das ferramentas:
{resultados_compactos}
""".strip()
        return self.llm.chat([
            {"role": "system", "content": "Você é o JARVIS Acadêmico. Integre resultados das ferramentas com transparência sobre a origem da informação."},
            {"role": "user", "content": prompt},
        ], temperature=0.2, max_tokens=450)
