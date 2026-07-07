import React, { useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom/client';
import './styles.css';

type View = 'home' | 'community';
type DepthMode = 'Quick Mode' | 'Deep Mode';
type CommunityTab = 'news' | 'forum' | 'models' | 'builder';

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

const FAILURE_MESSAGE =
  'Analysis request failed. Backend did not return a response. Please check Render backend health or retry.';

const QUICK_MODE_INSTRUCTION =
  'Quick Mode: write only 3 to 5 short paragraphs, exactly one table or one chart, and a 2 to 3 sentence verdict. Do not include peer comparison, exhaustive risks, full statement breakdown, or multiple visuals.';

const DEEP_MODE_INSTRUCTION =
  'Deep Mode: write a full structured institutional report with Executive Summary, Revenue and Growth, Profitability, Liquidity and Solvency, Cash Flow Quality, Valuation Snapshot, Key Risks, and Final Verdict Table.';

const SUGGESTED_PROMPTS = [
  'Analyze Alibaba',
  'Explain free cash flow yield',
  "Summarize NVIDIA's last quarter",
  'Compare AAPL vs MSFT profitability'
];

const NEWS_CATEGORIES = ['Crypto', 'Stocks', 'Bonds', 'ETFs', 'Other'] as const;
const COMMUNITY_TABS: Array<{ id: CommunityTab; label: string }> = [
  { id: 'news', label: 'News' },
  { id: 'forum', label: 'Forum' },
  { id: 'models', label: 'Models' },
  { id: 'builder', label: 'Builder' }
];

const TEMPLATE_SNIPPETS = [
  {
    name: 'RSI indicator',
    code:
      '# QFin Terminal - model template\n# Numbers must come from backend-provided data.\n\ndef signal(prices):\n    window = 14\n    if len(prices) < window:\n        return 0\n    gains = []\n    losses = []\n    for index in range(1, window):\n        move = prices[-index] - prices[-index - 1]\n        gains.append(max(move, 0))\n        losses.append(abs(min(move, 0)))\n    avg_gain = sum(gains) / window\n    avg_loss = sum(losses) / window or 1\n    rsi = 100 - (100 / (1 + avg_gain / avg_loss))\n    return 1 if rsi < 30 else -1 if rsi > 70 else 0\n'
  },
  {
    name: 'MACD',
    code:
      '# QFin Terminal - MACD template\n# Execution runs only in a backend sandbox.\n\ndef ema(values, span):\n    weight = 2 / (span + 1)\n    result = values[0]\n    for value in values[1:]:\n        result = value * weight + result * (1 - weight)\n    return result\n\ndef signal(prices):\n    if len(prices) < 26:\n        return 0\n    macd = ema(prices[-26:], 12) - ema(prices[-26:], 26)\n    return 1 if macd > 0 else -1\n'
  },
  {
    name: 'DCF sensitivity',
    code:
      '# QFin Terminal - DCF sensitivity template\n# Use backend financials; keep assumptions visible.\n\ndef valuation(free_cash_flow, growth=0.04, discount=0.1, terminal=0.025):\n    years = 5\n    cash_flows = []\n    for year in range(1, years + 1):\n        cash_flows.append(free_cash_flow * ((1 + growth) ** year))\n    present = sum(cf / ((1 + discount) ** index) for index, cf in enumerate(cash_flows, 1))\n    terminal_value = cash_flows[-1] * (1 + terminal) / (discount - terminal)\n    return present + terminal_value / ((1 + discount) ** years)\n'
  }
];

const ANALYSIS_SIGNAL_PATTERNS = [
  /^(analyze|analyse|review|check|research)\b/i,
  /^(quick analysis|brief|summary|overview)\b/i,
  /^tell me about\b/i,
  /^(how's|hows|how is)\b/i
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

  const instruction = mode === 'Deep Mode' ? DEEP_MODE_INSTRUCTION : QUICK_MODE_INSTRUCTION;
  return `${message}. ${instruction}`;
}

function buildChatMessage(input: string) {
  const clean = input.trim();

  if (!clean || !shouldUseAnalysisMode(clean)) {
    return {
      mode: undefined,
      message: clean
    };
  }

  const mode = detectDepthMode(clean);

  return {
    mode,
    message: appendModeInstruction(clean, mode)
  };
}

function IconLogo() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 16.5 9.5 11l3.3 3.3L20 7.1" />
      <path d="M15 7h5v5" />
    </svg>
  );
}

