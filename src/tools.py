from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

from .learning import LearningService
from .logger import registrar_tool_call
from .rag import RagEngine
from .storage import (
    AgendaStore,
    Dificuldade,
    DificuldadeStore,
    EventoAgenda,
    Revisao,
    RevisaoStore,
    Tarefa,
    TarefaStore,
)


TOOL_SPECS = [
    {
        "name": "consultar_agenda",
        "description": "Consulta eventos da agenda acadêmica por período ou termo.",
        "args": {
            "inicio": "Data inicial no formato AAAA-MM-DD, opcional.",
            "fim": "Data final no formato AAAA-MM-DD, opcional.",
            "termo": "Termo de busca, opcional. Exemplo: prova, aula, IA.",
        },
    },
    {
        "name": "adicionar_evento",
        "description": "Adiciona um evento acadêmico à agenda, como prova, aula, entrega ou reunião.",
        "args": {
            "data": "Data no formato AAAA-MM-DD.",
            "titulo": "Título ou descrição do evento.",
            "hora_inicio": "Horário inicial opcional, como 19:00.",
            "hora_fim": "Horário final opcional, como 21:00.",
            "tipo": "Tipo do evento: aula, prova, estudo, entrega etc.",
            "observacao": "Observação opcional.",
        },
    },
    {
        "name": "listar_tarefas",
        "description": "Lista tarefas acadêmicas pendentes ou todas as tarefas.",
        "args": {"incluir_concluidas": "booleano; false para mostrar apenas pendentes."},
    },
    {
        "name": "adicionar_tarefa",
        "description": "Adiciona uma nova tarefa acadêmica.",
        "args": {
            "titulo": "Descrição curta da tarefa.",
            "prazo": "Prazo no formato AAAA-MM-DD, opcional.",
            "disciplina": "Nome da disciplina, opcional.",
            "prioridade": "baixa, média ou alta.",
        },
    },
    {
        "name": "concluir_tarefa",
        "description": "Marca uma tarefa como concluída pelo id ou parte do título.",
        "args": {"tarefa_id_ou_titulo": "id ou trecho do título da tarefa."},
    },
    {
        "name": "buscar_material_rag",
        "description": "Busca informações nos materiais acadêmicos locais usando RAG. Use para verificar se um conceito está nos documentos do aluno. Se o tema não estiver na base, a ferramenta retorna RESULTADO_VAZIO para permitir fallback acadêmico transparente.",
        "args": {
            "pergunta": "Pergunta acadêmica ou conceito que deve ser verificado nos documentos locais.",
            "metodo": "bm25, dense ou hibrido. Padrão: hibrido.",
            "k": "Quantidade de chunks recuperados. Padrão: 3.",
        },
    },
    {
        "name": "gerar_exercicios",
        "description": "Gera exercícios de estudo com base em um tema e nos materiais do RAG.",
        "args": {"tema": "Tema acadêmico.", "quantidade": "Número de exercícios. Padrão: 3."},
    },
    {
        "name": "iniciar_revisao",
        "description": "Inicia uma sessão de revisão ativa: gera uma pergunta com base no RAG e salva um review_id para avaliação posterior.",
        "args": {
            "disciplina": "Disciplina de foco. Padrão: Inteligência Artificial.",
            "tema": "Tema específico da revisão, opcional. Exemplo: RAG, BM25, KNN.",
        },
    },
    {
        "name": "avaliar_resposta_revisao",
        "description": "Avalia a resposta do aluno para uma pergunta de revisão ativa e registra dificuldade quando a resposta for parcial ou incorreta.",
        "args": {
            "resposta_aluno": "Resposta escrita pelo aluno.",
            "review_id": "ID da revisão. Opcional: se ausente, usa a revisão pendente mais recente.",
        },
    },
    {
        "name": "registrar_dificuldade",
        "description": "Registra manualmente uma dificuldade do aluno para personalizar planos de estudo futuros.",
        "args": {
            "disciplina": "Disciplina associada.",
            "topico": "Tópico de dificuldade.",
            "observacao": "Observação opcional.",
        },
    },
    {
        "name": "listar_dificuldades",
        "description": "Lista dificuldades registradas pelo aluno ou pelo avaliador de revisão.",
        "args": {
            "disciplina": "Filtro opcional de disciplina.",
            "limite": "Quantidade máxima de itens. Padrão: 10.",
        },
    },
    {
        "name": "planejar_estudos",
        "description": "Monta plano de estudos combinando agenda, tarefas, dificuldades registradas e materiais recuperados por RAG.",
        "args": {
            "objetivo": "Objetivo do estudo. Exemplo: prova de IA.",
            "dias": "Quantidade de dias do plano. Padrão: 3.",
        },
    },
]


