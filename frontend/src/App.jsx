import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import BrandMark from './components/BrandMark.jsx';
import {
  ArrowRight,
  AlertTriangle,
  BrainCircuit,
  CalendarDays,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileSearch,
  FileText,
  Gauge,
  GitBranch,
  GraduationCap,
  ListTodo,
  Loader2,
  Menu,
  MessageSquareText,
  Moon,
  PanelRightClose,
  PanelRightOpen,
  Paperclip,
  RefreshCcw,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Sun,
  TerminalSquare,
  UploadCloud,
  Zap,
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || '';
const THEME_STORAGE_KEY = 'jarvis-theme';
const THEME_COLORS = {
  dark: '#2B2B2B',
  light: '#F4F1F5',
};

function getInitialTheme() {
  if (typeof window === 'undefined') return 'dark';
  try {
    const saved = window.localStorage.getItem(THEME_STORAGE_KEY);
    return saved === 'light' ? 'light' : 'dark';
  } catch {
    return 'dark';
  }
}

function applyTheme(theme) {
  const resolvedTheme = theme === 'light' ? 'light' : 'dark';
  document.documentElement.dataset.theme = resolvedTheme;
  document.documentElement.style.colorScheme = resolvedTheme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLORS[resolvedTheme]);
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, resolvedTheme);
  } catch {
    // Persistência indisponível no ambiente atual.
  }
}

const quickPrompts = [
  'O que é RAG?',
  'Explique regressão logística.',
  'Monte um plano de estudos para a prova de IA.',
  'Gere 3 exercícios sobre embeddings.',
  'O que é heap?',
];

const formatTime = () => new Intl.DateTimeFormat('pt-BR', {
  hour: '2-digit',
  minute: '2-digit',
}).format(new Date());

async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: options.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...options,
  });

  if (!response.ok) {
    let detail = `Erro HTTP ${response.status}`;
    try {
      const data = await response.json();
      if (Array.isArray(data.detail)) {
        detail = data.detail.map((item) => item.msg || item.message).filter(Boolean).join(' ');
      } else {
        detail = data.detail || detail;
      }
    } catch {
      // mantém erro padrão
    }
    throw new Error(detail);
  }
  return response.json();
}

function extractSources(toolCalls = []) {
  const map = new Map();
  for (const call of toolCalls) {
    const output = call?.saida || {};
    const docs = output.documentos_recuperados || output.materiais_relevantes || [];
    for (const doc of docs) {
      const score = typeof doc.score === 'number' ? doc.score : null;
      if (score !== null && score <= 0.0001) continue;
      const key = doc.id || `${doc.fonte}-${doc.score}`;
      if (!map.has(key)) map.set(key, doc);
    }
  }
  return Array.from(map.values());
}

function humanToolName(tool) {
  const names = {
    buscar_material_rag: 'Busca RAG',
    consultar_agenda: 'Agenda',
    adicionar_evento: 'Novo evento',
    listar_tarefas: 'Tarefas',
    adicionar_tarefa: 'Nova tarefa',
    concluir_tarefa: 'Concluir tarefa',
    planejar_estudos: 'Plano de estudo',
    gerar_exercicios: 'Exercícios',
    iniciar_revisao: 'Revisão ativa',
    avaliar_resposta_revisao: 'Avaliar revisão',
    registrar_dificuldade: 'Registrar dificuldade',
    listar_dificuldades: 'Dificuldades',
  };
  return names[tool] || tool || 'Ferramenta';
}

function inferMode(toolCalls = [], fallbackSemLlm = false) {
  if (fallbackSemLlm && !toolCalls.length) return { label: 'LLM indisponível', tone: 'warning' };
  if (!toolCalls.length) return { label: 'Resposta direta', tone: 'neutral' };
  const hasLlmFallback = toolCalls.some((call) => call?.saida?.fallback_sem_llm);
  const hasEmpty = toolCalls.some((call) => call?.saida?.resultado_vazio);
  const hasRag = toolCalls.some((call) => call?.tool === 'buscar_material_rag');
  if (hasLlmFallback) return { label: 'RAG sem LLM', tone: 'warning' };
  if (hasEmpty) return { label: 'Fallback acadêmico', tone: 'warning' };
  if (hasRag) return { label: 'RAG fundamentado', tone: 'rag' };
  return { label: 'Tool calling', tone: 'info' };
}

function formatScore(score) {
  return typeof score === 'number' ? score.toFixed(3) : '—';
}

function getLlmStatusLabel(status, unavailable = false) {
  if (!status) return 'carregando';
  if (status.usando_mock) return 'mock';
  if (unavailable) return 'LLM indisponível';

  const model = status.llm_provider_label || status.llm_model || status.gemma_model || '';
  if (/qwen/i.test(model)) return 'Qwen remoto';
  if (/gemma/i.test(model)) return 'Gemma remoto';
  return status.llm_provider || status.modo_llm || status.llm_mode || 'LLM remota';
}

