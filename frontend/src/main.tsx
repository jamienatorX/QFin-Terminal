import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import './styles.css';

type View = 'chat' | 'news' | 'settings';
type DepthMode = 'Quick Mode' | 'Deep Mode';

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  mode?: DepthMode;
  error?: boolean;
};

type NewsItem = {
  id?: string;
  headline?: string;
  sentiment?: string;
  teaser?: string;
  stale?: boolean;
  explanation?: {
    what_happened?: string;
    why_it_matters?: string;
    market_reaction?: string;
  };
  source?: {
    name?: string;
    url?: string;
  };
};

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'https://qfin-terminal.onrender.com';

const FALLBACK_GREETING =
  'Hello, I am QFin Terminal, your AI financial analyst and quantitative finance agent. You can ask me to analyze companies, compare stocks, explain financial ratios, review market risks, generate market news, or answer quant finance questions.';

const FAILURE_MESSAGE =
  'QFin backend health is online, but this chat request did not finish. Render may be waking up, or Qwen/yfinance took too long. Please wait 30 seconds and retry.';

const QUICK_MODE_INSTRUCTION =
  'Quick Mode: write only 3 to 5 short paragraphs, exactly one table or one chart, and a 2 to 3 sentence verdict. Do not include peer comparison, exhaustive risks, full statement breakdown, or multiple visuals.';

const DEEP_MODE_INSTRUCTION =
  'Deep Mode: write a full structured institutional report with Executive Summary, Revenue and Growth, Profitability, Liquidity and Solvency, Cash Flow Quality, Valuation Snapshot, Key Risks, and Final Verdict Table.';

const SUGGESTED_PROMPTS = [
  'Analyze Microsoft',
  'Analyze Bumi Resources',
  'Analyze Alibaba',
  'Analyze NVIDIA thoroughly',
  'Compare AAPL vs MSFT',
  'Explain free cash flow yield'
];

const NEWS_CATEGORIES = ['Stocks', 'Crypto', 'Bonds', 'ETFs', 'Other'];

const ANALYSIS_SIGNAL_PATTERNS = [
  /^(analyze|analyse|review|check|research)\b/i,
  /^(quick analysis|brief|summary|overview)\b/i,
  /^tell me about\b/i,
  /^(how's|hows|how is)\b/i,
  /^compare\b/i
];

function makeId() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function detectDepthMode(text: string): DepthMode {
  const lower = text.toLowerCase();

  const deepSignals = [
    'thoroughly',
    'in-depth',
    'in depth',
    'deep dive',
    'comprehensive',
    'full analysis',
    'detailed',
    'complete breakdown',
    "don't hold back",
    'dont hold back',
    'give me everything'
  ];

  return deepSignals.some((signal) => lower.includes(signal))
    ? 'Deep Mode'
    : 'Quick Mode';
}

function shouldUseAnalysisMode(text: string) {
  return (
    detectDepthMode(text) === 'Deep Mode' ||
    ANALYSIS_SIGNAL_PATTERNS.some((pattern) => pattern.test(text.trim()))
  );
}

function appendModeInstruction(message: string, mode: DepthMode) {
  if (/quick mode:|deep mode:/i.test(message)) {
    return message;
  }

  const instruction =
    mode === 'Deep Mode' ? DEEP_MODE_INSTRUCTION : QUICK_MODE_INSTRUCTION;

  return `${message}. ${instruction}`;
}

function buildBackendMessage(input: string) {
  const clean = input.trim();

  if (!clean || !shouldUseAnalysisMode(clean)) {
    return {
      mode: undefined as DepthMode | undefined,
      message: clean
    };
  }

  const mode = detectDepthMode(clean);

  return {
    mode,
    message: appendModeInstruction(clean, mode)
  };
}

function escapeForRegex(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function sanitizeAssistantText(text: string) {
  return text
    .replace(new RegExp(escapeForRegex(QUICK_MODE_INSTRUCTION), 'gi'), '')
    .replace(new RegExp(escapeForRegex(DEEP_MODE_INSTRUCTION), 'gi'), '')
    .replace(/Quick Mode:\s*/gi, '')
    .replace(/Deep Mode:\s*/gi, '')
    .replace(
      /Do not include peer comparison, exhaustive risks, full statement breakdown, or multiple visuals\./gi,
      ''
    )
    .trim();
}

function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs = 15000
) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  return fetch(url, {
    ...options,
    signal: controller.signal
  }).finally(() => window.clearTimeout(timeoutId));
}