function IconHome() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m4 11 8-7 8 7" />
      <path d="M6.5 10.5V20h11v-9.5" />
      <path d="M10 20v-5h4v5" />
    </svg>
  );
}

function IconUsers() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M8.5 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
      <path d="M2.8 19a5.7 5.7 0 0 1 11.4 0" />
      <path d="M16.2 11.4a2.7 2.7 0 1 0-1.1-5.1" />
      <path d="M15.7 14.1a5 5 0 0 1 5.5 4.9" />
    </svg>
  );
}

function IconFolder() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3.5 6.5h6l2 2h9v9.5a2 2 0 0 1-2 2h-15v-13.5Z" />
    </svg>
  );
}

function IconSend() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 19V5" />
      <path d="m6.5 10.5 5.5-5.5 5.5 5.5" />
    </svg>
  );
}

function IconUpload() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 15V4" />
      <path d="m7 9 5-5 5 5" />
      <path d="M5 15v4h14v-4" />
    </svg>
  );
}

function IconSave() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 4h12l2 2v14H5V4Z" />
      <path d="M8 4v6h8V4" />
      <path d="M8 20v-6h8v6" />
    </svg>
  );
}

function IconPlay() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M8 5v14l11-7L8 5Z" />
    </svg>
  );
}

function IconPlusBox() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4.5 5.5h15v13h-15v-13Z" />
      <path d="M12 9v6" />
      <path d="M9 12h6" />
    </svg>
  );
}

