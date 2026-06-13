# Design system — JARVIS Acadêmico

## Intent

Usuário principal: aluno de Computação estudando IA e avaliador técnico do trabalho.

Tarefa principal: consultar materiais, conversar com o assistente, organizar estudos e auditar evidências de RAG/tool calling.

Sensação desejada: acadêmico, técnico, autoral, silencioso, premium, cósmico e rastreável.

## Princípios

- A conversa é o centro da experiência.
- Evidências, fontes e ferramentas devem estar sempre próximas da resposta.
- Agenda e tarefas são recursos operacionais: o usuário deve conseguir cadastrar dados, não apenas consultá-los.
- A interface deve parecer produto acadêmico, não dashboard gamer, cripto ou template genérico de IA.
- Estados técnicos devem ser legíveis sem depender só de cor.
- Cards são reservados para unidades independentes; listas e linhas resolvem conteúdo secundário.

## Tokens conceituais

### Cores

- Tema escuro padrão: Charcoal Black `#2B2B2B`, com superfícies grafite-malva `#353238`, `#3E3942` e `#48414E`.
- Tema claro opcional: Porcelain Lavender `#F4F1F5`, com superfícies `#FCFAFD`, `#E7E1E9` e `#DDD6E0`.
- Texto: lavanda quase branco `#F7F3F7` no escuro e Charcoal `#2B2B2B` no claro.
- Marca no escuro: violeta `#8A83DA`, usado em pontos estratégicos da identidade.
- Marca no claro: Deep Mauve `#5D536B`.
- Apoio: Ash Lavender `#A49CA6` para metadados e texto secundário no escuro, não como marca principal.
- Profundidade: Deep Mauve no escuro e Ash Lavender no claro, sempre com contraste suave.
- Semânticas: dourado para aviso, verde somente para sucesso/concluído/online, vermelho seco para erro.

O verde não é identidade visual. RAG, foco, links, avatar, item ativo e botão primário usam a marca do tema atual.
O violeta deve aparecer em aproximadamente 10% da interface visível, concentrado em logo, navegação ativa, labels, RAG, foco, status da LLM e ações principais, sem dominar cards e superfícies grandes.

### Temas

- Primeiro acesso: tema escuro.
- Persistência: `localStorage` com a chave `jarvis-theme`.
- Valores válidos: `dark` e `light`.
- O app não usa automaticamente a preferência do sistema operacional.
- `index.html` aplica o tema antes do React carregar para reduzir flash visual.
- A meta `theme-color` alterna entre `#2B2B2B` e `#F4F1F5`.

### Tipografia

- Display: `Space Grotesk`, com fallback para `Sora` e sans-serif.
- Corpo: `Inter`, com fallback de sistema.
- Técnico: `IBM Plex Mono`, com fallback monospace.

Uso:

- Display em títulos e números.
- Corpo em mensagens, descrições e formulários.
- Mono em labels técnicas, scores, timestamps, modelos, nomes de arquivo e JSON.

### Raios

- `--radius-xl`: superfícies principais.
- `--radius-lg`: painéis e cards independentes.
- `--radius-md`: listas, inputs e elementos técnicos.
- `--radius-pill`: badges e chips.

### Profundidade

Sombras devem aparecer em elementos elevados de verdade: composer, menu mobile, hover e painéis flutuantes. Superfícies fixas usam borda e contraste, não sombra permanente.

### Motion

- Transições entre 150ms e 240ms.
- Hover com deslocamento de 1px a 3px.
- Sem glow pulsante.
- Respeitar `prefers-reduced-motion`.

## Marca

O símbolo aprovado é **F01 / C01 — Convergência orbital**. Ele representa três trajetórias orbitais, múltiplas fontes, síntese, decisão e aprendizagem contínua.

Uso:

- O componente `BrandMark` usa máscara CSS baseada em `frontend/public/brand/jarvis-symbol.svg`.
- No tema escuro, a marca herda o violeta `#8A83DA` via `--brand`.
- No tema claro, a marca herda Deep Mauve via `--brand`.
- `frontend/public/brand/jarvis-symbol-micro.svg` continua disponível para favicon e tamanhos pequenos.
- Não redesenhar o símbolo manualmente no React.
- Não aplicar gradiente, neon ou sombra pulsante dentro do símbolo.

## Assinatura visual

A assinatura do JARVIS é o **Inspector acadêmico**: fontes, ferramentas, tarefas, agenda e logs perto da conversa, com metadados em mono e detalhes malva/lavanda que conectam RAG, tool calling e evidências.

Estados de resiliência usam os mesmos padrões:

- `RAG fundamentado` usa a cor de marca;
- `RAG sem LLM` usa o estado semântico de aviso;
- `LLM indisponível` usa erro controlado no status superior;
- ausência de fontes explica se o RAG ainda não rodou ou se rodou sem evidência suficiente.

O formulário da Agenda reutiliza superfícies, raios, spacing, foco e botão primário existentes. Em mobile, os campos passam para uma coluna e mantêm alvos mínimos de toque.

## Contexto fixo da interface

A área principal do chat deve representar a disciplina inteira:

```text
DISCIPLINA
Inteligência Artificial
Consulte os materiais da disciplina, organize tarefas e acompanhe as fontes usadas em cada resposta.
```

Não usar título fixo que limite o sistema a uma prova específica. A palavra “prova” continua permitida em prompts, tarefas, agenda e objetivos informados pelo usuário.

## Padrões de acessibilidade

- Foco visível em botões, inputs e navegação.
- Alvos de toque mínimos de 44px em mobile.
- Botões de ícone com `title` ou `aria-label`.
- Contraste adequado nos dois temas.
- Sem informação transmitida apenas por cor.
- Feedback de formulários usa texto, `role` apropriado e `aria-live`.