function App() {
  const [view, setView] = useState<View>('chat');

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: makeId(),
      role: 'assistant',
      content: FALLBACK_GREETING
    }
  ]);

  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);

  const [backendStatus, setBackendStatus] = useState('Checking backend...');
  const [backendOnline, setBackendOnline] = useState(false);
  const [qwenConfigured, setQwenConfigured] = useState(false);

  const [selectedMode, setSelectedMode] = useState<DepthMode>('Quick Mode');

  const [newsCategory, setNewsCategory] = useState('Stocks');
  const [news, setNews] = useState<NewsItem[]>([]);
  const [newsLoading, setNewsLoading] = useState(false);
  const [newsError, setNewsError] = useState('');
  const [expandedNewsId, setExpandedNewsId] = useState<string | null>(null);

  const [debugInfo, setDebugInfo] = useState({
    lastUrl: '',
    lastStatus: '',
    lastError: ''
  });

  async function checkBackend() {
    const url = `${API_BASE_URL}/health`;

    setDebugInfo({
      lastUrl: url,
      lastStatus: 'Loading...',
      lastError: ''
    });

    try {
      const response = await fetchWithTimeout(url, {}, 15000);
      const data = await response.json();

      setDebugInfo({
        lastUrl: url,
        lastStatus: `${response.status} ${response.statusText}`,
        lastError: ''
      });

      if (response.ok && data.status === 'ok') {
        setBackendOnline(true);
        setQwenConfigured(Boolean(data.qwen_configured));
        setBackendStatus(
          data.qwen_configured
            ? 'QFin backend connected — Qwen configured'
            : 'QFin backend connected — Qwen not configured'
        );
      } else {
        setBackendOnline(false);
        setBackendStatus('Backend warning');
      }
    } catch (error) {
      setBackendOnline(false);
      setQwenConfigured(false);
      setBackendStatus('Backend offline');

      setDebugInfo({
        lastUrl: url,
        lastStatus: 'Request failed',
        lastError: String(error)
      });
    }
  }

  useEffect(() => {
    checkBackend();
  }, []);

  async function sendToChatStream(displayMessage: string) {
    const cleanDisplayMessage = displayMessage.trim();
    if (!cleanDisplayMessage || loading) return;

    const request = buildBackendMessage(cleanDisplayMessage);
    const assistantId = makeId();
    const url = `${API_BASE_URL}/chat/stream`;

    if (request.mode) {
      setSelectedMode(request.mode);
    }

    setMessages((current) => [
      ...current,
      {
        id: makeId(),
        role: 'user',
        content: cleanDisplayMessage,
        mode: request.mode
      },
      {
        id: assistantId,
        role: 'assistant',
        content: 'Connecting to QFin backend...',
        mode: request.mode
      }
    ]);

    setLoading(true);

    setDebugInfo({
      lastUrl: url,
      lastStatus: 'Loading...',
      lastError: ''
    });

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: request.message
        })
      });

      setDebugInfo({
        lastUrl: url,
        lastStatus: `${response.status} ${response.statusText}`,
        lastError: ''
      });

      if (!response.ok) {
        throw new Error(`Backend returned ${response.status}`);
      }

      let accumulatedText = '';

      if (response.body) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
          const part = await reader.read();

          if (part.done) {
            break;
          }

          accumulatedText += decoder.decode(part.value, { stream: true });

          const visibleText =
            sanitizeAssistantText(accumulatedText) || 'QFin is generating...';

          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    content: visibleText,
                    error: false
                  }
                : message
            )
          );
        }
      } else {
        accumulatedText = await response.text();
      }

      const finalText = accumulatedText.trim()
        ? sanitizeAssistantText(accumulatedText)
        : FALLBACK_GREETING;

      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                content: finalText,
                error: false
              }
            : message
        )
      );
    } catch (error) {
      console.error('QFin backend request failed:', error);

      setDebugInfo({
        lastUrl: url,
        lastStatus: 'Request failed',
        lastError: String(error)
      });

      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                content: FAILURE_MESSAGE,
                error: true
              }
            : message
        )
      );
    } finally {
      setLoading(false);
    }
  }

  function submitPrompt(event?: React.FormEvent) {
    event?.preventDefault();

    const clean = prompt.trim();
    if (!clean) return;

    setPrompt('');
    setView('chat');
    sendToChatStream(clean);
  }

  function runSuggestedPrompt(text: string) {
    setView('chat');
    sendToChatStream(text);
  }

  async function loadNews(category: string) {
    setNewsLoading(true);
    setNewsError('');
    setNews([]);
    setExpandedNewsId(null);

    const primaryUrl = `${API_BASE_URL}/community/news/${encodeURIComponent(
      category
    )}`;
    const fallbackUrl = `${API_BASE_URL}/news/${encodeURIComponent(category)}`;

    try {
      let response = await fetchWithTimeout(primaryUrl, {}, 20000);

      setDebugInfo({
        lastUrl: primaryUrl,
        lastStatus: `${response.status} ${response.statusText}`,
        lastError: ''
      });

      if (!response.ok) {
        response = await fetchWithTimeout(fallbackUrl, {}, 20000);

        setDebugInfo({
          lastUrl: fallbackUrl,
          lastStatus: `${response.status} ${response.statusText}`,
          lastError: ''
        });
      }

      if (!response.ok) {
        throw new Error(`News request failed: ${response.status}`);
      }

      const data = await response.json();
      const items = Array.isArray(data.news) ? data.news.slice(0, 5) : [];

      if (!items.length) {
        throw new Error('Backend returned no news array.');
      }

      setNews(items);
    } catch (error) {
      console.error('QFin news request failed:', error);
      setNewsError('News unavailable. Please retry in a moment.');

      setDebugInfo((current) => ({
        ...current,
        lastError: String(error)
      }));
    } finally {
      setNewsLoading(false);
    }
  }

  useEffect(() => {
    if (view === 'news') {
      loadNews(newsCategory);
    }
  }, [view, newsCategory]);

  return (
    <div className="appShell">
      <aside className="sidebar">
        <div className="brandRow">
          <div className="logo">↗</div>
          <div>
            <h2>QFin</h2>
            <p>TERMINAL</p>
          </div>
        </div>

        <nav className="navList">
          <button
            type="button"
            className={view === 'chat' ? 'navActive' : ''}
            onClick={() => setView('chat')}
          >
            AI Analyst
          </button>

          <button
            type="button"
            className={view === 'news' ? 'navActive' : ''}
            onClick={() => setView('news')}
          >
            Community News
          </button>

          <button
            type="button"
            className={view === 'settings' ? 'navActive' : ''}
            onClick={() => setView('settings')}
          >
            System Status
          </button>
        </nav>

        <div className="securityBox">
          <strong>Backend</strong>
          <p>{backendStatus}</p>
        </div>
      </aside>

      <main className="workspace">
        <section className="hero">
          <div>
            <p className="eyebrow">AI Financial Analyst Dashboard</p>
            <h1>QFin Terminal</h1>
            <p>
              A clean Qwen-powered finance workspace for company analysis,
              market news, valuation thinking, and quantitative finance.
            </p>
          </div>

          <div className="heroActions">
            <button type="button" onClick={checkBackend}>
              Check Backend
            </button>

            <button type="button" onClick={() => setView('news')}>
              Open News
            </button>
          </div>
        </section>

        {view === 'chat' && (
          <>
            <section className="grid">
              <div className="panel">
                <div className="panelHeader">
                  <div>
                    <h3>Ask QFin</h3>
                    <p>
                      Ask for a quick company view, a deep report, a ratio
                      explanation, or a quant finance concept.
                    </p>
                  </div>

                  <span className="pill">{selectedMode}</span>
                </div>

                <form onSubmit={submitPrompt}>
                  <label className="label" htmlFor="prompt">
                    Prompt
                  </label>

                  <textarea
                    id="prompt"
                    className="textarea"
                    value={prompt}
                    onChange={(event) => setPrompt(event.target.value)}
                    placeholder="Example: Analyze Bumi Resources, Analyze Microsoft thoroughly, Explain CAPM..."
                  />

                  <div className="buttonRow">
                    <button
                      type="submit"
                      className="primary"
                      disabled={loading}
                    >
                      {loading ? 'Generating...' : 'Send to QFin'}
                    </button>

                    <button
                      type="button"
                      onClick={() => setPrompt('Analyze Bumi Resources')}
                    >
                      Bumi Resources
                    </button>

                    <button
                      type="button"
                      onClick={() =>
                        setPrompt('Analyze Microsoft thoroughly')
                      }
                    >
                      Deep Report
                    </button>
                  </div>
                </form>

                <div className="tickerGrid">
                  {SUGGESTED_PROMPTS.map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => runSuggestedPrompt(item)}
                      disabled={loading}
                    >
                      {item}
                    </button>
                  ))}
                </div>

                <div className="output">
                  <p className="status">
                    {backendOnline
                      ? 'Backend online'
                      : 'Backend status not confirmed'}
                  </p>

                  {messages.map((message) => (
                    <div
                      key={message.id}
                      className={
                        message.error ? 'reportText errorText' : 'reportText'
                      }
                    >
                      <strong>
                        {message.role === 'user' ? 'You' : 'QFin'}
                        {message.mode ? ` · ${message.mode}` : ''}
                      </strong>
                      {message.content}
                    </div>
                  ))}
                </div>
              </div>

              <aside className="panel stockPanel">
                <h3>Terminal Snapshot</h3>
                <p>
                  This panel confirms which backend and mode your frontend is
                  using.
                </p>

                <div className="metrics">
                  <div>
                    <span>Backend</span>
                    <strong>{API_BASE_URL}</strong>
                  </div>

                  <div>
                    <span>Status</span>
                    <strong>{backendStatus}</strong>
                  </div>

                  <div>
                    <span>Qwen</span>
                    <strong>
                      {qwenConfigured ? 'Configured' : 'Not confirmed'}
                    </strong>
                  </div>

                  <div>
                    <span>Default Analysis</span>
                    <strong>Quick Mode</strong>
                  </div>
                </div>
              </aside>
            </section>

            <div className="disclaimer">
              QFin is for education and financial analysis support only. It is
              not personal investment advice.
            </div>
          </>
        )}

        {view === 'news' && (
          <>
            <section className="grid">
              <div className="panel">
                <div className="panelHeader">
                  <div>
                    <h3>Community News</h3>
                    <p>
                      Pulls backend-generated market news cards from the QFin
                      Render API.
                    </p>
                  </div>

                  <span className="pill">{newsCategory}</span>
                </div>

                <div className="tickerGrid">
                  {NEWS_CATEGORIES.map((category) => (
                    <button
                      key={category}
                      type="button"
                      className={newsCategory === category ? 'primary' : ''}
                      onClick={() => setNewsCategory(category)}
                    >
                      {category}
                    </button>
                  ))}
                </div>

                <div className="buttonRow">
                  <button
                    type="button"
                    className="primary"
                    onClick={() => loadNews(newsCategory)}
                    disabled={newsLoading}
                  >
                    {newsLoading ? 'Loading news...' : 'Refresh News'}
                  </button>
                </div>

                <div className="output">
                  {newsLoading && <p className="status">Loading news...</p>}

                  {newsError && (
                    <p className="reportText errorText">{newsError}</p>
                  )}

                  {!newsLoading &&
                    !newsError &&
                    news.map((item, index) => {
                      const id = item.id || `${item.headline}-${index}`;
                      const expanded = expandedNewsId === id;

                      return (
                        <div key={id} className="reportText">
                          <strong>
                            {item.headline || `Market update ${index + 1}`}
                          </strong>

                          <p>
                            Sentiment:{' '}
                            <b>{item.sentiment || 'Neutral-Watch'}</b>
                          </p>

                          <p>{item.teaser || 'No teaser available.'}</p>

                          {expanded && (
                            <>
                              <p>
                                <b>What happened:</b>{' '}
                                {item.explanation?.what_happened ||
                                  'Not provided.'}
                              </p>

                              <p>
                                <b>Why it matters:</b>{' '}
                                {item.explanation?.why_it_matters ||
                                  'Not provided.'}
                              </p>

                              <p>
                                <b>Market reaction:</b>{' '}
                                {item.explanation?.market_reaction ||
                                  'Not provided.'}
                              </p>

                              {item.source?.url && (
                                <p>
                                  <a
                                    href={item.source.url}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    Source: {item.source.name || 'Open source'}
                                  </a>
                                </p>
                              )}
                            </>
                          )}

                          <button
                            type="button"
                            onClick={() =>
                              setExpandedNewsId(expanded ? null : id)
                            }
                          >
                            {expanded ? 'Show Less' : 'Read More'}
                          </button>
                        </div>
                      );
                    })}
                </div>
              </div>

              <aside className="panel stockPanel">
                <h3>News API</h3>
                <p>Frontend tries both endpoints automatically.</p>

                <div className="metrics">
                  <div>
                    <span>Primary</span>
                    <strong>/community/news/{newsCategory}</strong>
                  </div>

                  <div>
                    <span>Fallback</span>
                    <strong>/news/{newsCategory}</strong>
                  </div>

                  <div>
                    <span>Cards</span>
                    <strong>5 max</strong>
                  </div>
                </div>
              </aside>
            </section>

            <div className="disclaimer">
              News is generated by the backend and may depend on available API
              keys and external data.
            </div>
          </>
        )}

        {view === 'settings' && (
          <section className="grid">
            <div className="panel">
              <div className="panelHeader">
                <div>
                  <h3>System Status</h3>
                  <p>
                    Use this panel to confirm the frontend is calling the
                    correct Render backend.
                  </p>
                </div>

                <span className="pill">
                  {backendOnline ? 'Online' : 'Offline'}
                </span>
              </div>

              <div className="metrics">
                <div>
                  <span>Backend Base URL</span>
                  <strong>{API_BASE_URL}</strong>
                </div>

                <div>
                  <span>Backend Status</span>
                  <strong>{backendStatus}</strong>
                </div>

                <div>
                  <span>Qwen Configured</span>
                  <strong>{qwenConfigured ? 'Yes' : 'Not confirmed'}</strong>
                </div>

                <div>
                  <span>Last URL</span>
                  <strong>{debugInfo.lastUrl || 'None yet'}</strong>
                </div>

                <div>
                  <span>Last Status</span>
                  <strong>{debugInfo.lastStatus || 'None yet'}</strong>
                </div>

                <div>
                  <span>Last Error</span>
                  <strong>{debugInfo.lastError || 'None'}</strong>
                </div>
              </div>

              <div className="buttonRow">
                <button type="button" className="primary" onClick={checkBackend}>
                  Recheck Backend
                </button>

                <button
                  type="button"
                  onClick={() => window.open(`${API_BASE_URL}/health`, '_blank')}
                >
                  Open /health
                </button>

                <button
                  type="button"
                  onClick={() => window.open(`${API_BASE_URL}/debug`, '_blank')}
                >
                  Open /debug
                </button>
              </div>
            </div>

            <aside className="panel stockPanel">
              <h3>Deployment Notes</h3>
              <p>
                If this works locally but not on Vercel, redeploy Vercel after
                committing this file.
              </p>

              <div className="metrics">
                <div>
                  <span>Vercel Root Directory</span>
                  <strong>frontend</strong>
                </div>

                <div>
                  <span>Build Command</span>
                  <strong>npm run build</strong>
                </div>

                <div>
                  <span>Output Directory</span>
                  <strong>dist</strong>
                </div>
              </div>
            </aside>
          </section>
        )}
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
