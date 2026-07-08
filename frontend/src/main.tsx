import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import './styles.css';

type View = 'home' | 'community';
type CommunityTab = 'news' | 'forum' | 'models' | 'builder';

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
  score: number;
  created_at: string;
  tags: string[];
  stats: Record<string, string>;
  code: string;
  profile?: Record<string, string>;
  series?: Array<{
    label: string;
    equity: number;
    benchmark: number;
    drawdown: number;
  }>;
  highlights?: string[];
  status?: string;
};

type BuilderResult = {
  name: string;
  author: string;
  summary: string;
  stats: Record<string, string>;
  profile?: Record<string, string>;
  series?: Array<{
    label: string;
    equity: number;
    benchmark: number;
    drawdown: number;
  }>;
  highlights?: string[];
  validation?: Array<{
    label: string;
    status: string;
    detail: string;
  }>;
  notes?: string[];
  status?: string;
};

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'https://qfin-terminal.onrender.com';
const AGENT_REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_AGENT_TIMEOUT_MS || 240000);

const FAILURE_MESSAGE =
  'QFin could not complete that reply just now. The backend may still be waking up or the current route failed. Please retry in a moment.';

const SUGGESTED_PROMPTS = [
  'Analyze Alibaba thoroughly',
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
    description: 'Mean-reversion template for oversold and overbought pullbacks.',
    code:
      '# RSI pullback template\n\ndef signal(prices):\n    window = 14\n    if len(prices) < window:\n        return 0\n    gains = []\n    losses = []\n    for index in range(1, window):\n        move = prices[-index] - prices[-index - 1]\n        gains.append(max(move, 0))\n        losses.append(abs(min(move, 0)))\n    avg_gain = sum(gains) / window\n    avg_loss = sum(losses) / window or 1\n    rsi = 100 - (100 / (1 + avg_gain / avg_loss))\n    return 1 if rsi < 30 else -1 if rsi > 70 else 0\n'
  },
  {
    name: 'MACD crossover',
    description: 'Trend-following template that reacts to momentum regime shifts.',
    code:
      '# MACD crossover template\n\ndef ema(values, span):\n    weight = 2 / (span + 1)\n    result = values[0]\n    for value in values[1:]:\n        result = value * weight + result * (1 - weight)\n    return result\n\ndef signal(prices):\n    if len(prices) < 26:\n        return 0\n    macd = ema(prices[-26:], 12) - ema(prices[-26:], 26)\n    return 1 if macd > 0 else -1\n'
  },
  {
    name: 'DCF sensitivity',
    description: 'Valuation workbench for scenario-testing growth and discount rates.',
    code:
      '# DCF sensitivity template\n\ndef valuation(free_cash_flow, growth=0.04, discount=0.1, terminal=0.025):\n    years = 5\n    cash_flows = []\n    for year in range(1, years + 1):\n        cash_flows.append(free_cash_flow * ((1 + growth) ** year))\n    present = sum(cf / ((1 + discount) ** index) for index, cf in enumerate(cash_flows, 1))\n    terminal_value = cash_flows[-1] * (1 + terminal) / (discount - terminal)\n    return present + terminal_value / ((1 + discount) ** years)\n'
  }
];

function makeId() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function fetchWithTimeout(url: string, options: RequestInit = {}, timeoutMs?: number | null) {
  if (!timeoutMs || timeoutMs <= 0) {
    return fetch(url, options);
  }

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  return fetch(url, {
    ...options,
    signal: controller.signal
  }).finally(() => window.clearTimeout(timeoutId));
}