function getLlmStatusTitle(status, unavailable = false) {
  if (!status) return 'Carregando status da LLM';
  if (unavailable) return 'A última chamada à LLM falhou; o RAG local continua disponível';
  return [
    status.llm_provider || 'LLM',
    status.llm_provider_label || status.llm_model || status.gemma_model || status.modo_llm,
  ].filter(Boolean).join(' · ');
}

function getLogDocs(log) {
  const output = log?.saida || {};
  return output.documentos_recuperados || output.materiais_relevantes || [];
}

function getLogDiagnostics(log) {
  const output = log?.saida || {};
  const docs = getLogDocs(log);
  const bestScore = docs.reduce((best, doc) => {
    const score = typeof doc.score === 'number' ? doc.score : 0;
    return Math.max(best, score);
  }, 0);

  return {
    docs,
    bestScore,
    isRag: log?.ferramenta === 'buscar_material_rag',
    isLlmFallback: Boolean(output.fallback_sem_llm),
    isFallback: Boolean(output.resultado_vazio) || String(output.resposta || '').includes('Não encontrei esse tema'),
    method: log?.entrada?.metodo || output?.diagnostico_recuperacao?.modo_recuperacao || '—',
    k: log?.entrada?.k || output?.diagnostico_recuperacao?.top_k || '—',
    query: log?.entrada?.pergunta || log?.entrada?.objetivo || log?.entrada?.tema || '—',
  };
}

function getEvidenceMetrics(logs = []) {
  const latest = logs[0] || null;
  const ragCalls = logs.filter((log) => log.ferramenta === 'buscar_material_rag');
  const fallbackCalls = logs.filter((log) => {
    const diagnostics = getLogDiagnostics(log);
    return diagnostics.isFallback || diagnostics.isLlmFallback;
  });
  const tools = new Set(logs.map((log) => log.ferramenta).filter(Boolean));
  const recoveredDocs = logs.reduce((acc, log) => acc + getLogDocs(log).filter((doc) => (doc.score ?? 0) > 0.0001).length, 0);

  return {
    latest,
    ragCalls: ragCalls.length,
    fallbackCalls: fallbackCalls.length,
    toolTypes: tools.size,
    recoveredDocs,
  };
}

const navigationItems = [
  { id: 'chat', label: 'Chat', icon: MessageSquareText },
  { id: 'materiais', label: 'Materiais', icon: Database },
  { id: 'tarefas', label: 'Tarefas', icon: ListTodo },
  { id: 'agenda', label: 'Agenda', icon: CalendarDays },
  { id: 'logs', label: 'Evidências', icon: TerminalSquare },
];

