import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import './styles.css';

type View = 'home' | 'community';
type CommunityTab = 'news' | 'forum' | 'models' | 'builder';
type VoteDirection = 'up' | 'down';

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
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

type ForumThread = {
  id: string;
  title: string;
  body: string;
  author: string;
  created_at: string;
  score: number;
  upvotes: number;
  downvotes: number;
};

type CommunityModel = {
  id: string;
  name: string;
  author: string;
  summary: string;
  tags?: string[];
  score?: number;
  created_at?: string;
  code: string;
  visibility?: string;
  stats?: Record<string, string>;
};

type BuilderResult = {
  name: string;
  author: string;
  summary: string;
  stats?: Record<string, string>;
  notes?: string[];
};

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'https://qfin-terminal.onrender.com';

const CHAT_FAILURE_MESSAGE =
  'QFin could not complete that reply just now. Please retry in a moment.';
const NEWS_FAILURE_MESSAGE = 'News unavailable. Please retry.';
const FORUM_FAILURE_MESSAGE = 'Forum is unavailable right now. Please retry.';
const MODELS_FAILURE_MESSAGE = 'Models are unavailable right now. Please retry.';
const BUILDER_FAILURE_MESSAGE = 'Builder request failed. Please retry.';

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
    author: 'System template',
    summary: 'Simple momentum reversal template using RSI thresholds.',
    code:
      '# QFin Terminal - model template\n\ndef signal(prices):\n    window = 14\n    if len(prices) < window:\n        return 0\n\n    gains = []\n    losses = []\n    for index in range(1, window):\n        move = prices[-index] - prices[-index - 1]\n        gains.append(max(move, 0))\n        losses.append(abs(min(move, 0)))\n\n    avg_gain = sum(gains) / window\n    avg_loss = sum(losses) / window or 1\n    rsi = 100 - (100 / (1 + avg_gain / avg_loss))\n    return 1 if rsi < 30 else -1 if rsi > 70 else 0\n'
  },
  {
    name: 'MACD',
    author: 'System template',
    summary: 'Trend-following template using moving-average convergence divergence.',
    code:
      '# QFin Terminal - MACD template\n\ndef ema(values, span):\n    weight = 2 / (span + 1)\n    result = values[0]\n    for value in values[1:]:\n        result = value * weight + result * (1 - weight)\n    return result\n\ndef signal(prices):\n    if len(prices) < 26:\n        return 0\n    macd = ema(prices[-26:], 12) - ema(prices[-26:], 26)\n    return 1 if macd > 0 else -1\n'
  },
  {
    name: 'DCF sensitivity',
    author: 'System template',
    summary: 'Valuation scaffold that keeps discount and terminal assumptions explicit.',
    code:
      '# QFin Terminal - DCF template\n\ndef valuation(free_cash_flow, growth=0.04, discount=0.10, terminal=0.025):\n    years = 5\n    cash_flows = []\n    for year in range(1, years + 1):\n        cash_flows.append(free_cash_flow * ((1 + growth) ** year))\n\n    present = sum(cf / ((1 + discount) ** index) for index, cf in enumerate(cash_flows, 1))\n    terminal_value = cash_flows[-1] * (1 + terminal) / (discount - terminal)\n    return present + terminal_value / ((1 + discount) ** years)\n'
  }
];

function makeId() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function fetchWithTimeout(url: string, options: RequestInit = {}, timeoutMs = 12000) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  return fetch(url, {
    ...options,
    signal: controller.signal
  }).finally(() => window.clearTimeout(timeoutId));
}

function renderInlineMarkdown(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }

    return part;
  });
}

function isTableLine(line: string) {
  return /^\s*\|.+\|\s*$/.test(line);
}

function parseTableLine(line: string) {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim());
}

function isTableSeparator(line: string) {
  const cells = parseTableLine(line);
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s/g, '')));
}

function formatDate(value?: string) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  }).format(date);
}

