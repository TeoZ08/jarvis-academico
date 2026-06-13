# Interface Web e Deploy

## Objetivo

A interface final do JARVIS Acadêmico usa **React + Vite** no frontend e **FastAPI** no backend. O objetivo é entregar uma experiência de produto, com chat acadêmico, upload de documentos, agenda, tarefas, revisão ativa e painel de evidências técnicas.

```text
frontend/  -> React, Vite e CSS
web_api/   -> FastAPI
src/       -> RAG, agente, tool calling, agenda, tarefas, revisão e storage
```

---

## Decisão arquitetural

A interface web não acessa diretamente os módulos Python internos. Ela se comunica com o backend por endpoints HTTP.

Principais endpoints:

- `GET /` — abre a interface web compilada.
- `GET /api/status` — mostra modo LLM, documentos, chunks e configuração do RAG.
- `GET /api/debug/gemma-ping` — testa a LLM remota diretamente, sem RAG e sem agente. O nome do endpoint é legado.
- `GET /api/debug/config` — exibe configuração efetiva sem vazar segredos.
- `POST /api/chat` — envia mensagem ao JARVIS.
- `POST /api/upload` — importa documentos e reindexa a base.
- `POST /api/reindex` — força reindexação dos materiais.
- `GET /api/tasks` — lista tarefas.
- `POST /api/tasks` — adiciona tarefa.
- `PATCH /api/tasks/{id}/complete` — conclui tarefa.
- `GET /api/agenda` — lista agenda.
- `POST /api/agenda` — adiciona evento com validação de data e intervalo de horário.
- `GET /api/logs` — exibe logs técnicos.

O frontend usa esses endpoints para manter tarefas, agenda e inspector sincronizados sem recarregar a página. Na Agenda, o usuário pode cadastrar título, data, horários, tipo e observação; o backend exige título/data e rejeita hora final anterior à inicial.

No chat, falhas de autenticação, timeout, conexão ou resposta inválida na etapa de decisão não tornam a base local inacessível. Perguntas acadêmicas acionam o RAG diretamente, e a interface exibe `RAG sem LLM`, fontes, scores e evidências técnicas. Conversas casuais não disparam busca local.

---

## Identidade visual

A direção visual segue a ideia:

```text
Notion clean + painel técnico JARVIS + assistente acadêmico
```

Características:

- fundo escuro sofisticado;
- cards limpos;
- menu lateral;
- chat principal;
- painel direito com status, fontes, ferramentas, agenda, tarefas e logs;
- evidências técnicas visíveis para facilitar a correção do trabalho.
- formulários compactos com feedback textual de sucesso e erro;
- estados distintos para RAG fundamentado, fallback acadêmico e RAG sem LLM.

---

## Deploy oficial

O deploy oficial da entrega é o **Hugging Face Spaces com Docker**.

Link do Space:

```text
https://huggingface.co/spaces/TeoZ08/jarvis-academico
```

Link direto provável do app:

```text
https://teoz08-jarvis-academico.hf.space
```

O `README.md` precisa manter o YAML do Hugging Face na primeira linha absoluta:

```yaml
---
title: JARVIS Acadêmico
emoji: 🧠
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---
```

---

## Variáveis no Hugging Face

Em **Variables**:

```env
LLM_MODE=gemma
GEMMA_BASE_URL=https://llm.liaufms.org/v1/qwen2-5-14b-instruct-awq
GEMMA_MODEL=Qwen/Qwen2.5-14B-Instruct-AWQ
GEMMA_TIMEOUT_SECONDS=180
GEMMA_MAX_TOKENS=512
RAG_MODE=hibrido
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
PYTHONUNBUFFERED=1
```

Em **Secrets**:

```env
GEMMA_API_KEY=sua_chave_aqui
```

A chave deve ser salva sem aspas e sem prefixo `GEMMA_API_KEY=`.

`GEMMA_*` são nomes legados mantidos por compatibilidade. Eles configuram o cliente LLM remoto OpenAI-compatible atual.

---

## Execução local da interface web

Backend:

```bash
source .venv/bin/activate
python -m uvicorn web_api.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Abrir:

```text
http://localhost:5173
```

---

## Observações importantes

- A chave da LLM nunca deve ficar no frontend.
- A chave da LLM nunca deve ser commitada no GitHub.
- `data/uploads/*` deve ser ignorado no Git, mantendo apenas `data/uploads/.gitkeep` se necessário.
- O deploy principal é Hugging Face Spaces; outros provedores não fazem parte do fluxo oficial da entrega.