function Sidebar({ active, setActive, collapsed, setCollapsed }) {
  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-top">
        <div className="brand">
          <BrandMark size={38} />
          {!collapsed && (
            <div>
              <strong>JARVIS</strong>
              <span>Acadêmico</span>
            </div>
          )}
        </div>
        <button
          className="icon-button ghost"
          onClick={() => setCollapsed(!collapsed)}
          title="Alternar menu"
          aria-label="Alternar menu lateral"
        >
          <Menu size={18} />
        </button>
      </div>

      <nav className="nav-list">
        {navigationItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              className={`nav-item ${active === item.id ? 'active' : ''}`}
              onClick={() => setActive(item.id)}
              title={collapsed ? item.label : undefined}
              aria-label={item.label}
              aria-current={active === item.id ? 'page' : undefined}
            >
              <Icon size={18} />
              {!collapsed && <span>{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {!collapsed && (
        <div className="sidebar-card">
          <div className="mini-label">Linha de trabalho</div>
          <p>Estudo com fontes, ferramentas e evidências auditáveis.</p>
        </div>
      )}
    </aside>
  );
}

function MobileNav({ active, setActive }) {
  return (
    <nav className="mobile-nav" aria-label="Navegação principal">
      {navigationItems.map((item) => {
        const Icon = item.icon;
        return (
          <button
            key={item.id}
            className={`mobile-nav-item ${active === item.id ? 'active' : ''}`}
            onClick={() => setActive(item.id)}
            aria-label={item.label}
            aria-current={active === item.id ? 'page' : undefined}
          >
            <Icon size={18} />
            <span>{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

function StatusBar({ status, onRefresh, theme, onToggleTheme, llmUnavailable }) {
  const base = status?.base_rag || {};
  const llmStatusClass = status?.usando_mock ? 'mock' : llmUnavailable ? 'unavailable' : 'remote';
  const themeLabel = theme === 'dark' ? 'Usar tema claro' : 'Usar tema escuro';
  return (
    <header className="topbar">
      <div>
        <div className="eyebrow"><Sparkles size={14} /> Espaço de estudo</div>
        <h1>JARVIS Acadêmico</h1>
        <p className="topbar-copy">Consulta, planejamento e evidências em uma única sessão.</p>
      </div>
      <div className="topbar-actions">
        <span className={`status-pill ${llmStatusClass}`} title={getLlmStatusTitle(status, llmUnavailable)}>
          <Gauge size={14} /> {getLlmStatusLabel(status, llmUnavailable)}
        </span>
        <span className="status-pill"><Database size={14} /> {base.chunks ?? 0} chunks</span>
        <button
          className="icon-button theme-toggle"
          onClick={onToggleTheme}
          title={themeLabel}
          aria-label={themeLabel}
          aria-pressed={theme === 'light'}
        >
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </button>
        <button className="icon-button" onClick={onRefresh} title="Atualizar status">
          <RefreshCcw size={16} />
        </button>
      </div>
    </header>
  );
}

function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  const mode = inferMode(message.tool_calls, message.fallback_sem_llm);
  return (
    <article className={`message ${isUser ? 'user' : 'assistant'}`}>
      <div className="message-avatar">
        {isUser ? <GraduationCap size={18} /> : <BrandMark size={30} />}
      </div>
      <div className="message-body">
        <div className="message-meta">
          <strong>{isUser ? 'Você' : 'JARVIS'}</strong>
          <span>{message.time}</span>
          {!isUser && <span className={`mode-badge ${mode.tone}`}>{mode.label}</span>}
        </div>
        <div className="markdown-card">
          {isUser ? (
            <p>{message.content}</p>
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          )}
        </div>
        {!isUser && message.sources?.length > 0 && (
          <div className="source-row">
            {message.sources.slice(0, 3).map((source) => (
              <span key={source.id || source.fonte} className="source-chip">
                <FileText size={13} /> {source.fonte || source.id}
              </span>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

function ChatPanel({ messages, input, setInput, onSubmit, isLoading, onQuickPrompt, refreshAll, onUploadResult }) {
  const messagesAreaRef = useRef(null);
  const fileInputRef = useRef(null);
  const [isUploading, setIsUploading] = useState(false);

  useEffect(() => {
    const messagesArea = messagesAreaRef.current;
    if (!messagesArea) return;
    const frame = requestAnimationFrame(() => {
      messagesArea.scrollTop = messagesArea.scrollHeight;
    });
    return () => cancelAnimationFrame(frame);
  }, [messages, isLoading]);

  async function handleComposerUpload(event) {
    const selectedFiles = Array.from(event.target.files || []);
    if (!selectedFiles.length) return;

    setIsUploading(true);
    try {
      const formData = new FormData();
      selectedFiles.forEach((file) => formData.append('files', file));
      const data = await apiFetch('/api/upload', { method: 'POST', body: formData });
      await refreshAll?.();
      onUploadResult?.(selectedFiles, data, null);
    } catch (error) {
      onUploadResult?.(selectedFiles, null, error);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  return (
    <section className="chat-panel">
      <div className="session-card">
        <div>
          <span className="mini-label">Disciplina</span>
          <h2>Inteligência Artificial</h2>
          <p>Consulte os materiais da disciplina, organize tarefas e acompanhe as fontes usadas em cada resposta.</p>
        </div>
        <div className="session-actions">
          <span><ShieldCheck size={15} /> Governança de fonte</span>
          <span><Zap size={15} /> Modo tutor</span>
        </div>
      </div>

      <div className="quick-row">
        {quickPrompts.map((prompt) => (
          <button key={prompt} className="quick-chip" onClick={() => onQuickPrompt(prompt)}>
            {prompt}
          </button>
        ))}
      </div>

      <div className="messages-area" ref={messagesAreaRef}>
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {isLoading && (
          <article className="message assistant loading">
            <div className="message-avatar"><BrandMark size={30} /></div>
            <div className="message-body">
              <div className="message-meta"><strong>JARVIS</strong><span>pensando...</span></div>
              <div className="typing"><span /><span /><span /></div>
            </div>
          </article>
        )}
      </div>

      <form className="composer" onSubmit={onSubmit}>
        <input
          ref={fileInputRef}
          className="hidden-file-input"
          type="file"
          multiple
          accept=".pdf,.md,.txt,.py"
          onChange={handleComposerUpload}
        />
        <button
          type="button"
          className="composer-icon"
          title="Anexar materiais à base RAG"
          aria-label="Anexar materiais à base RAG"
          disabled={isUploading}
          onClick={() => fileInputRef.current?.click()}
        >
          {isUploading ? <Loader2 className="spin" size={18} /> : <Paperclip size={18} />}
        </button>
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              onSubmit(event);
            }
          }}
          placeholder="Pergunte ao JARVIS sobre seus estudos..."
          rows={1}
        />
        <button className="send-button" disabled={isLoading || !input.trim()} aria-label="Enviar mensagem">
          {isLoading ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
        </button>
      </form>
    </section>
  );
}

function ContextPanel({ selectedMessage, logs, tasks, agenda, status, collapsed, onToggle }) {
  const toolCalls = selectedMessage?.tool_calls || [];
  const sources = selectedMessage?.sources || [];
  const ragExecutado = toolCalls.some((call) => call?.tool === 'buscar_material_rag');
  const eventosRecentes = [...agenda].slice(-2).reverse();

  return (
    <aside className={`context-panel ${collapsed ? 'collapsed' : ''}`} aria-label="Inspector acadêmico">
      <div className="inspector-head">
        <div>
          <span className="mini-label">Inspector</span>
          <h2>Contexto acadêmico</h2>
        </div>
        <button
          className="icon-button ghost"
          onClick={onToggle}
          title={collapsed ? 'Expandir inspector' : 'Recolher inspector'}
          aria-label={collapsed ? 'Expandir inspector acadêmico' : 'Recolher inspector acadêmico'}
        >
          {collapsed ? <PanelRightOpen size={17} /> : <PanelRightClose size={17} />}
        </button>
      </div>

      <section className="context-card glow-card">
        <div className="context-title"><BrainCircuit size={17} /> Estado do sistema</div>
        <div className="metric-grid">
          <div><strong>{status?.base_rag?.documentos ?? 0}</strong><span>docs</span></div>
          <div><strong>{status?.base_rag?.chunks ?? 0}</strong><span>chunks</span></div>
        </div>
      </section>

      <section className="context-card">
        <div className="context-title"><Search size={17} /> Fontes do turno</div>
        {sources.length ? sources.slice(0, 5).map((source) => (
          <div className="source-card" key={source.id || source.fonte}>
            <div><FileText size={15} /> <strong>{source.fonte || source.id}</strong></div>
            <p>{source.texto ? `${source.texto.slice(0, 170)}...` : 'Trecho recuperado pelo RAG.'}</p>
            {typeof source.score === 'number' && <span>score {source.score.toFixed(3)}</span>}
          </div>
        )) : (
          <p className="muted">
            {ragExecutado
              ? 'A busca RAG foi executada, mas não encontrou evidência suficiente para este turno.'
              : 'As fontes recuperadas aparecerão aqui após uma consulta RAG.'}
          </p>
        )}
      </section>

      <section className="context-card">
        <div className="context-title"><TerminalSquare size={17} /> Ferramentas chamadas</div>
        {toolCalls.length ? toolCalls.map((call, index) => (
          <div className="tool-line" key={`${call.tool}-${index}`}>
            <span>{humanToolName(call.tool)}</span>
            <code>{Object.keys(call.args || {}).join(', ') || 'sem args'}</code>
          </div>
        )) : <p className="muted">Quando a LLM usar uma ferramenta, o rastro técnico aparece aqui.</p>}
      </section>

      <section className="context-card compact-list">
        <div className="context-title"><ListTodo size={17} /> Próximas tarefas</div>
        {tasks.slice(0, 3).map((task) => (
          <div className="mini-item" key={task.id}>
            <span>{task.titulo}</span>
            <small>{task.prazo || 'sem prazo'}</small>
          </div>
        ))}
        {!tasks.length && <p className="muted">Nenhuma tarefa pendente.</p>}
      </section>

      <section className="context-card compact-list">
        <div className="context-title"><CalendarDays size={17} /> Agenda</div>
        {eventosRecentes.map((event, index) => (
          <div className="mini-item" key={`${event.data}-${index}`}>
            <span>{event.titulo}</span>
            <small>{event.data} {event.hora_inicio || ''}</small>
          </div>
        ))}
        {!agenda.length && <p className="muted">Nenhum evento encontrado.</p>}
      </section>

      <section className="context-card compact-list">
        <div className="context-title"><GitBranch size={17} /> Últimos logs</div>
        {logs.slice(0, 3).map((log, index) => (
          <div className="mini-item" key={`${log.timestamp}-${index}`}>
            <span>{humanToolName(log.ferramenta)}</span>
            <small>{log.timestamp}</small>
          </div>
        ))}
        {!logs.length && <p className="muted">Sem logs ainda.</p>}
      </section>
    </aside>
  );
}

function MaterialsView({ status, onRefresh }) {
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const inputRef = useRef(null);

  async function upload() {
    if (!files.length) return;
    setUploading(true);
    setResult(null);
    try {
      const formData = new FormData();
      Array.from(files).forEach((file) => formData.append('files', file));
      const data = await apiFetch('/api/upload', { method: 'POST', body: formData });
      setResult(data);
      inputRef.current.value = '';
      setFiles([]);
      onRefresh();
    } catch (error) {
      setResult({ error: error.message });
    } finally {
      setUploading(false);
    }
  }

  const arquivos = status?.base_rag?.arquivos || [];
  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="mini-label">Base de conhecimento</span>
          <h2>Materiais conectados ao JARVIS</h2>
          <p>Importe PDFs, Markdown, textos ou código. O RAG reindexa a base e passa a responder com esses materiais.</p>
        </div>
        <button className="primary-button" onClick={onRefresh}><RefreshCcw size={16} /> Atualizar</button>
      </div>

      <div className="upload-zone">
        <UploadCloud size={30} />
        <h3>Importar documentos</h3>
        <p>Formatos suportados: PDF, MD, TXT e PY.</p>
        <input ref={inputRef} type="file" multiple accept=".pdf,.md,.txt,.py" onChange={(event) => setFiles(event.target.files)} />
        <button className="primary-button" disabled={!files.length || uploading} onClick={upload}>
          {uploading ? <Loader2 className="spin" size={16} /> : <UploadCloud size={16} />}
          Salvar e reindexar
        </button>
        {result && (
          <div className={`result-box ${result.error ? 'error' : 'ok'}`}>
            {result.error ? result.error : `Arquivos salvos: ${result.salvos?.join(', ') || 'nenhum'}`}
          </div>
        )}
      </div>

      <div className="file-grid">
        {arquivos.map((arquivo) => (
          <div className="file-card" key={arquivo}>
            <FileText size={18} />
            <span>{arquivo}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function TasksView({ tasks, refresh }) {
  const [form, setForm] = useState({ titulo: '', prazo: '', disciplina: 'Inteligência Artificial', prioridade: 'alta' });

  async function addTask(event) {
    event.preventDefault();
    if (!form.titulo.trim()) return;
    await apiFetch('/api/tasks', { method: 'POST', body: JSON.stringify(form) });
    setForm({ ...form, titulo: '', prazo: '' });
    refresh();
  }

  async function completeTask(id) {
    await apiFetch(`/api/tasks/${id}/complete`, { method: 'PATCH' });
    refresh();
  }

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="mini-label">Execução</span>
          <h2>Tarefas de estudo</h2>
          <p>Organize pendências e deixe o JARVIS usar esses dados no planejamento.</p>
        </div>
      </div>
      <form className="task-form" onSubmit={addTask}>
        <input placeholder="Nova tarefa" value={form.titulo} onChange={(e) => setForm({ ...form, titulo: e.target.value })} />
        <input type="date" value={form.prazo} onChange={(e) => setForm({ ...form, prazo: e.target.value })} />
        <button className="primary-button"><ArrowRight size={16} /> Adicionar</button>
      </form>
      <div className="list-stack">
        {tasks.map((task) => (
          <div className="list-card" key={task.id}>
            <div>
              <strong>{task.titulo}</strong>
              <span>{task.disciplina} • {task.prazo || 'sem prazo'} • {task.prioridade}</span>
            </div>
            {!task.concluida && (
              <button className="icon-button" onClick={() => completeTask(task.id)} aria-label={`Concluir tarefa ${task.titulo}`}>
                <CheckCircle2 size={18} />
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

const emptyAgendaForm = {
  titulo: '',
  data: '',
  hora_inicio: '',
  hora_fim: '',
  tipo: 'estudo',
  observacao: '',
};

function AgendaView({ agenda, refresh }) {
  const [form, setForm] = useState(emptyAgendaForm);
  const [feedback, setFeedback] = useState(null);
  const [saving, setSaving] = useState(false);

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function addEvent(event) {
    event.preventDefault();
    setFeedback(null);

    if (!form.titulo.trim() || !form.data) {
      setFeedback({ type: 'error', message: 'Informe o título e a data do evento.' });
      return;
    }
    if (form.hora_inicio && form.hora_fim && form.hora_fim < form.hora_inicio) {
      setFeedback({ type: 'error', message: 'A hora final não pode ser anterior à hora inicial.' });
      return;
    }

    setSaving(true);
    try {
      await apiFetch('/api/agenda', {
        method: 'POST',
        body: JSON.stringify({ ...form, titulo: form.titulo.trim(), observacao: form.observacao.trim() }),
      });
      setForm(emptyAgendaForm);
      await refresh?.();
      setFeedback({ type: 'ok', message: 'Evento adicionado à agenda.' });
    } catch (error) {
      setFeedback({ type: 'error', message: error.message });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="mini-label">Rotina</span>
          <h2>Agenda acadêmica</h2>
          <p>Cadastre aulas, provas, entregas e sessões de estudo para o JARVIS considerar no planejamento.</p>
        </div>
      </div>

      <form className="agenda-form" onSubmit={addEvent}>
        <label className="form-field wide">
          <span>Título *</span>
          <input
            value={form.titulo}
            onChange={(event) => updateField('titulo', event.target.value)}
            placeholder="Ex.: Revisão de RAG"
            required
          />
        </label>
        <label className="form-field">
          <span>Data *</span>
          <input
            type="date"
            value={form.data}
            onChange={(event) => updateField('data', event.target.value)}
            required
          />
        </label>
        <label className="form-field">
          <span>Hora inicial</span>
          <input
            type="time"
            value={form.hora_inicio}
            onChange={(event) => updateField('hora_inicio', event.target.value)}
          />
        </label>
        <label className="form-field">
          <span>Hora final</span>
          <input
            type="time"
            value={form.hora_fim}
            min={form.hora_inicio || undefined}
            onChange={(event) => updateField('hora_fim', event.target.value)}
          />
        </label>
        <label className="form-field">
          <span>Tipo</span>
          <select value={form.tipo} onChange={(event) => updateField('tipo', event.target.value)}>
            <option value="aula">Aula</option>
            <option value="prova">Prova</option>
            <option value="entrega">Entrega</option>
            <option value="revisão">Revisão</option>
            <option value="estudo">Estudo</option>
            <option value="outro">Outro</option>
          </select>
        </label>
        <label className="form-field full">
          <span>Observação</span>
          <textarea
            rows={3}
            value={form.observacao}
            onChange={(event) => updateField('observacao', event.target.value)}
            placeholder="Detalhes, materiais ou objetivo da sessão."
          />
        </label>
        <div className="agenda-form-actions full">
          <button className="primary-button" disabled={saving || !form.titulo.trim() || !form.data}>
            {saving ? <Loader2 className="spin" size={16} /> : <CalendarDays size={16} />}
            {saving ? 'Salvando...' : 'Adicionar evento'}
          </button>
          {feedback && (
            <div
              className={`agenda-feedback ${feedback.type}`}
              role={feedback.type === 'error' ? 'alert' : 'status'}
              aria-live="polite"
            >
              {feedback.message}
            </div>
          )}
        </div>
      </form>

      <div className="timeline">
        {agenda.map((event, index) => (
          <div className="timeline-item" key={`${event.data}-${index}`}>
            <div className="timeline-dot" />
            <div>
              <div className="event-title-row">
                <strong>{event.titulo}</strong>
                <span className="event-type">{event.tipo || 'evento'}</span>
              </div>
              <span className="event-meta">
                {event.data} • {event.hora_inicio || 'sem horário'} {event.hora_fim ? `até ${event.hora_fim}` : ''}
              </span>
              {event.observacao && <p>{event.observacao}</p>}
            </div>
          </div>
        ))}
        {!agenda.length && (
          <div className="empty-state">
            <CalendarDays size={28} />
            <strong>Nenhum evento na agenda.</strong>
            <p>Use o formulário acima para cadastrar a próxima aula, prova, entrega ou revisão.</p>
          </div>
        )}
      </div>
    </section>
  );
}

function EvidencePill({ icon: Icon, label, value, tone = 'neutral' }) {
  return (
    <div className={`evidence-pill ${tone}`}>
      <Icon size={17} />
      <div>
        <strong>{value}</strong>
        <span>{label}</span>
      </div>
    </div>
  );
}

function EvidenceCard({ log, index }) {
  const output = log.saida || {};
  const inputData = log.entrada || {};
  const diagnostics = getLogDiagnostics(log);
  const relevantDocs = diagnostics.docs.filter((doc) => (doc.score ?? 0) > 0.0001);
  const resumo = output.resposta || output.status || output.mensagem || 'Saída registrada pela ferramenta.';

  return (
    <article className="evidence-card">
      <div className="evidence-card-head">
        <div>
          <span className="mini-label">Chamada #{index + 1}</span>
          <h3>{humanToolName(log.ferramenta)}</h3>
        </div>
        <span className={`mode-badge ${diagnostics.isLlmFallback || diagnostics.isFallback ? 'warning' : diagnostics.isRag ? 'rag' : 'info'}`}>
          {diagnostics.isLlmFallback
            ? 'RAG sem LLM'
            : diagnostics.isFallback
              ? 'fallback tratado'
              : diagnostics.isRag
                ? 'RAG executado'
                : 'ferramenta executada'}
        </span>
      </div>

      <div className="evidence-grid">
        <div className="evidence-field wide">
          <span>Entrada principal</span>
          <strong>{diagnostics.query}</strong>
        </div>
        <div className="evidence-field">
          <span>Método</span>
          <strong>{diagnostics.method}</strong>
        </div>
        <div className="evidence-field">
          <span>Top-k</span>
          <strong>{diagnostics.k}</strong>
        </div>
        <div className="evidence-field">
          <span>Melhor score</span>
          <strong>{formatScore(diagnostics.bestScore)}</strong>
        </div>
        <div className="evidence-field">
          <span>Docs úteis</span>
          <strong>{relevantDocs.length}</strong>
        </div>
      </div>

      {diagnostics.isLlmFallback && (
        <div className="warning-box">
          <AlertTriangle size={17} />
          <span>
            A LLM remota falhou na etapa {output.erro_llm_etapa || 'de geração'}.
            O RAG local foi executado automaticamente e preservou as evidências recuperadas.
          </span>
        </div>
      )}

      {diagnostics.isFallback && !diagnostics.isLlmFallback && (
        <div className="warning-box">
          <AlertTriangle size={17} />
          <span>Busca executada, mas sem evidência suficiente nos materiais. O JARVIS acionou fallback acadêmico com aviso de fonte.</span>
        </div>
      )}

      {relevantDocs.length > 0 && (
        <div className="evidence-sources">
          <h4>Fontes recuperadas</h4>
          {relevantDocs.slice(0, 4).map((doc) => (
            <div className="evidence-source" key={doc.id || `${doc.fonte}-${doc.score}`}>
              <div>
                <FileSearch size={15} />
                <strong>{doc.fonte || doc.id}</strong>
              </div>
              <span>score {formatScore(doc.score)}</span>
              <p>{doc.texto ? `${doc.texto.slice(0, 210)}...` : 'Trecho recuperado pelo RAG.'}</p>
            </div>
          ))}
        </div>
      )}

      <div className="evidence-summary">
        <span>Resumo da saída</span>
        <p>{String(resumo).slice(0, 520)}{String(resumo).length > 520 ? '...' : ''}</p>
      </div>

      <details className="raw-json">
        <summary>Ver JSON técnico bruto</summary>
        <pre>{JSON.stringify({ timestamp: log.timestamp, ferramenta: log.ferramenta, entrada: inputData, saida: output }, null, 2)}</pre>
      </details>
    </article>
  );
}

function LogsView({ logs }) {
  const metrics = getEvidenceMetrics(logs);

  return (
    <section className="workspace-view evidence-view">
      <div className="view-header">
        <div>
          <span className="mini-label">Evidência técnica</span>
          <h2>Painel de avaliação do tool calling</h2>
          <p>Resumo legível das ferramentas chamadas, recuperação RAG, fontes, scores e tratamento de erro. O JSON bruto continua disponível para auditoria.</p>
        </div>
      </div>

      <div className="rubric-grid">
        <EvidencePill icon={Search} label="chamadas RAG" value={metrics.ragCalls} tone="rag" />
        <EvidencePill icon={TerminalSquare} label="tipos de ferramenta" value={metrics.toolTypes} tone="info" />
        <EvidencePill icon={FileText} label="fontes recuperadas" value={metrics.recoveredDocs} tone="neutral" />
        <EvidencePill icon={ShieldCheck} label="fallbacks tratados" value={metrics.fallbackCalls} tone="warning" />
      </div>

      <div className="rubric-card">
        <div className="context-title"><ClipboardCheck size={18} /> Critérios evidenciados</div>
        <div className="criterion-list">
          <span><CheckCircle2 size={15} /> RAG com documentos, chunks e scores</span>
          <span><CheckCircle2 size={15} /> Tool calling com entrada e saída</span>
          <span><CheckCircle2 size={15} /> Integração real com LLM remota via API</span>
          <span><CheckCircle2 size={15} /> Erros e fallback acadêmico controlados</span>
        </div>
      </div>

      <div className="log-stack">
        {logs.map((log, index) => (
          <EvidenceCard log={log} index={index} key={`${log.timestamp}-${index}`} />
        ))}
        {!logs.length && (
          <div className="empty-state">
            <TerminalSquare size={28} />
            <strong>Nenhuma ferramenta registrada ainda.</strong>
            <p>Faça uma pergunta como “O que é RAG?” para gerar evidências de recuperação e tool calling.</p>
          </div>
        )}
      </div>
    </section>
  );
}

function ChatWorkspace({ active, ...props }) {
  if (active === 'materiais') return <MaterialsView status={props.status} onRefresh={props.refreshAll} />;
  if (active === 'tarefas') return <TasksView tasks={props.tasks} refresh={props.refreshAll} />;
  if (active === 'agenda') return <AgendaView agenda={props.agenda} refresh={props.refreshAll} />;
  if (active === 'logs') return <LogsView logs={props.logs} />;
  return <ChatPanel {...props} />;
}

export default function App() {
  const [theme, setTheme] = useState(getInitialTheme);
  const [active, setActive] = useState('chat');
  const [collapsed, setCollapsed] = useState(false);
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);
  const [status, setStatus] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [agenda, setAgenda] = useState([]);
  const [logs, setLogs] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      role: 'assistant',
      time: formatTime(),
      content: 'Olá! Eu sou o **JARVIS Acadêmico**. Posso consultar seus materiais, montar planos de estudo, gerar exercícios e registrar as ferramentas usadas em cada resposta.',
      tool_calls: [],
      sources: [],
    },
  ]);

  const selectedMessage = useMemo(() => {
    return [...messages].reverse().find((msg) => msg.role === 'assistant') || null;
  }, [messages]);
  const llmUnavailable = Boolean(selectedMessage?.fallback_sem_llm)
    || selectedMessage?.tool_calls?.some((call) => call?.saida?.fallback_sem_llm);

  async function refreshAll() {
    try {
      const [statusData, taskData, agendaData, logData] = await Promise.all([
        apiFetch('/api/status'),
        apiFetch('/api/tasks'),
        apiFetch('/api/agenda'),
        apiFetch('/api/logs?limit=20'),
      ]);
      setStatus(statusData);
      setTasks(taskData || []);
      setAgenda(agendaData || []);
      setLogs(logData.items || []);
    } catch (error) {
      console.error(error);
    }
  }

  useEffect(() => {
    refreshAll();
  }, []);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  function toggleTheme() {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'));
  }

  async function submitMessage(event) {
    event?.preventDefault();
    const text = input.trim();
    if (!text || isLoading) return;

    setInput('');
    setActive('chat');
    const userMessage = { id: crypto.randomUUID(), role: 'user', content: text, time: formatTime() };
    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      const data = await apiFetch('/api/chat', {
        method: 'POST',
        body: JSON.stringify({ mensagem: text }),
      });
      const sources = extractSources(data.tool_calls || []);
      const assistantMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: data.resposta || 'Sem resposta retornada.',
        time: formatTime(),
        tool_calls: data.tool_calls || [],
        sources,
        fallback_sem_llm: Boolean(data.fallback_sem_llm),
      };
      setMessages((prev) => [...prev, assistantMessage]);
      refreshAll();
    } catch (error) {
      setMessages((prev) => [...prev, {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `### Erro controlado\n${error.message}`,
        time: formatTime(),
        tool_calls: [],
        sources: [],
      }]);
    } finally {
      setIsLoading(false);
    }
  }

  function onQuickPrompt(prompt) {
    setInput(prompt);
    setActive('chat');
  }

  function handleUploadResult(files, result, error) {
    const fileNames = files.map((file) => file.name).join(', ');
    const content = error
      ? `### Erro ao importar material\n${error.message}`
      : `### Materiais importados com sucesso\nArquivos enviados: **${fileNames}**.\n\nA base RAG foi reindexada e os novos documentos já podem ser consultados pelo JARVIS.`;

    setMessages((prev) => [...prev, {
      id: crypto.randomUUID(),
      role: 'assistant',
      content,
      time: formatTime(),
      tool_calls: [],
      sources: [],
    }]);
    setActive('chat');
  }

  return (
    <div className="app-shell">
      <Sidebar active={active} setActive={setActive} collapsed={collapsed} setCollapsed={setCollapsed} />
      <main className="main-area">
        <StatusBar
          status={status}
          onRefresh={refreshAll}
          theme={theme}
          onToggleTheme={toggleTheme}
          llmUnavailable={llmUnavailable}
        />
        <div className={`workspace-grid ${inspectorCollapsed ? 'inspector-collapsed' : ''}`}>
          <ChatWorkspace
            active={active}
            messages={messages}
            input={input}
            setInput={setInput}
            onSubmit={submitMessage}
            isLoading={isLoading}
            onQuickPrompt={onQuickPrompt}
            status={status}
            tasks={tasks}
            agenda={agenda}
            logs={logs}
            refreshAll={refreshAll}
            onUploadResult={handleUploadResult}
          />
          <ContextPanel
            selectedMessage={selectedMessage}
            logs={logs}
            tasks={tasks}
            agenda={agenda}
            status={status}
            collapsed={inspectorCollapsed}
            onToggle={() => setInspectorCollapsed((current) => !current)}
          />
        </div>
      </main>
      <MobileNav active={active} setActive={setActive} />
    </div>
  );
}