function MessageBody({ content }: { content: string }) {
  const lines = content.split(/\r?\n/);
  const blocks: React.ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const trimmed = lines[index].trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed.startsWith('```')) {
      const codeLines: string[] = [];
      index += 1;

      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        codeLines.push(lines[index]);
        index += 1;
      }

      index += 1;
      blocks.push(
        <pre className="reportCode" key={`code-${index}`}>
          {codeLines.join('\n')}
        </pre>
      );
      continue;
    }

    if (isTableLine(trimmed) && lines[index + 1] && isTableSeparator(lines[index + 1])) {
      const tableLines = [trimmed];
      index += 1;

      while (index < lines.length && isTableLine(lines[index].trim())) {
        tableLines.push(lines[index].trim());
        index += 1;
      }

      const [headerLine, , ...bodyLines] = tableLines;
      const headers = parseTableLine(headerLine);
      const rows = bodyLines.map(parseTableLine);

      blocks.push(
        <div className="reportTableWrap" key={`table-${index}`}>
          <table className="reportTable">
            <thead>
              <tr>
                {headers.map((header, headerIndex) => (
                  <th key={`${header}-${headerIndex}`}>{renderInlineMarkdown(header)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={`row-${rowIndex}`}>
                  {headers.map((_, cellIndex) => (
                    <td key={`cell-${cellIndex}`}>
                      {renderInlineMarkdown(row[cellIndex] || '')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    const headingMatch = trimmed.match(/^#{1,4}\s+(.+)$/);
    if (headingMatch) {
      blocks.push(
        <h3 className="reportHeading" key={`heading-${index}`}>
          {renderInlineMarkdown(headingMatch[1])}
        </h3>
      );
      index += 1;
      continue;
    }

    const boldHeadingMatch = trimmed.match(/^\*\*([^*]+):\*\*\s*(.*)$/);
    if (boldHeadingMatch) {
      blocks.push(
        <h3 className="reportHeading" key={`bold-heading-${index}`}>
          {boldHeadingMatch[1]}
        </h3>
      );

      if (boldHeadingMatch[2]) {
        blocks.push(
          <p key={`bold-paragraph-${index}`}>{renderInlineMarkdown(boldHeadingMatch[2])}</p>
        );
      }

      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = [];

      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ''));
        index += 1;
      }

      blocks.push(
        <ul className="reportList" key={`list-${index}`}>
          {items.map((item, itemIndex) => (
            <li key={`${item}-${itemIndex}`}>{renderInlineMarkdown(item)}</li>
          ))}
        </ul>
      );
      continue;
    }

    const paragraphLines = [trimmed];
    index += 1;

    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^#{1,4}\s+/.test(lines[index].trim()) &&
      !/^\*\*([^*]+):\*\*/.test(lines[index].trim()) &&
      !/^[-*]\s+/.test(lines[index].trim()) &&
      !isTableLine(lines[index].trim()) &&
      !lines[index].trim().startsWith('```')
    ) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }

    blocks.push(
      <p key={`paragraph-${index}`}>{renderInlineMarkdown(paragraphLines.join(' '))}</p>
    );
  }

  return <>{blocks}</>;
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
  const [communityTab, setCommunityTab] = useState<CommunityTab>('news');

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedFileName, setSelectedFileName] = useState('');

  const [backendStatus, setBackendStatus] = useState('Checking QFin backend...');
  const [backendOnline, setBackendOnline] = useState(false);

  const [newsCategory, setNewsCategory] =
    useState<(typeof NEWS_CATEGORIES)[number]>('Crypto');
  const [news, setNews] = useState<NewsItem[]>([]);
  const [newsLoading, setNewsLoading] = useState(false);
  const [newsError, setNewsError] = useState('');
  const [expandedNewsId, setExpandedNewsId] = useState<string | null>(null);

  const [topThread, setTopThread] = useState<ForumThread | null>(null);
  const [forumThreads, setForumThreads] = useState<ForumThread[]>([]);
  const [forumLoading, setForumLoading] = useState(false);
  const [forumError, setForumError] = useState('');
  const [forumTitle, setForumTitle] = useState('');
  const [forumBody, setForumBody] = useState('');
  const [forumAuthor, setForumAuthor] = useState('');
  const [forumPosting, setForumPosting] = useState(false);

  const [communityModels, setCommunityModels] = useState<CommunityModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState('');

  const [builderName, setBuilderName] = useState('Volatility Regime Switcher');
  const [builderAuthor, setBuilderAuthor] = useState('Private workspace');
  const [builderSummary, setBuilderSummary] = useState('A regime-aware trading model for sandbox runs and publishing.');
  const [builderCode, setBuilderCode] = useState(TEMPLATE_SNIPPETS[0].code);
  const [builderOutput, setBuilderOutput] = useState(
    'Output appears here after Run template or Run privately.'
  );
  const [builderBusy, setBuilderBusy] = useState(false);

  async function checkBackend() {
    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/health`, {}, 7000);
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

  async function sendPrompt(input?: string) {
    const message = (input ?? prompt).trim();
    if (!message || loading) return;

    setView('home');
    setPrompt('');

    const assistantId = makeId();
    setMessages((current) => [
      ...current,
      { id: makeId(), role: 'user', content: message },
      { id: assistantId, role: 'assistant', content: 'QFin is working on it...' }
    ]);

    setLoading(true);

    try {
      const response = await fetchWithTimeout(
        `${API_BASE_URL}/agent/chat/stream`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ message })
        },
        90000
      );

      if (!response.ok) {
        throw new Error(`Backend returned ${response.status}`);
      }

      const text = (await response.text()).trim();
      const finalText = text || CHAT_FAILURE_MESSAGE;

      setMessages((current) =>
        current.map((entry) =>
          entry.id === assistantId
            ? {
                ...entry,
                content: finalText,
                error: false
              }
            : entry
        )
      );
    } catch {
      setMessages((current) =>
        current.map((entry) =>
          entry.id === assistantId
            ? {
                ...entry,
                content: CHAT_FAILURE_MESSAGE,
                error: true
              }
            : entry
        )
      );
    } finally {
      setLoading(false);
    }
  }

  async function loadNews(category: string) {
    setNewsLoading(true);
    setNewsError('');

    const urls = [
      `${API_BASE_URL}/community/news/${encodeURIComponent(category)}`,
      `${API_BASE_URL}/news/${encodeURIComponent(category)}`
    ];

    try {
      let items: NewsItem[] = [];

      for (const url of urls) {
        try {
          const response = await fetchWithTimeout(url, {}, 30000);
          if (!response.ok) continue;
          const data = await response.json();
          if (Array.isArray(data.news) && data.news.length) {
            items = data.news.slice(0, 5);
            break;
          }
        } catch {
          continue;
        }
      }

      if (!items.length) {
        throw new Error('No news returned');
      }

      setExpandedNewsId(null);
      setNews(items);
    } catch {
      setNews([]);
      setNewsError(NEWS_FAILURE_MESSAGE);
    } finally {
      setNewsLoading(false);
    }
  }

  async function loadForum() {
    setForumLoading(true);
    setForumError('');

    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/community/forum`, {}, 15000);
      if (!response.ok) {
        throw new Error(`Forum returned ${response.status}`);
      }

      const data = await response.json();
      setTopThread(data.top_today?.[0] || null);
      setForumThreads(Array.isArray(data.threads) ? data.threads : []);
    } catch {
      setForumError(FORUM_FAILURE_MESSAGE);
      setTopThread(null);
      setForumThreads([]);
    } finally {
      setForumLoading(false);
    }
  }

  async function submitForumThread(event?: React.FormEvent) {
    event?.preventDefault();
    if (!forumTitle.trim() || !forumBody.trim() || forumPosting) return;

    setForumPosting(true);
    setForumError('');

    try {
      const response = await fetchWithTimeout(
        `${API_BASE_URL}/community/forum`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            title: forumTitle,
            body: forumBody,
            author: forumAuthor
          })
        },
        15000
      );

      if (!response.ok) {
        throw new Error(`Forum returned ${response.status}`);
      }

      const data = await response.json();
      const thread = data.thread as ForumThread;
      setForumThreads((current) => [thread, ...current]);
      setTopThread((current) => {
        if (!current || thread.score >= current.score) return thread;
        return current;
      });
      setForumTitle('');
      setForumBody('');
      setForumAuthor('');
    } catch {
      setForumError(FORUM_FAILURE_MESSAGE);
    } finally {
      setForumPosting(false);
    }
  }

  async function voteThread(threadId: string, direction: VoteDirection) {
    try {
      const response = await fetchWithTimeout(
        `${API_BASE_URL}/community/forum/${encodeURIComponent(threadId)}/vote`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ direction })
        },
        12000
      );

      if (!response.ok) {
        throw new Error('Vote failed');
      }

      const data = await response.json();
      const thread = data.thread as ForumThread;
      setForumThreads((current) =>
        current
          .map((entry) => (entry.id === thread.id ? thread : entry))
          .sort((a, b) => b.score - a.score)
      );
      setTopThread((current) => {
        if (!current || current.id === thread.id || thread.score >= current.score) return thread;
        return current;
      });
    } catch {
      setForumError(FORUM_FAILURE_MESSAGE);
    }
  }

  async function loadModels() {
    setModelsLoading(true);
    setModelsError('');

    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/community/models`, {}, 15000);
      if (!response.ok) {
        throw new Error(`Models returned ${response.status}`);
      }

      const data = await response.json();
      setCommunityModels(Array.isArray(data.models) ? data.models : []);
    } catch {
      setModelsError(MODELS_FAILURE_MESSAGE);
      setCommunityModels([]);
    } finally {
      setModelsLoading(false);
    }
  }

  function loadModelIntoBuilder(model: CommunityModel) {
    setBuilderName(model.name);
    setBuilderAuthor(model.author);
    setBuilderSummary(model.summary);
    setBuilderCode(model.code);
    setBuilderOutput('Model loaded into the builder. Run it privately or publish an updated version.');
    setCommunityTab('builder');
  }

  function formatBuilderOutput(result?: BuilderResult, model?: CommunityModel) {
    if (result) {
      const lines = [
        result.summary,
        '',
        ...(result.stats
          ? Object.entries(result.stats).map(([key, value]) => `${key.replace(/_/g, ' ')}: ${value}`)
          : []),
        '',
        ...(result.notes || [])
      ];
      return lines.join('\n').trim();
    }

    if (model) {
      return `${model.name} was saved as ${model.visibility || 'community'} model by ${model.author}.`;
    }

    return BUILDER_FAILURE_MESSAGE;
  }

  async function runBuilderAction(endpoint: string) {
    if (!builderName.trim() || !builderCode.trim() || builderBusy) return;

    setBuilderBusy(true);
    setBuilderOutput('QFin builder is processing your request...');

    try {
      const response = await fetchWithTimeout(
        `${API_BASE_URL}${endpoint}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            name: builderName,
            author: builderAuthor,
            summary: builderSummary,
            code: builderCode
          })
        },
        20000
      );

      if (!response.ok) {
        throw new Error(`Builder returned ${response.status}`);
      }

      const data = await response.json();
      setBuilderOutput(formatBuilderOutput(data.result, data.model));

      if (endpoint === '/builder/publish' || endpoint === '/community/models') {
        loadModels();
      }
      if (endpoint === '/builder/publish') {
        loadModels();
      }
    } catch {
      setBuilderOutput(BUILDER_FAILURE_MESSAGE);
    } finally {
      setBuilderBusy(false);
    }
  }

  useEffect(() => {
    if (view === 'community' && communityTab === 'news') {
      loadNews(newsCategory);
    }
  }, [view, communityTab, newsCategory]);

  useEffect(() => {
    if (view === 'community' && communityTab === 'forum') {
      loadForum();
    }
  }, [view, communityTab]);

  useEffect(() => {
    if (view === 'community' && (communityTab === 'models' || communityTab === 'builder')) {
      loadModels();
    }
  }, [view, communityTab]);

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

        <p className="sidebarNote">Qwen-powered financial intelligence. Not investment advice.</p>
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
                onClick={() => window.alert('Reports & Watchlist is coming soon.')}
              >
                <IconFolder />
                Reports & Watchlist
              </button>
            </header>

            <section className="homeHero">
              <div className="chartBand" aria-hidden="true" />
              <div className="heroCopy">
                <h1>Ask QFin. Explore Community.</h1>
                <p>Qwen handles the language. QFin routes the work, pulls the data, and returns the result.</p>
              </div>
            </section>

            <section className="chatSurface" aria-label="QFin chat">
              {!messages.length && (
                <div className="promptChips">
                  {SUGGESTED_PROMPTS.map((suggestion) => (
                    <button key={suggestion} type="button" onClick={() => sendPrompt(suggestion)}>
                      {suggestion}
                    </button>
                  ))}
                </div>
              )}

              {messages.length > 0 && (
                <div className="chatActions">
                  <button type="button" onClick={() => setMessages([])}>
                    New chat
                  </button>
                </div>
              )}

              <div className="chatTranscript" aria-live="polite">
                {!messages.length && (
                  <div className="emptyChat">
                    <h2>What would you like to analyze?</h2>
                    <p>
                      Ask for a company analysis, valuation explanation, market update, or a quant
                      finance idea.
                    </p>
                  </div>
                )}

                {messages.map((message) => (
                  <article
                    key={message.id}
                    className={`chatMessage ${message.role} ${message.error ? 'error' : ''}`}
                  >
                    {message.role === 'assistant' && <div className="assistantMark">Q</div>}
                    <div className="messageContent">
                      <MessageBody content={message.content} />
                    </div>
                  </article>
                ))}
              </div>

              <form
                className="composer"
                onSubmit={(event) => {
                  event.preventDefault();
                  sendPrompt();
                }}
              >
                <textarea
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  onKeyDown={(event) => {
                    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
                      event.preventDefault();
                      sendPrompt();
                    }
                  }}
                  placeholder="Ask QFin to analyze a company, compare stocks, explain a finance concept, or summarize the market..."
                />

                <div className="composerFooter">
                  <label className="uploadButton">
                    <input
                      type="file"
                      accept=".csv,.xls,.xlsx"
                      onChange={(event) => setSelectedFileName(event.target.files?.[0]?.name || '')}
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
                QFin uses one backend chat route and keeps the prompt handling on the server side.
              </p>
            </section>
          </>
        )}

        {view === 'community' && (
          <section className="communityPage">
            <header className="pageHeader">
              <p>Community</p>
              <h1>Ideas, models, and market chatter.</h1>
              <span>
                Browse market news, post threads, vote on the strongest ideas, and remix
                community-built trading templates.
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
                  [1, 2, 3, 4, 5].map((item) => (
                    <article key={item} className="newsCard skeletonCard">
                      <span />
                      <strong />
                      <p />
                    </article>
                  ))}

                {newsError && !newsLoading && (
                  <article className="emptyState">
                    <h2>{newsError}</h2>
                    <p>Refresh the category or retry in a moment.</p>
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
                  <button type="button" className="darkButton" onClick={() => setForumTitle('')}>
                    <IconPlusBox />
                    New thread
                  </button>
                </div>

                {topThread && (
                  <article className="topThreadCard">
                    <span>Top thread today</span>
                    <h3>{topThread.title}</h3>
                    <p>{topThread.body}</p>
                    <div className="threadMeta">
                      <span>{topThread.author}</span>
                      <span>{topThread.score} score</span>
                      <span>{formatDate(topThread.created_at)}</span>
                    </div>
                  </article>
                )}

                <form className="forumComposer" onSubmit={submitForumThread}>
                  <div className="forumComposerBody">
                    <input
                      className="forumTitleInput"
                      value={forumTitle}
                      onChange={(event) => setForumTitle(event.target.value)}
                      placeholder="Thread title"
                    />
                    <input
                      className="forumAuthorInput"
                      value={forumAuthor}
                      onChange={(event) => setForumAuthor(event.target.value)}
                      placeholder="Your name (optional)"
                    />
                    <textarea
                      className="forumTextArea"
                      value={forumBody}
                      onChange={(event) => setForumBody(event.target.value)}
                      placeholder="Share a trade idea, question, or market take..."
                    />
                  </div>
                  <div className="modelActions">
                    <button type="submit" className="darkButton" disabled={forumPosting}>
                      {forumPosting ? 'Posting...' : 'Post thread'}
                    </button>
                  </div>
                </form>

                {forumError && (
                  <article className="emptyState">
                    <h2>{forumError}</h2>
                    <button type="button" onClick={loadForum}>
                      Retry
                    </button>
                  </article>
                )}

                {forumLoading && !forumThreads.length && (
                  <article className="emptyState">
                    <h2>Loading threads...</h2>
                  </article>
                )}

                {!forumLoading && !forumError && (
                  <div className="forumGrid">
                    {forumThreads.map((thread) => (
                      <article key={thread.id} className="threadCard">
                        <div className="voteRail">
                          <button type="button" onClick={() => voteThread(thread.id, 'up')}>
                            ▲
                          </button>
                          <strong>{thread.score}</strong>
                          <button type="button" onClick={() => voteThread(thread.id, 'down')}>
                            ▼
                          </button>
                        </div>
                        <div className="threadContent">
                          <h3>{thread.title}</h3>
                          <p>{thread.body}</p>
                          <div className="threadMeta">
                            <span>{thread.author}</span>
                            <span>{thread.upvotes} up / {thread.downvotes} down</span>
                            <span>{formatDate(thread.created_at)}</span>
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </section>
            )}

            {communityTab === 'models' && (
              <section className="communityStack">
                <div className="sectionHeader">
                  <h2>Models</h2>
                </div>

                {modelsError && (
                  <article className="emptyState">
                    <h2>{modelsError}</h2>
                    <button type="button" onClick={loadModels}>
                      Retry
                    </button>
                  </article>
                )}

                {modelsLoading && !communityModels.length && (
                  <article className="emptyState">
                    <h2>Loading models...</h2>
                  </article>
                )}

                {!modelsLoading && !modelsError && (
                  <div className="modelGrid">
                    {communityModels.map((model) => (
                      <article key={model.id} className="modelCard">
                        <div className="threadMeta">
                          <span>{model.author}</span>
                          <span>{model.score || 0} score</span>
                        </div>
                        <h3>{model.name}</h3>
                        <p>{model.summary}</p>
                        <div className="tagRow">
                          {(model.tags || []).map((tag) => (
                            <span key={tag} className="tagPill">
                              {tag}
                            </span>
                          ))}
                        </div>
                        <div className="modelStats">
                          {Object.entries(model.stats || {}).map(([key, value]) => (
                            <div key={key}>
                              <span>{key.replace(/_/g, ' ')}</span>
                              <strong>{value}</strong>
                            </div>
                          ))}
                        </div>
                        <div className="modelActions">
                          <button type="button" onClick={() => loadModelIntoBuilder(model)}>
                            Load in builder
                          </button>
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </section>
            )}

            {communityTab === 'builder' && (
              <section className="builderGrid">
                <article className="modelEditor">
                  <div className="modelToolbar">
                    <h2>Model editor</h2>
                    <div>
                      <button
                        type="button"
                        onClick={() => runBuilderAction('/builder/save-private')}
                        disabled={builderBusy}
                      >
                        <IconSave />
                        Save privately
                      </button>
                      <button
                        type="button"
                        onClick={() => runBuilderAction('/builder/publish')}
                        disabled={builderBusy}
                      >
                        <IconUpload />
                        Publish
                      </button>
                      <button
                        type="button"
                        onClick={() => runBuilderAction('/builder/run-private')}
                        disabled={builderBusy}
                      >
                        <IconPlay />
                        Run privately
                      </button>
                      <button
                        type="button"
                        className="darkButton"
                        onClick={() => runBuilderAction('/builder/run')}
                        disabled={builderBusy}
                      >
                        <IconPlay />
                        Run template
                      </button>
                    </div>
                  </div>

                  <div className="builderMetaRow">
                    <input
                      value={builderName}
                      onChange={(event) => setBuilderName(event.target.value)}
                      placeholder="Model name"
                    />
                    <input
                      value={builderAuthor}
                      onChange={(event) => setBuilderAuthor(event.target.value)}
                      placeholder="Author"
                    />
                  </div>
                  <div className="builderMetaRow">
                    <input
                      value={builderSummary}
                      onChange={(event) => setBuilderSummary(event.target.value)}
                      placeholder="Short model summary"
                    />
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
                    <p>Hypothetical or simulated performance shown here is not a guarantee of future results.</p>
                  </div>
                </article>

                <aside className="templatePanel">
                  <h2>Templates</h2>
                  {TEMPLATE_SNIPPETS.map((template) => (
                    <button
                      key={template.name}
                      type="button"
                      onClick={() => {
                        setBuilderName(template.name);
                        setBuilderAuthor(template.author);
                        setBuilderSummary(template.summary);
                        setBuilderCode(template.code);
                        setBuilderOutput('Template loaded. Run template to preview the backend result.');
                      }}
                    >
                      {template.name}
                    </button>
                  ))}
                  <p>
                    Published community models can be loaded here, edited, run privately, or pushed back to the public model list.
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
