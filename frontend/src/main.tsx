import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import './styles.css';

type View = 'chat' | 'analyze' | 'news';
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
  'Hello, I am QFin Terminal, your AI financial analyst and quantitative finance agent. You are welcome to ask me to analyze a company, compare stocks, explain financial ratios, build a valuation view, review risks, generate market news, or answer quant finance questions.';

const SUGGESTED_PROMPTS = [
  'Analyze Microsoft',
  'Analyze TSLA',
  'Compare Nvidia and AMD',
  'Explain VaR',
  'Explain CAPM',
  'Show Crypto news',
  'Analyze Bumi Resources'
];

const QUICK_COMPANIES = ['Microsoft', 'TSLA', 'Nvidia', 'AMD', 'Bumi Resources'];
const NEWS_CATEGORIES = ['Stocks', 'Crypto', 'Bonds', 'ETFs', 'Other'];

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

function buildAnalysisMessage(companyOrRequest: string) {
  const mode = detectDepthMode(companyOrRequest);
  const clean = companyOrRequest.trim();

  const baseMessage = /^(analyze|analyse|review|check|research)\b/i.test(clean)
    ? clean
    : `analyze ${clean}`;

  if (mode === 'Deep Mode') {
    return {
      mode,
      message:
        `${baseMessage}. Deep Mode: write a full structured institutional report with Executive Summary, Revenue and Growth, Profitability, Liquidity and Solvency, Cash Flow Quality, Valuation Snapshot, Key Risks, and Final Verdict Table.`
    };
  }

  return {
    mode,
    message:
      `${baseMessage}. Quick Mode: write only 3 to 5 short paragraphs, exactly one table or one chart, and a 2 to 3 sentence verdict. Do not include peer comparison, exhaustive risks, full statement breakdown, or multiple visuals.`
  };
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

  const [chatInput, setChatInput] = useState('');
  const [companyInput, setCompanyInput] = useState('');
  const [loading, setLoading] = useState(false);

  const [backendStatus, setBackendStatus] = useState('Checking backend...');
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
      const response = await fetch(url);
      const data = await response.json();

      setDebugInfo({
        lastUrl: url,
        lastStatus: `${response.status} ${response.statusText}`,
        lastError: ''
      });

      if (response.ok && data.status === 'ok') {
        setBackendStatus(
          data.qwen_configured ? 'QFin Online — Qwen Configured' : 'QFin Online — Qwen Not Configured'
        );
      } else {
        setBackendStatus('Backend Warning');
      }
    } catch (error) {
      setBackendStatus('Backend Offline');

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

  async function sendToChatStream(userMessage: string, mode?: DepthMode) {
    const cleanMessage = userMessage.trim();
    if (!cleanMessage || loading) return;

    const url = `${API_BASE_URL}/chat/stream`;
    const assistantId = makeId();

    setMessages((current) => [
      ...current,
      {
        id: makeId(),
        role: 'user',
        content: cleanMessage,
        mode
      },
      {
        id: assistantId,
        role: 'assistant',
        content: 'QFin is generating...',
        mode
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
          message: cleanMessage
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

      const text = await response.text();

      const finalText = text.trim() ? text : FALLBACK_GREETING;

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
                content:
                  'Analysis request failed. Backend did not return a response. Please check Render backend health or retry.',
                error: true
              }
            : message
        )
      );
    } finally {
      setLoading(false);
    }
  }

  function submitChat(event?: React.FormEvent) {
    event?.preventDefault();

    const text = chatInput;
    setChatInput('');

    sendToChatStream(text);
  }

  function runCompanyAnalysis(input: string) {
    const clean = input.trim();
    if (!clean) return;

    const result = buildAnalysisMessage(clean);

    setSelectedMode(result.mode);
    setView('chat');

    sendToChatStream(result.message, result.mode);
  }

  async function loadNews(category: string) {
    setNewsLoading(true);
    setNewsError('');
    setNews([]);

    const primaryUrl = `${API_BASE_URL}/community/news/${encodeURIComponent(category)}`;
    const fallbackUrl = `${API_BASE_URL}/news/${encodeURIComponent(category)}`;

    try {
      let response = await fetch(primaryUrl);

      setDebugInfo({
        lastUrl: primaryUrl,
        lastStatus: `${response.status} ${response.statusText}`,
        lastError: ''
      });

      if (!response.ok) {
        response = await fetch(fallbackUrl);

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
      setNewsError('News unavailable. Please retry.');

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
            <h2>QFin Terminal</h2>
            <p>Qwen financial analyst</p>
          </div>
        </div>

        <nav className="navList">
          <button
            type="button"
            className={view === 'chat' ? 'navActive' : ''}
            onClick={() => setView('chat')}
          >
            AI Chat
          </button>

          <button
            type="button"
            className={view === 'analyze' ? 'navActive' : ''}
            onClick={() => setView('analyze')}
          >
            Analyze Company
          </button>

          <button
            type="button"
            className={view === 'news' ? 'navActive' : ''}
            onClick={() => setView('news')}
          >
            Community News
          </button>

          <button type="button" onClick={() => alert('Portfolio coming soon.')}>
            Portfolio
          </button>

          <button type="button" onClick={() => alert('Report Vault coming soon.')}>
            Report Vault
          </button>
        </nav>

        <div className="securityBox">
          <strong>Grounded AI</strong>
          <p>Qwen is called only from the backend. Not investment advice.</p>
        </div>
      </aside>

      <main className="workspace">
        <header className="hero">
          <div>
            <p className="eyebrow">QFin Terminal</p>
            <h1>
              {view === 'chat' && 'AI Financial Analyst'}
              {view === 'analyze' && 'Company Analysis'}
              {view === 'news' && 'Community News'}
            </h1>
            <p>{backendStatus}</p>
          </div>

          <div className="heroActions">
            <button type="button" onClick={checkBackend}>
              Check Backend
            </button>
            <button
              type="button"
              onClick={() =>
                setMessages([
                  {
                    id: makeId(),
                    role: 'assistant',
                    content: FALLBACK_GREETING
                  }
                ])
              }
            >
              New Chat
            </button>
          </div>
        </header>

        {view === 'chat' && (
          <section className="grid">
            <section className="panel">
              <div className="panelHeader">
                <div>
                  <h3>Ask QFin</h3>
                  <p>Uses POST /chat/stream and reads plain text.</p>
                </div>
                <span className="pill">{API_BASE_URL}</span>
              </div>

              <div className="tickerGrid">
                {SUGGESTED_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => sendToChatStream(prompt)}
                  >
                    {prompt}
                  </button>
                ))}
              </div>

              <div className="output">
                <p className="status">Status: {loading ? 'Generating' : 'Ready'}</p>

                {messages.map((message) => (
                  <div key={message.id} className="reportText" style={{ marginBottom: 18 }}>
                    <strong>
                      {message.role === 'user' ? 'You' : 'QFin'}
                      {message.mode ? ` — ${message.mode}` : ''}
                    </strong>

                    <div className={message.error ? 'errorText' : ''}>
                      {message.content}
                    </div>
                  </div>
                ))}
              </div>

              <form className="buttonRow" onSubmit={submitChat}>
                <textarea
                  className="textarea"
                  value={chatInput}
                  onChange={(event) => setChatInput(event.target.value)}
                  placeholder="Ask QFin to analyze a company, explain CAPM, compare stocks..."
                />

                <button
                  type="submit"
                  className="primary"
                  disabled={loading || !chatInput.trim()}
                >
                  {loading ? 'Generating...' : 'Send'}
                </button>
              </form>
            </section>

            <aside className="panel stockPanel">
              <p className="eyebrow">Analytics Panel</p>
              <h3>Backend Debug</h3>

              <div className="metrics">
                <div>
                  <span>API Base</span>
                  <strong style={{ fontSize: 12 }}>{API_BASE_URL}</strong>
                </div>

                <div>
                  <span>Last URL</span>
                  <strong style={{ fontSize: 12 }}>{debugInfo.lastUrl || 'None yet'}</strong>
                </div>

                <div>
                  <span>Status</span>
                  <strong style={{ fontSize: 14 }}>{debugInfo.lastStatus || 'None yet'}</strong>
                </div>

                <div>
                  <span>Error</span>
                  <strong style={{ fontSize: 12 }}>{debugInfo.lastError || 'None'}</strong>
                </div>
              </div>
            </aside>
          </section>
        )}

        {view === 'analyze' && (
          <section className="panel">
            <div className="panelHeader">
              <div>
                <h3>Company Analysis</h3>
                <p>
                  Default is Quick Mode. Type “deep dive” or “comprehensive” for Deep Mode.
                </p>
              </div>

              <span className="pill">{selectedMode}</span>
            </div>

            <label className="label">Company or ticker</label>

            <input
              className="input"
              value={companyInput}
              onChange={(event) => setCompanyInput(event.target.value)}
              placeholder="e.g. Microsoft, TSLA, Nvidia, Bumi Resources"
            />

            <div className="buttonRow">
              <button
                type="button"
                className="primary"
                onClick={() => runCompanyAnalysis(companyInput)}
                disabled={!companyInput.trim() || loading}
              >
                Analyze company
              </button>
            </div>

            <p className="eyebrow" style={{ marginTop: 24 }}>
              Quick Analyze
            </p>

            <div className="tickerGrid">
              {QUICK_COMPANIES.map((company) => (
                <button
                  key={company}
                  type="button"
                  onClick={() => runCompanyAnalysis(company)}
                  disabled={loading}
                >
                  {company}
                </button>
              ))}
            </div>
          </section>
        )}

        {view === 'news' && (
          <section>
            <section className="panel">
              <div className="panelHeader">
                <div>
                  <h3>Market News</h3>
                  <p>Calls /community/news/category, then retries /news/category.</p>
                </div>
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
            </section>

            {newsLoading && (
              <section className="grid">
                {[1, 2, 3, 4, 5].map((item) => (
                  <div key={item} className="panel">
                    <p>Loading news...</p>
                  </div>
                ))}
              </section>
            )}

            {newsError && !newsLoading && (
              <section className="panel">
                <p className="errorText">{newsError}</p>
                <button type="button" className="primary" onClick={() => loadNews(newsCategory)}>
                  Retry
                </button>
              </section>
            )}

            {!newsLoading && !newsError && (
              <section className="grid">
                {news.map((item, index) => {
                  const newsId = item.id || String(index);
                  const expanded = expandedNewsId === newsId;

                  return (
                    <article key={newsId} className="panel">
                      <p className="eyebrow">
                        {(item.sentiment || 'neutral').toUpperCase()}
                        {item.stale ? ' · LAST KNOWN' : ''}
                      </p>

                      <h3>{item.headline || 'Untitled market update'}</h3>

                      <p>{item.teaser || 'No teaser returned by backend.'}</p>

                      <p>
                        <strong>Source:</strong> {item.source?.name || 'Backend source'}
                      </p>

                      <button
                        type="button"
                        onClick={() => setExpandedNewsId(expanded ? null : newsId)}
                      >
                        {expanded ? 'Hide details' : 'Show details'}
                      </button>

                      {expanded && (
                        <div className="output">
                          <strong>What happened</strong>
                          <p>{item.explanation?.what_happened || 'Not provided.'}</p>

                          <strong>Why it matters</strong>
                          <p>{item.explanation?.why_it_matters || 'Not provided.'}</p>

                          <strong>Market reaction</strong>
                          <p>{item.explanation?.market_reaction || 'Not provided.'}</p>

                          {item.source?.url && (
                            <a href={item.source.url} target="_blank" rel="noreferrer">
                              Open source
                            </a>
                          )}
                        </div>
                      )}
                    </article>
                  );
                })}
              </section>
            )}
          </section>
        )}

        <div className="disclaimer">
          This is not financial advice. Confirm all figures before using them in investment work.
        </div>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