class ToolRegistry:
    def __init__(self, rag: RagEngine | None = None) -> None:
        self.agenda = AgendaStore()
        self.tarefas = TarefaStore()
        self.dificuldades = DificuldadeStore()
        self.revisoes = RevisaoStore()
        self.rag = rag or RagEngine(carregar_agora=True)
        self.learning = LearningService(self.rag)
        self.funcoes: dict[str, Callable[..., Any]] = {
            "consultar_agenda": self.consultar_agenda,
            "adicionar_evento": self.adicionar_evento,
            "listar_tarefas": self.listar_tarefas,
            "adicionar_tarefa": self.adicionar_tarefa,
            "concluir_tarefa": self.concluir_tarefa,
            "buscar_material_rag": self.buscar_material_rag,
            "gerar_exercicios": self.gerar_exercicios,
            "iniciar_revisao": self.iniciar_revisao,
            "avaliar_resposta_revisao": self.avaliar_resposta_revisao,
            "registrar_dificuldade": self.registrar_dificuldade,
            "listar_dificuldades": self.listar_dificuldades,
            "planejar_estudos": self.planejar_estudos,
        }

    def executar(
        self,
        nome: str,
        argumentos: dict[str, Any],
        metadados_saida: dict[str, Any] | None = None,
    ) -> Any:
        if nome not in self.funcoes:
            raise ValueError(f"Ferramenta desconhecida: {nome}")
        try:
            saida = self.funcoes[nome](**argumentos)
        except TypeError as exc:
            raise ValueError(f"Argumentos inválidos para {nome}: {argumentos}") from exc
        if metadados_saida and isinstance(saida, dict):
            saida = {**saida, **metadados_saida}
        registrar_tool_call(nome, argumentos, saida)
        return saida

    def consultar_agenda(self, inicio: str | None = None, fim: str | None = None, termo: str | None = None) -> list[dict]:
        return self.agenda.consultar(inicio=inicio, fim=fim, termo=termo)

    def adicionar_evento(
        self,
        data: str,
        titulo: str,
        hora_inicio: str = "",
        hora_fim: str = "",
        tipo: str = "aula",
        observacao: str = "",
    ) -> dict:
        return self.agenda.adicionar(
            EventoAgenda(
                data=data,
                titulo=titulo,
                hora_inicio=hora_inicio,
                hora_fim=hora_fim,
                tipo=tipo,
                observacao=observacao,
            )
        )

    def listar_tarefas(self, incluir_concluidas: bool = False) -> list[dict]:
        return self.tarefas.listar(incluir_concluidas=incluir_concluidas)

    def adicionar_tarefa(self, titulo: str, prazo: str = "", disciplina: str = "", prioridade: str = "média") -> dict:
        return self.tarefas.adicionar(Tarefa(titulo=titulo, prazo=prazo, disciplina=disciplina, prioridade=prioridade))

    def concluir_tarefa(self, tarefa_id_ou_titulo: str) -> dict:
        return self.tarefas.concluir(tarefa_id_ou_titulo)

    def buscar_material_rag(
        self,
        pergunta: str,
        metodo: str = "hibrido",
        k: int = 3,
        sem_llm: bool = False,
    ) -> dict:
        return self.rag.responder(
            pergunta=pergunta,
            metodo=metodo,
            k=int(k),
            usar_llm=not bool(sem_llm),
        )

    def gerar_exercicios(self, tema: str, quantidade: int = 3) -> dict:
        pergunta = f"Explique os principais conceitos sobre {tema} para criar exercícios."
        resultado = self.rag.responder(pergunta=pergunta, metodo="hibrido", k=3)
        contexto = resultado["resposta"]
        return {
            "tema": tema,
            "quantidade": int(quantidade),
            "base_para_exercicios": contexto,
            "resultado_vazio": resultado.get("resultado_vazio", False),
            "documentos_recuperados": resultado["documentos_recuperados"],
        }

    def iniciar_revisao(self, disciplina: str = "Inteligência Artificial", tema: str = "") -> dict:
        gerada = self.learning.gerar_pergunta_revisao(disciplina=disciplina, tema=tema)
        if not gerada.get("ok"):
            return gerada

        revisao = self.revisoes.criar(
            Revisao(
                disciplina=disciplina,
                tema=gerada.get("tema", tema or disciplina),
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
            "instrucoes": "Responda à pergunta e depois peça para avaliar usando este review_id, ou diga 'avalie minha resposta' se for a revisão pendente mais recente.",
            "fontes": revisao["fontes"],
        }

    def avaliar_resposta_revisao(self, resposta_aluno: str, review_id: str = "") -> dict:
        revisao = self.revisoes.obter(review_id or None)
        avaliacao = self.learning.avaliar_resposta(
            pergunta=revisao["pergunta"],
            contexto=revisao["contexto"],
            resposta_aluno=resposta_aluno,
        )
        atualizada = self.revisoes.registrar_avaliacao(revisao["id"], avaliacao)

        if avaliacao.get("status") in {"PARTIAL", "INCORRECT"}:
            self.dificuldades.adicionar(
                Dificuldade(
                    disciplina=revisao.get("disciplina", "Inteligência Artificial"),
                    topico=str(avaliacao.get("topic", "Revisão geral")),
                    origem="avaliacao_revisao",
                    observacao=str(avaliacao.get("feedback", "")),
                )
            )

        return {
            "ok": True,
            "review_id": revisao["id"],
            "pergunta": revisao["pergunta"],
            "avaliacao": avaliacao,
            "revisao": atualizada,
        }

    def registrar_dificuldade(self, disciplina: str, topico: str, observacao: str = "") -> dict:
        return self.dificuldades.adicionar(
            Dificuldade(disciplina=disciplina, topico=topico, origem="manual", observacao=observacao)
        )

    def listar_dificuldades(self, disciplina: str | None = None, limite: int = 10) -> list[dict]:
        return self.dificuldades.listar(disciplina=disciplina, limite=int(limite))

    def planejar_estudos(self, objetivo: str, dias: int = 3) -> dict:
        hoje = date.today()
        fim = hoje + timedelta(days=int(dias))
        eventos = self.agenda.consultar(inicio=hoje.isoformat(), fim=fim.isoformat())
        tarefas = self.tarefas.listar(incluir_concluidas=False)
        dificuldades = self.dificuldades.listar(limite=8)
        query_materiais = objetivo
        if dificuldades:
            topicos = " ".join(d.get("topico", "") for d in dificuldades[:4])
            query_materiais = f"{objetivo} {topicos}"
        materiais = self.rag.buscar(query_materiais, metodo="hibrido", k=5)
        return {
            "objetivo": objetivo,
            "periodo": {"inicio": hoje.isoformat(), "fim": fim.isoformat()},
            "agenda": eventos,
            "tarefas_pendentes": tarefas,
            "dificuldades_recentes": dificuldades,
            "materiais_relevantes": materiais,
            "criterio_personalizacao": "Plano considera agenda, tarefas pendentes, dificuldades registradas e materiais recuperados por RAG.",
        }