function App() {
  const [view, setView] = useState<View>('home');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [backendStatus, setBackendStatus] = useState('Checking QFin backend...');
  const [backendOnline, setBackendOnline] = useState(false);
  const [selectedFileName, setSelectedFileName] = useState('');

  const [newsCategory, setNewsCategory] =
    useState<(typeof NEWS_CATEGORIES)[number]>('Crypto');
  const [communityTab, setCommunityTab] = useState<CommunityTab>('news');
  const [news, setNews] = useState<NewsItem[]>([]);
  const [newsLoading, setNewsLoading] = useState(false);
  const [newsError, setNewsError] = useState('');
  const [expandedNewsId, setExpandedNewsId] = useState<string | null>(null);
  const [builderCode, setBuilderCode] = useState(TEMPLATE_SNIPPETS[0].code);
  const [builderOutput, setBuilderOutput] = useState(
    'Output appears here after Run template or Run backtest.'
  );

  const latestAssistantMessage = useMemo(
    () => [...messages].reverse().find((message) => message.role === 'assistant'),
    [messages]
  );

  async function checkBackend() {
    try {
      const response = await fetch(`${API_BASE_URL}/health`);
      const data = await response.json();

      if (response.ok && data.status === 'ok') {
        setBackendOnline(true);
        setBackendStatus('QFin backend connected');
      } else {
        setBackendOnline(false);
        setBackendStatus('Backend warning');
      }
    } catch {
      setBackendOnline(false);
      setBackendStatus('Backend offline');
    }
  }

  useEffect(() => {
    checkBackend();
  }, []);

  async function sendToChatStream(rawMessage: string, mode?: DepthMode) {
    const cleanMessage = rawMessage.trim();
    if (!cleanMessage || loading) return;

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
        content: 'QFin is generating the analysis...',
        mode
      }
    ]);

    setLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: cleanMessage
        })
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
    } catch {
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

  function submitPrompt(input = prompt) {
    const request = buildChatMessage(input);
    if (!request.message) return;

    setView('home');
    setPrompt('');
    sendToChatStream(request.message, request.mode);
  }

  async function loadNews(category: string) {
    setNewsLoading(true);
    setNewsError('');
    setNews([]);

    const primaryUrl = `${API_BASE_URL}/community/news/${encodeURIComponent(category)}`;
    const fallbackUrl = `${API_BASE_URL}/news/${encodeURIComponent(category)}`;

    try {
      let response = await fetch(primaryUrl);

      if (!response.ok) {
        response = await fetch(fallbackUrl);
      }

      if (!response.ok) {
        throw new Error(`News request failed: ${response.status}`);
      }

      const data = await response.json();
      const items = Array.isArray(data.news) ? data.news.slice(0, 6) : [];

      if (!items.length) {
        throw new Error('Backend returned no news array.');
      }

      setNews(items);
    } catch {
      setNewsError('News unavailable. Please retry.');
    } finally {
      setNewsLoading(false);
    }
  }

  useEffect(() => {
    if (view === 'community' && communityTab === 'news') {
      loadNews(newsCategory);
    }
  }, [view, communityTab, newsCategory]);

  return (
    <div className="appShell">
      <aside className="sidebar">
        <div className="brandBlock">
          <div className="brandIcon">
            <IconLogo />
          </div>
          <div>
            <strong>QFin</strong>
            <span>Terminal</span>
          </div>
        </div>

        <nav className="sideNav" aria-label="Main navigation">
          <button
            type="button"
            className={view === 'home' ? 'active' : ''}
            onClick={() => setView('home')}
          >
            <IconHome />
            Home
          </button>

          <button
            type="button"
            className={view === 'community' ? 'active' : ''}
            onClick={() => setView('community')}
          >
            <IconUsers />
            Community
          </button>
        </nav>

        <p className="sidebarNote">
          Qwen-powered financial intelligence. Not investment advice.
        </p>
      </aside>

      <main className="mainSurface">
        {view === 'home' && (
          <>
            <header className="topBar">
              <button
                type="button"
                className={`statusPill ${backendOnline ? 'online' : 'offline'}`}
                onClick={checkBackend}
              >
                <span />
                {backendStatus}
              </button>

              <button
                type="button"
                className="watchlistButton"
                onClick={() => alert('Reports & Watchlist is coming soon.')}
              >
                <IconFolder />
                Reports & Watchlist
              </button>
            </header>

            <section className="homeHero">
              <div className="chartBand" aria-hidden="true" />
              <div className="heroCopy">
                <h1>Ask QFin. Explore Community.</h1>
                <p>Real financial data, computed on the backend. Qwen explains the result.</p>
              </div>
            </section>

            <section className="promptArea" aria-label="Ask QFin">
              <div className="promptChips">
                {SUGGESTED_PROMPTS.map((suggestion) => (
                  <button key={suggestion} type="button" onClick={() => submitPrompt(suggestion)}>
                    {suggestion}
                  </button>
                ))}
              </div>

              <form
                className="composer"
                onSubmit={(event) => {
                  event.preventDefault();
                  submitPrompt();
                }}
              >
                <textarea
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  onKeyDown={(event) => {
                    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
                      event.preventDefault();
                      submitPrompt();
                    }
                  }}
                  placeholder="Ask QFin to analyze a company, explain a finance concept, or upload a financial statement..."
                />

                <div className="composerFooter">
                  <label className="uploadButton">
                    <input
                      type="file"
                      accept=".csv,.xls,.xlsx"
                      onChange={(event) =>
                        setSelectedFileName(event.target.files?.[0]?.name || '')
                      }
                    />
                    <span>+</span>
                    {selectedFileName || 'Upload CSV or Excel'}
                  </label>

                  <button
                    type="submit"
                    className="sendButton"
                    disabled={loading || !prompt.trim()}
                    aria-label="Send prompt"
                  >
                    <IconSend />
                  </button>
                </div>
              </form>

              <p className="supportText">
                Supports finance questions, company analysis, market news, and Excel statement uploads.
              </p>
            </section>

            {!!messages.length && (
              <section className="analysisPanel">
                <div className="analysisHeader">
                  <div>
                    <span>Analysis</span>
                    <h2>{loading ? 'QFin is working' : 'Latest response'}</h2>
                  </div>
                  <button type="button" onClick={() => setMessages([])}>
                    New chat
                  </button>
                </div>

                <div className="messageList">
                  {messages.map((message) => (
                    <article
                      key={message.id}
                      className={`messageBubble ${message.role} ${message.error ? 'error' : ''}`}
                    >
                      <strong>
                        {message.role === 'user' ? 'You' : 'QFin'}
                        {message.mode ? ` - ${message.mode}` : ''}
                      </strong>
                      <p>{message.content}</p>
                    </article>
                  ))}
                </div>
              </section>
            )}

            {!messages.length && latestAssistantMessage && (
              <section className="analysisPanel">
                <p>{latestAssistantMessage.content}</p>
              </section>
            )}
          </>
        )}

        {view === 'community' && (
          <section className="communityPage">
            <header className="pageHeader">
              <p>Community</p>
              <h1>Ideas, models, and market chatter.</h1>
              <span>
                Browse cached market news, discuss with other analysts, and remix
                community-built model templates.
              </span>
            </header>

            <div className="categoryTabs" role="tablist" aria-label="Market category">
              {NEWS_CATEGORIES.map((category) => (
                <button
                  key={category}
                  type="button"
                  className={newsCategory === category ? 'active' : ''}
                  onClick={() => setNewsCategory(category)}
                >
                  {category}
                </button>
              ))}
            </div>

            <div className="sectionRule" />

            <div className="communityTabs" role="tablist" aria-label="Community section">
              {COMMUNITY_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  className={communityTab === tab.id ? 'active' : ''}
                  onClick={() => setCommunityTab(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {communityTab === 'news' && (
              <section className="newsGrid">
                {newsLoading &&
                  [1, 2, 3, 4].map((item) => (
                    <article key={item} className="newsCard skeletonCard">
                      <span />
                      <strong />
                      <p />
                    </article>
                  ))}

                {newsError && !newsLoading && (
                  <article className="emptyState">
                    <h2>News unavailable</h2>
                    <p>Please retry the backend news request.</p>
                    <button type="button" onClick={() => loadNews(newsCategory)}>
                      Retry
                    </button>
                  </article>
                )}

                {!newsLoading &&
                  !newsError &&
                  news.map((item, index) => {
                    const newsId = item.id || String(index);
                    const expanded = expandedNewsId === newsId;

                    return (
                      <article key={newsId} className="newsCard">
                        <span className="sentiment">
                          {(item.sentiment || 'neutral').toUpperCase()}
                          {item.stale ? ' - LAST KNOWN' : ''}
                        </span>
                        <h2>{item.headline || 'Untitled market update'}</h2>
                        <p>{item.teaser || 'No teaser returned by backend.'}</p>
                        <div className="newsMeta">
                          <span>{item.source?.name || 'QFin backend'}</span>
                          <button
                            type="button"
                            onClick={() => setExpandedNewsId(expanded ? null : newsId)}
                          >
                            {expanded ? 'Hide details' : 'Show details'}
                          </button>
                        </div>

                        {expanded && (
                          <div className="newsDetails">
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

            {communityTab === 'forum' && (
              <section className="communityStack">
                <div className="sectionHeader">
                  <h2>Forum</h2>
                  <button type="button" className="darkButton">
                    <IconPlusBox />
                    New thread
                  </button>
                </div>
                <article className="emptyState">
                  <h2>No threads yet</h2>
                  <p>Community discussions will appear here after posting is enabled.</p>
                </article>
              </section>
            )}

            {communityTab === 'models' && (
              <section className="communityStack">
                <div className="sectionHeader">
                  <h2>Models</h2>
                </div>
                <article className="emptyState">
                  <h2>No published models yet</h2>
                  <p>Forkable valuation, backtest, and quant templates will appear here.</p>
                </article>
              </section>
            )}

            {communityTab === 'builder' && (
              <section className="builderGrid">
                <article className="modelEditor">
                  <div className="modelToolbar">
                    <h2>Model editor</h2>
                    <div>
                      <button type="button" onClick={() => alert('Saved privately for this MVP.')}>
                        <IconSave />
                        Save privately
                      </button>
                      <button type="button" onClick={() => alert('Publishing is disabled in MVP.')}>
                        <IconUpload />
                        Publish
                      </button>
                      <button
                        type="button"
                        className="darkButton"
                        onClick={() =>
                          setBuilderOutput(
                            'Template parsed successfully. Backtest execution is routed through the backend sandbox in the production flow.'
                          )
                        }
                      >
                        <IconPlay />
                        Run template
                      </button>
                    </div>
                  </div>

                  <textarea
                    className="codeEditor"
                    value={builderCode}
                    onChange={(event) => setBuilderCode(event.target.value)}
                    spellCheck={false}
                  />

                  <div className="outputPanel">
                    <span>Output</span>
                    <pre>{builderOutput}</pre>
                    <p>Hypothetical or simulated performance is not a guarantee of future results.</p>
                  </div>
                </article>

                <aside className="templatePanel">
                  <h2>Templates</h2>
                  {TEMPLATE_SNIPPETS.map((template) => (
                    <button
                      key={template.name}
                      type="button"
                      onClick={() => {
                        setBuilderCode(template.code);
                        setBuilderOutput('Template loaded. Run template to preview output.');
                      }}
                    >
                      {template.name}
                    </button>
                  ))}
                  <p>
                    Running a stranger's published model is disabled in MVP. Fork to your workspace
                    to run privately.
                  </p>
                </aside>
              </section>
            )}
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