function sanitizeAssistantText(text: string) {
  return text
    .split('\n')
    .filter((line) => line.trim() !== '---')
    .join('\n')
    .replace(/[ \t]{2,}/g, ' ')
    .trim();
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

function formatMetricLabel(label: string) {
  return label
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function modelStatusLabel(status?: string) {
  if (!status) return 'Research';
  return status.replace(/-/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function TrendChart({
  series,
  compact = false
}: {
  series?: Array<{ label: string; equity: number; benchmark: number; drawdown: number }>;
  compact?: boolean;
}) {
  if (!series?.length) return null;

  const width = compact ? 320 : 760;
  const height = compact ? 148 : 248;
  const left = 14;
  const right = 14;
  const top = 16;
  const bottom = 24;
  const chartWidth = width - left - right;
  const chartHeight = height - top - bottom;
  const gradientId = `equity-fill-${compact ? 'compact' : 'full'}-${Math.round(series[0].equity)}-${Math.round(series[series.length - 1].equity)}`;
  const values = series.flatMap((point) => [point.equity, point.benchmark]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(1, max - min);

  const xFor = (index: number) =>
    left + (series.length === 1 ? chartWidth / 2 : (chartWidth * index) / (series.length - 1));
  const yFor = (value: number) => top + ((max - value) / range) * chartHeight;

  const areaPath = series
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${xFor(index)} ${yFor(point.equity)}`)
    .join(' ');
  const areaFill = `${areaPath} L ${xFor(series.length - 1)} ${top + chartHeight} L ${xFor(0)} ${top + chartHeight} Z`;
  const benchmarkPath = series
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${xFor(index)} ${yFor(point.benchmark)}`)
    .join(' ');

  return (
    <svg
      className={compact ? 'trendChart compact' : 'trendChart'}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(126, 98, 255, 0.28)" />
          <stop offset="100%" stopColor="rgba(126, 98, 255, 0.02)" />
        </linearGradient>
      </defs>
      {[0, 0.5, 1].map((step) => (
        <line
          key={step}
          x1={left}
          x2={width - right}
          y1={top + chartHeight * step}
          y2={top + chartHeight * step}
          className="chartGridLine"
        />
      ))}
      <path d={areaFill} fill={`url(#${gradientId})`} />
      <path d={benchmarkPath} className="chartBenchmarkLine" />
      <path d={areaPath} className="chartEquityLine" />
      {series.map((point, index) => (
        <text
          key={`${point.label}-${index}`}
          x={xFor(index)}
          y={height - 6}
          textAnchor="middle"
          className="chartAxisLabel"
        >
          {point.label}
        </text>
      ))}
    </svg>
  );
}

function BuilderOutputPanel({
  builderOutput,
  builderResult
}: {
  builderOutput: string;
  builderResult: BuilderResult | null;
}) {
  if (!builderResult) {
    return (
      <div className="outputPanel">
        <span>Output</span>
        <pre>{builderOutput}</pre>
        <p>
          Hypothetical or simulated performance shown here is part of the builder MVP and
          not a guarantee of future results.
        </p>
      </div>
    );
  }

  return (
    <div className="outputPanel richOutputPanel">
      <div className="outputHeader">
        <div>
          <span>Simulation report</span>
          <h3>{builderResult.name}</h3>
          <p>{builderResult.summary}</p>
        </div>
        <strong className={`statusBadge status-${builderResult.status || 'research'}`}>
          {modelStatusLabel(builderResult.status)}
        </strong>
      </div>

      <div className="builderMetricGrid">
        {Object.entries(builderResult.stats).map(([label, value]) => (
          <article key={label} className="builderMetricCard">
            <span>{formatMetricLabel(label)}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </div>

      <article className="builderChartCard">
        <div className="builderPanelHeader">
          <div>
            <h4>Simulation curve</h4>
            <p>
              Strategy equity vs {builderResult.profile?.benchmark || 'benchmark'} preview over
              the last 12 periods.
            </p>
          </div>
        </div>
        <TrendChart series={builderResult.series} />
      </article>

      <div className="builderInsightGrid">
        <article className="builderInsightCard">
          <h4>Real-world deployment</h4>
          <dl className="builderFacts">
            {Object.entries(builderResult.profile || {}).map(([label, value]) => (
              <div key={label}>
                <dt>{formatMetricLabel(label)}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </article>

        <article className="builderInsightCard">
          <h4>Validation notes</h4>
          <ul className="builderBulletList">
            {(builderResult.validation || []).map((item) => (
              <li key={item.label}>
                <strong>{item.label}</strong>
                <span>{item.detail}</span>
              </li>
            ))}
            {(builderResult.notes || []).map((note) => (
              <li key={note}>
                <strong>Note</strong>
                <span>{note}</span>
              </li>
            ))}
          </ul>
        </article>
      </div>

      {!!builderResult.highlights?.length && (
        <div className="builderHighlights">
          {builderResult.highlights.map((highlight) => (
            <span key={highlight} className="tagPill">
              {highlight}
            </span>
          ))}
        </div>
      )}

      <p>
        Hypothetical or simulated performance shown here is part of the builder MVP and
        not a guarantee of future results.
      </p>
    </div>
  );
}

function isTableSeparator(line: string) {
  const cells = parseTableLine(line);
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s/g, '')));
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

function relativeTime(iso: string) {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const minutes = Math.max(1, Math.round((now - then) / 60000));
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
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

  const [forumThreads, setForumThreads] = useState<ForumThread[]>([]);
  const [topThreads, setTopThreads] = useState<ForumThread[]>([]);
  const [forumLoading, setForumLoading] = useState(false);
  const [threadTitle, setThreadTitle] = useState('');
  const [threadBody, setThreadBody] = useState('');
  const [threadAuthor, setThreadAuthor] = useState('MarketNomad');

  const [models, setModels] = useState<CommunityModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);

  const [builderName, setBuilderName] = useState(TEMPLATE_SNIPPETS[0].name);
  const [builderCode, setBuilderCode] = useState(TEMPLATE_SNIPPETS[0].code);
  const [builderOutput, setBuilderOutput] = useState(
    'Output appears here after Run template or Run privately.'
  );
  const [builderResult, setBuilderResult] = useState<BuilderResult | null>(null);
  const [builderAuthor, setBuilderAuthor] = useState('James');

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

  async function sendMessage(input = prompt) {
    const cleanInput = input.trim();
    if (!cleanInput || loading) return;

    setPrompt('');
    setView('home');

    const assistantId = makeId();

    setMessages((current) => [
      ...current,
      { id: makeId(), role: 'user', content: cleanInput },
      { id: assistantId, role: 'assistant', content: 'QFin is thinking...' }
    ]);

    setLoading(true);

    try {
      const response = await fetchWithTimeout(
        `${API_BASE_URL}/agent/chat/stream`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: cleanInput })
        },
        AGENT_REQUEST_TIMEOUT_MS
      );

      if (!response.ok) {
        throw new Error(`Backend returned ${response.status}`);
      }

      const text = await response.text();
      const finalText = text.trim() ? sanitizeAssistantText(text) : FAILURE_MESSAGE;

      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? { ...message, content: finalText, error: false }
            : message
        )
      );
    } catch {
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? { ...message, content: FAILURE_MESSAGE, error: true }
            : message
        )
      );
    } finally {
      setLoading(false);
    }
  }

  async function loadNews(category: string) {
    setNewsLoading(true);
    setNewsError('');
    setNews([]);

    const primaryUrl = `${API_BASE_URL}/community/news/${encodeURIComponent(category)}`;
    const fallbackUrl = `${API_BASE_URL}/news/${encodeURIComponent(category)}`;

    try {
      const readNews = async (url: string) => {
        const response = await fetchWithTimeout(url, {}, 30000);
        if (!response.ok) {
          throw new Error(`News request failed: ${response.status}`);
        }
        const data = await response.json();
        return Array.isArray(data.news) ? data.news.slice(0, 5) : [];
      };

      const results = await Promise.allSettled([readNews(primaryUrl), readNews(fallbackUrl)]);
      const items =
        results.find(
          (result): result is PromiseFulfilledResult<NewsItem[]> =>
            result.status === 'fulfilled' && result.value.length > 0
        )?.value || [];

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

  async function loadForum() {
    setForumLoading(true);
    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/community/forum`, {}, 20000);
      const data = await response.json();
      setForumThreads(Array.isArray(data.threads) ? data.threads : []);
      setTopThreads(Array.isArray(data.top_today) ? data.top_today : []);
    } finally {
      setForumLoading(false);
    }
  }

  async function postThread() {
    if (!threadTitle.trim() || !threadBody.trim()) return;
    await fetchWithTimeout(
      `${API_BASE_URL}/community/forum`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: threadTitle,
          body: threadBody,
          author: threadAuthor
        })
      },
      20000
    );
    setThreadTitle('');
    setThreadBody('');
    loadForum();
  }

  async function voteThread(threadId: string, direction: 'up' | 'down') {
    await fetchWithTimeout(
      `${API_BASE_URL}/community/forum/${threadId}/vote`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction })
      },
      15000
    );
    loadForum();
  }

  async function loadModels() {
    setModelsLoading(true);
    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/community/models`, {}, 20000);
      const data = await response.json();
      setModels(Array.isArray(data.models) ? data.models : []);
    } finally {
      setModelsLoading(false);
    }
  }

  async function runBuilder(mode: 'run' | 'private') {
    if (!builderName.trim() || !builderCode.trim()) return;
    const endpoint = mode === 'private' ? '/builder/run-private' : '/builder/run';
    const response = await fetchWithTimeout(
      `${API_BASE_URL}${endpoint}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: builderName,
          code: builderCode,
          author: builderAuthor,
          summary: 'Saved from the QFin builder.'
        })
      },
      30000
    );
    const data = await response.json();

    if (mode === 'private') {
      const result = data.result;
      setBuilderResult(result);
      setBuilderOutput(
        `${result.summary}\n\nSaved privately as ${data.model?.name || builderName}.\nAnnual return: ${result.stats.annual_return}\nSharpe: ${result.stats.sharpe}\nMax drawdown: ${result.stats.max_drawdown}\nTurnover: ${result.stats.turnover}\nWin rate: ${result.stats.win_rate}`
      );
      return;
    }

    const result = data.result;
    setBuilderResult(result);
    setBuilderOutput(
      `${result.summary}\n\nAnnual return: ${result.stats.annual_return}\nSharpe: ${result.stats.sharpe}\nMax drawdown: ${result.stats.max_drawdown}\nTurnover: ${result.stats.turnover}\nWin rate: ${result.stats.win_rate}\n\n${result.notes.join('\n')}`
    );
  }

  async function publishBuilderModel() {
    if (!builderName.trim() || !builderCode.trim()) return;
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/builder/publish`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: builderName,
          code: builderCode,
          author: builderAuthor,
          summary: 'Published from the QFin builder.'
        })
      },
      30000
    );
    const data = await response.json();
    setBuilderResult(null);
    setBuilderOutput(
      `Published to community models.\n\nModel: ${data.model?.name || builderName}\nAuthor: ${data.model?.author || builderAuthor}\nScore: ${data.model?.score ?? 0}`
    );
    setCommunityTab('models');
    loadModels();
  }

  async function savePrivateBuilder() {
    if (!builderName.trim() || !builderCode.trim()) return;
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/builder/save-private`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: builderName,
          code: builderCode,
          author: builderAuthor,
          summary: 'Saved from the QFin builder.'
        })
      },
      20000
    );
    const data = await response.json();
    setBuilderResult(null);
    setBuilderOutput(
      `Saved privately.\n\nModel: ${data.model?.name || builderName}\nAuthor: ${data.model?.author || builderAuthor}\nCreated: ${data.model?.created_at || 'just now'}`
    );
  }

  useEffect(() => {
    if (view === 'community' && communityTab === 'news') {
      loadNews(newsCategory);
    }
    if (view === 'community' && communityTab === 'forum') {
      loadForum();
    }
    if (view === 'community' && communityTab === 'models') {
      loadModels();
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
                <p>Qwen handles the language. QFin routes the finance work and brings back the data.</p>
              </div>
            </section>

            <section className="chatSurface" aria-label="QFin chat">
              {!!messages.length && (
                <div className="chatActions">
                  <button type="button" onClick={() => setMessages([])}>
                    New chat
                  </button>
                </div>
              )}

              <div className="chatTranscript" aria-live="polite">
                {!messages.length && (
                  <div className="emptyChat">
                    <h2>What would you like to ask?</h2>
                    <p>
                      Ask a normal question, a finance concept, a company deep dive, or a ticker comparison.
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

              {!messages.length && (
                <div className="promptChips">
                  {SUGGESTED_PROMPTS.map((suggestion) => (
                    <button key={suggestion} type="button" onClick={() => sendMessage(suggestion)}>
                      {suggestion}
                    </button>
                  ))}
                </div>
              )}

              <form
                className="composer"
                onSubmit={(event) => {
                  event.preventDefault();
                  sendMessage();
                }}
              >
                <textarea
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  onKeyDown={(event) => {
                    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
                      event.preventDefault();
                      sendMessage();
                    }
                  }}
                  placeholder="Ask QFin anything. For finance questions, it will route the data work and let Qwen write the final answer."
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
                Basic chat routes to Qwen. Finance questions route through QFin tools and come back as a final narrated answer.
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
                Browse market news, post forum threads, upvote the strongest ideas, and publish builder models into the shared feed.
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
                </div>

                <article className="modelEditor forumComposer">
                  <div className="modelToolbar">
                    <h2>Start a thread</h2>
                    <div>
                      <input
                        className="forumAuthorInput"
                        value={threadAuthor}
                        onChange={(event) => setThreadAuthor(event.target.value)}
                        placeholder="Author name"
                      />
                      <button type="button" className="darkButton" onClick={postThread}>
                        <IconPlusBox />
                        Post thread
                      </button>
                    </div>
                  </div>

                  <div className="forumComposerBody">
                    <input
                      className="forumTitleInput"
                      value={threadTitle}
                      onChange={(event) => setThreadTitle(event.target.value)}
                      placeholder="Thread title"
                    />
                    <textarea
                      className="forumTextArea"
                      value={threadBody}
                      onChange={(event) => setThreadBody(event.target.value)}
                      placeholder="Write your thesis, question, setup, or observation."
                    />
                  </div>
                </article>

                {!!topThreads.length && (
                  <article className="newsCard topThreadCard">
                    <span className="sentiment">MOST UPVOTED TODAY</span>
                    <h2>{topThreads[0].title}</h2>
                    <p>{topThreads[0].body}</p>
                    <div className="threadMeta">
                      <span>{topThreads[0].author}</span>
                      <span>{topThreads[0].score} score</span>
                      <span>{relativeTime(topThreads[0].created_at)}</span>
                    </div>
                  </article>
                )}

                {forumLoading && (
                  <article className="emptyState">
                    <h2>Loading forum</h2>
                    <p>Fetching the latest threads and daily ranking.</p>
                  </article>
                )}

                {!forumLoading && (
                  <section className="forumGrid">
                    {forumThreads.map((thread) => (
                      <article key={thread.id} className="threadCard">
                        <div className="voteRail">
                          <button type="button" onClick={() => voteThread(thread.id, 'up')}>
                            +1
                          </button>
                          <strong>{thread.score}</strong>
                          <button type="button" onClick={() => voteThread(thread.id, 'down')}>
                            -1
                          </button>
                        </div>
                        <div className="threadContent">
                          <h3>{thread.title}</h3>
                          <p>{thread.body}</p>
                          <div className="threadMeta">
                            <span>{thread.author}</span>
                            <span>{thread.upvotes} up</span>
                            <span>{thread.downvotes} down</span>
                            <span>{relativeTime(thread.created_at)}</span>
                          </div>
                        </div>
                      </article>
                    ))}
                  </section>
                )}
              </section>
            )}

            {communityTab === 'models' && (
              <section className="communityStack">
                <div className="sectionHeader">
                  <h2>Models</h2>
                </div>

                {modelsLoading && (
                  <article className="emptyState">
                    <h2>Loading models</h2>
                    <p>Fetching community-published trading models.</p>
                  </article>
                )}

                {!modelsLoading && (
                  <section className="modelGrid">
                    {models.map((model) => (
                      <article key={model.id} className="modelCard">
                        <div className="modelCardHeader">
                          <span className="sentiment">{model.score} SCORE</span>
                          <strong className={`statusBadge status-${model.status || 'research'}`}>
                            {modelStatusLabel(model.status)}
                          </strong>
                        </div>
                        <h2>{model.name}</h2>
                        <p>{model.summary}</p>
                        <div className="modelChartCard">
                          <div className="modelChartHeader">
                            <span>Preview curve</span>
                            <strong>{model.profile?.benchmark || 'SPY'} benchmark</strong>
                          </div>
                          <TrendChart series={model.series} compact />
                        </div>
                        <div className="tagRow">
                          {model.tags.map((tag) => (
                            <span key={tag} className="tagPill">
                              {tag}
                            </span>
                          ))}
                        </div>
                        <div className="modelStats">
                          {Object.entries(model.stats).map(([label, value]) => (
                            <div key={label}>
                              <span>{label.replace(/_/g, ' ')}</span>
                              <strong>{value}</strong>
                            </div>
                          ))}
                        </div>
                        {!!model.highlights?.length && (
                          <ul className="modelHighlights">
                            {model.highlights.map((highlight) => (
                              <li key={highlight}>{highlight}</li>
                            ))}
                          </ul>
                        )}
                        {model.profile && (
                          <dl className="modelFacts">
                            {Object.entries(model.profile).slice(0, 4).map(([label, value]) => (
                              <div key={label}>
                                <dt>{formatMetricLabel(label)}</dt>
                                <dd>{value}</dd>
                              </div>
                            ))}
                          </dl>
                        )}
                        <div className="threadMeta">
                          <span>{model.author}</span>
                          <span>{relativeTime(model.created_at)}</span>
                        </div>
                        <div className="modelActions">
                          <button
                            type="button"
                            onClick={() => {
                              setBuilderName(model.name);
                              setBuilderCode(model.code);
                              setBuilderResult(null);
                              setCommunityTab('builder');
                            }}
                          >
                            Load in builder
                          </button>
                        </div>
                      </article>
                    ))}
                  </section>
                )}
              </section>
            )}

            {communityTab === 'builder' && (
              <section className="builderGrid">
                <article className="modelEditor">
                  <div className="modelToolbar">
                    <h2>Model editor</h2>
                    <div>
                      <button type="button" onClick={savePrivateBuilder}>
                        <IconSave />
                        Save privately
                      </button>
                      <button type="button" onClick={publishBuilderModel}>
                        <IconUpload />
                        Publish
                      </button>
                      <button type="button" onClick={() => runBuilder('private')}>
                        <IconPlay />
                        Run privately
                      </button>
                      <button type="button" className="darkButton" onClick={() => runBuilder('run')}>
                        <IconPlay />
                        Run template
                      </button>
                    </div>
                  </div>

                  <div className="builderMetaRow">
                    <input
                      className="forumTitleInput"
                      value={builderName}
                      onChange={(event) => setBuilderName(event.target.value)}
                      placeholder="Model name"
                    />
                    <input
                      className="forumAuthorInput"
                      value={builderAuthor}
                      onChange={(event) => setBuilderAuthor(event.target.value)}
                      placeholder="Author"
                    />
                  </div>

                  <textarea
                    className="codeEditor"
                    value={builderCode}
                    onChange={(event) => setBuilderCode(event.target.value)}
                    spellCheck={false}
                  />

                  <BuilderOutputPanel builderOutput={builderOutput} builderResult={builderResult} />
                </article>

                <aside className="templatePanel">
                  <h2>Templates</h2>
                  <div className="templateList">
                    {TEMPLATE_SNIPPETS.map((template) => (
                      <button
                        key={template.name}
                        type="button"
                        className="templateButton"
                        onClick={() => {
                          setBuilderName(template.name);
                          setBuilderCode(template.code);
                          setBuilderResult(null);
                          setBuilderOutput('Template loaded. Run template, run privately, or publish it.');
                        }}
                      >
                        <strong>{template.name}</strong>
                        <span>{template.description}</span>
                      </button>
                    ))}
                  </div>
                  <p>
                    A strong model page should show a strategy curve, benchmark comparison, risk
                    metrics, market coverage, and a clear live-deployment note.
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
