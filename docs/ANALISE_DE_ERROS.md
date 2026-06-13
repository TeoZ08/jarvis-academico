# Análise de erros e decisões de correção

Este documento registra falhas encontradas durante o desenvolvimento do JARVIS Acadêmico e as soluções aplicadas. Ele existe para demonstrar avaliação, tratamento de erros e maturidade de engenharia.

---

## 1. Falha: resposta vazia quando o tema não estava nos materiais

### Sintoma

Perguntas sobre temas fora da base local, como `heap`, retornavam resposta insuficiente ou negativa, mesmo sendo temas acadêmicos relevantes.

### Causa

O RAG estava sendo tratado como única fonte possível de resposta. Quando a recuperação não encontrava documentos relevantes, o assistente ficava limitado.

### Correção

Foi criado o padrão **Fallback Acadêmico com Governança**:

1. o sistema tenta buscar nos materiais;
2. se não houver evidência suficiente, retorna `resultado_vazio`;
3. a resposta começa com um aviso explícito;
4. o modelo usa conhecimento geral para ajudar o aluno;
5. a interface sinaliza que houve fallback.

### Resultado

O aluno não fica sem resposta, mas também não é induzido a acreditar que a informação veio dos documentos locais.

---

## 2. Falha: deploy no Render excedendo memória

### Sintoma

O serviço no Render retornava erro HTTP 502 e foi reiniciado automaticamente por limite de memória.

### Causa

O stack de IA local é pesado para planos gratuitos:

- `torch`;
- `sentence-transformers`;
- modelo de embeddings;
- FAISS;
- indexação em memória.

### Correção

Foi previsto o uso de `RAG_MODE=lexical` em ambientes mais restritos e `RAG_MODE=hibrido` em ambientes com mais memória. Além disso, se o modo híbrido estiver configurado mas as dependências densas (`sentence-transformers`/FAISS) não estiverem disponíveis no ambiente, o RAG cai automaticamente para `lexical_bm25_fallback`.

### Resultado

A arquitetura ficou adaptável ao ambiente de deploy e evita que a ausência de dependências densas derrube `/api/status` ou o fluxo básico de recuperação.

---

## 3. Falha: API key inválida no Hugging Face

### Sintoma

A aplicação retornou:

```text
401 Invalid API token
```

### Causa

A chave da API foi inserida com aspas no campo Secret. Em código Python, aspas delimitam string; no painel de Secrets, elas viram parte do valor.

### Correção

A secret `GEMMA_API_KEY` foi recriada sem aspas, sem prefixo `GEMMA_API_KEY=` e sem espaços extras.

### Resultado

O erro 401 foi eliminado.

---

## 4. Falha: timeout na chamada da LLM

### Sintoma

A aplicação retornava:

```text
Request timed out.
```

### Causa

O tempo de resposta da LLM poderia exceder o limite configurado no cliente.

### Correção

Foram adicionadas variáveis configuráveis:

```env
GEMMA_TIMEOUT_SECONDS=180
GEMMA_MAX_TOKENS=512
```

Também foi criado o endpoint:

```text
/api/debug/gemma-ping
```

para testar a LLM remota sem RAG e sem tool calling.

### Resultado

O teste retornou `OK`, provando que o Hugging Face conseguia acessar a API LLM.

---

## 5. Falha: logs técnicos pouco legíveis

### Sintoma

A aba de logs exibia apenas JSON bruto, dificultando a avaliação visual do requisito de tool calling.

### Causa

O log era útil para auditoria, mas pouco didático para apresentação.

### Correção

Foi criada uma interface de **Evidências Técnicas**, com:

- ferramenta chamada;
- entrada principal;
- método usado;
- top-k;
- melhor score;
- documentos recuperados;
- fallback tratado;
- JSON bruto recolhido em accordion.

### Resultado

A evidência técnica ficou mais clara para avaliação.

---

## 6. Falha: clipe de anexar arquivos sem ação

### Sintoma

O botão de clipe no composer do chat não executava upload.

### Causa

O botão existia visualmente, mas não estava conectado a um input de arquivo.

### Correção

Foi adicionado um input oculto com suporte a múltiplos arquivos e integração com o endpoint `/api/upload`.

### Resultado

Agora é possível anexar materiais diretamente pelo chat e reindexar a base RAG.

---

## 7. Falha: logo sobreposta no menu recolhido

### Sintoma

Ao fechar o menu lateral esquerdo, a logo e o botão de menu ficavam visualmente sobrepostos.

### Causa

O layout recolhido mantinha a distribuição horizontal do menu aberto.

### Correção

O estado recolhido passou a organizar a logo e o botão verticalmente, centralizados.

### Resultado

O menu recolhido ficou limpo e responsivo.

---

## 8. Falha: nomes legados da LLM confundindo o deploy

### Sintoma

O projeto ainda usava mensagens e documentação falando em Gemma, mas o endpoint configurado no Hugging Face apontava para Qwen:

```env
GEMMA_BASE_URL=https://llm.liaufms.org/v1/qwen2-5-14b-instruct-awq
GEMMA_MODEL=Qwen/Qwen2.5-14B-Instruct-AWQ
```

Isso dificultava diagnosticar se uma falha vinha do código, da chave, do endpoint, do modelo ou do ambiente do Space.

### Causa

As variáveis `GEMMA_*` já estavam incorporadas ao código e ao deploy. Elas viraram nomes legados, mas continuavam sendo exibidas como se o provedor atual fosse necessariamente Gemma.

### Correção

O backend passou a tratar `gemma`, `qwen`, `remote` e `openai_compatible` como modos remotos válidos. As mensagens de erro foram neutralizadas para "API LLM", e os endpoints de diagnóstico passaram a retornar:

- provider OpenAI-compatible;
- modelo real configurado;
- presença e tamanho da chave, sem expor o valor;
- base URL configurada;
- tipo e mensagem segura do erro.

### Resultado

O deploy continua compatível com `LLM_MODE=gemma` e `GEMMA_*`, mas a interface e a documentação indicam que esses nomes são legados e que o modelo atual é Qwen.

---

## 9. Falha: RAG inacessível quando a LLM remota falhava

### Sintoma

Uma pergunta como `O que é RAG?` retornava erro 401, timeout ou falha de conexão antes de consultar a base local, mesmo com documentos e chunks carregados.

### Causa

O agente dependia da LLM para decidir a chamada de `buscar_material_rag`. Além disso, o próprio RAG usava a LLM para redigir a resposta após recuperar os documentos.

### Correção

Foi adicionado um fluxo resiliente:

1. falhas técnicas ou JSON inválido na decisão são capturados;
2. uma heurística simples separa perguntas acadêmicas de conversa casual;
3. perguntas acadêmicas executam `buscar_material_rag` diretamente;
4. o RAG apresenta trechos locais sem reescrita quando a LLM não pode ser usada;
5. logs registram `fallback_sem_llm`, etapa, provider e tipo seguro do erro;
6. nenhuma chave ou mensagem técnica bruta é exposta.

### Resultado

O chat não retorna 500 apenas porque a LLM está indisponível. Fontes, scores, tool calls e evidências continuam auditáveis. Se não houver evidência local, a resposta informa simultaneamente a ausência de material e a indisponibilidade da LLM.

---

## 10. Falha: Agenda apenas consultiva

### Sintoma

A aba Agenda exibia eventos, mas não permitia cadastrar aulas, provas, entregas ou revisões manualmente.

### Causa

O endpoint `POST /api/agenda` já existia, porém não estava conectado a um formulário no frontend.

### Correção

Foi criado um formulário responsivo com título, data, horários, tipo e observação. O frontend valida campos obrigatórios e ordem dos horários; a API repete essas validações. Após salvar, a lista e o inspector são atualizados sem recarregar a página.

### Resultado

A Agenda passou a ser um recurso operacional coerente com Tarefas e com a ferramenta de planejamento do JARVIS.
