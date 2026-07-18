import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { qfinApi } from './api/qfinApi';
import type {
  BuilderResult,
  BuilderTemplate,
  ChatMessage,
  CommunityModel,
  CommunityTab,
  ForumComment,
  ForumThread,
  NewsItem,
  PersonalShelfItem,
  ShelfItemKind,
  View
} from './domain/types';
import { readPersonalShelf, writePersonalShelf } from './lib/personalShelf';
import './styles.css';

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

const TEMPLATE_SNIPPETS: BuilderTemplate[] = [
  {
    name: 'Monte Carlo Simulator · GBM Paths',
    description: 'Scenario engine for path dispersion, drawdown cones, and bull/base/bear cases.',
    summary:
      'Probability-first terminal for simulating return paths, drawdown bands, and scenario ranges on a single research card.',
    tags: ['Simulation', 'Macro', 'Volatility'],
    benchmark: 'SPY',
    status: 'paper-ready',
    previewStats: {
      annual_return: '14.8%',
      sharpe: '1.31',
      max_drawdown: '-12.6%',
      turnover: '18%',
      win_rate: '62%'
    },
    previewProfile: {
      benchmark: 'SPY',
      universe: 'US large cap',
      horizon: '12 month',
      regime: 'Risk-on / risk-off',
      engine: 'GBM + shock bands'
    },
    code:
      '# Monte Carlo GBM path terminal\n\nimport math\nimport random\n\ndef simulate_paths(start_price=100, drift=0.09, vol=0.24, horizon=252, paths=500):\n    scenarios = []\n    for _ in range(paths):\n        price = start_price\n        path = [price]\n        for _ in range(horizon):\n            shock = random.gauss(0, 1)\n            step = (drift - 0.5 * vol**2) / 252 + vol * shock / math.sqrt(252)\n            price *= math.exp(step)\n            path.append(price)\n        scenarios.append(path)\n    return scenarios\n\n\ndef signal(prices):\n    if len(prices) < 60:\n        return 0\n    realized = max(prices[-1] / prices[-21] - 1, -1)\n    return 1 if realized > 0.03 else -1 if realized < -0.04 else 0\n'
  },
  {
    name: 'LBO Value Bridge · Waterfall & Returns',
    description: 'Deal workbench for sponsor returns, leverage cases, and valuation bridges.',
    summary:
      'Private equity underwriting frame that links entry multiples, deleveraging, and exit cases into one decision surface.',
    tags: ['Private Equity', 'LBO', 'Waterfall'],
    benchmark: 'PE Comp Set',
    status: 'research',
    previewStats: {
      irr: '21.6%',
      moic: '2.34x',
      debt_paydown: '39%',
      equity_check: '$420m',
      exit_multiple: '11.5x'
    },
    previewProfile: {
      benchmark: 'PE Comp Set',
      sector: 'Business services',
      horizon: '5 years',
      financing: 'First lien + TLB',
      engine: 'Waterfall + bridge'
    },
    code:
      '# LBO value bridge workbench\n\ndef lbo_model(ebitda, entry_multiple, leverage, exit_multiple, cash_conversion):\n    enterprise_value = ebitda * entry_multiple\n    debt = ebitda * leverage\n    equity = enterprise_value - debt\n    annual_cash = ebitda * cash_conversion\n    debt_end = max(debt - annual_cash * 5, 0)\n    exit_value = ebitda * 1.18 * exit_multiple\n    exit_equity = exit_value - debt_end\n    moic = exit_equity / max(equity, 1)\n    irr = moic ** (1 / 5) - 1\n    return {\"equity\": equity, \"debt_end\": debt_end, \"moic\": moic, \"irr\": irr}\n\n\ndef signal(prices):\n    return 1 if len(prices) > 0 else 0\n'
  },
  {
    name: 'Bond Ladder / Portfolio Builder · Cashflow & Rate Shock',
    description: 'Fixed-income builder for ladder design, carry, and duration shock analysis.',
    summary:
      'Cashflow-led builder for treasury ladders, rate sensitivity, maturity staging, and reinvestment risk in one terminal.',
    tags: ['Rates', 'Fixed Income', 'Portfolio'],
    benchmark: 'UST Curve',
    status: 'paper-ready',
    previewStats: {
      yield_to_worst: '4.71%',
      duration: '7.44',
      cash_yield: '$97k',
      avg_coupon: '4.49%',
      stress_pnl: '-8.6%'
    },
    previewProfile: {
      benchmark: 'UST Curve',
      universe: 'Treasury ladder',
      horizon: '10 years',
      shock: '+100 bps',
      engine: 'Cashflow + DV01'
    },
    code:
      '# Bond ladder / rate shock builder\n\ndef bond_price(coupon, maturity, ytm, face=100):\n    total = 0\n    for year in range(1, maturity + 1):\n        total += (coupon * face) / ((1 + ytm) ** year)\n    total += face / ((1 + ytm) ** maturity)\n    return total\n\n\ndef ladder_cashflows(maturities, coupons, ytm):\n    flows = []\n    for maturity, coupon in zip(maturities, coupons):\n        flows.append({\"maturity\": maturity, \"price\": bond_price(coupon, maturity, ytm)})\n    return flows\n\n\ndef signal(prices):\n    return -1 if len(prices) > 20 and prices[-1] < prices[-20] else 1\n'
  },
  {
    name: 'IPO New Issue Calendar · ECM Pipeline',
    description: 'Primary markets board for issue windows, sector heat, and aftermarket quality.',
    summary:
      'ECM surveillance grid for upcoming listings, sector rotation, demand appetite, and the quality of aftermarket performance.',
    tags: ['ECM', 'IPO', 'Primary Markets'],
    benchmark: 'IPO Index',
    status: 'high-risk',
    previewStats: {
      live_deals: '36',
      avg_return_30d: '8.4%',
      hit_rate: '58%',
      deal_size: '$14.2bn',
      sectors: '11'
    },
    previewProfile: {
      benchmark: 'IPO Index',
      geography: 'US / Asia',
      cadence: 'Daily refresh',
      lens: 'ECM pipeline',
      engine: 'Calendar + aftermarket'
    },
    code:
      '# IPO calendar and aftermarket monitor\n\ndef score_deal(price_range_mid, demand_multiple, free_float, quality):\n    demand_score = min(demand_multiple / 4, 1.5)\n    float_score = 0.8 if free_float < 0.15 else 1.0\n    return round(price_range_mid * demand_score * float_score * quality, 2)\n\n\ndef rank_pipeline(deals):\n    ranked = []\n    for deal in deals:\n        ranked.append((deal[\"name\"], score_deal(deal[\"price\"], deal[\"demand\"], deal[\"float\"], deal[\"quality\"])))\n    return sorted(ranked, key=lambda item: item[1], reverse=True)\n\n\ndef signal(prices):\n    return 1 if len(prices) > 5 and prices[-1] > prices[-5] else 0\n'
  }
];

function defaultTickerForTemplate(template: BuilderTemplate) {
  const text = `${template.name} ${template.tags.join(' ')} ${template.benchmark}`.toLowerCase();
  if (text.includes('bond') || text.includes('rate') || text.includes('treasury')) return 'TLT';
  if (text.includes('ipo') || text.includes('ecm')) return 'IPO';
  if (text.includes('crypto')) return 'BTC-USD';
  if (text.includes('ai') || text.includes('technology')) return 'QQQ';
  return 'SPY';
}

function makeId() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function shelfKindLabel(kind: ShelfItemKind) {
  if (kind === 'model_run') return 'Private run';
  return kind.replace('_', ' ');
}

function latestAssistantAnswer(messages: ChatMessage[]) {
  return [...messages].reverse().find((message) => message.role === 'assistant' && !message.error);
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

type ChartTone = 'amber' | 'teal' | 'blue' | 'violet' | 'emerald';

const TONE_PALETTES: Record<
  ChartTone,
  {
    equity: string;
    benchmark: string;
    fillStart: string;
    fillEnd: string;
    glow: string;
  }
> = {
  amber: {
    equity: '#e3b95b',
    benchmark: '#7aa2ff',
    fillStart: 'rgba(227, 185, 91, 0.30)',
    fillEnd: 'rgba(227, 185, 91, 0.02)',
    glow: 'rgba(227, 185, 91, 0.20)'
  },
  teal: {
    equity: '#66d6c2',
    benchmark: '#98a7cf',
    fillStart: 'rgba(102, 214, 194, 0.24)',
    fillEnd: 'rgba(102, 214, 194, 0.02)',
    glow: 'rgba(102, 214, 194, 0.18)'
  },
  blue: {
    equity: '#7fa9ff',
    benchmark: '#d1a35f',
    fillStart: 'rgba(127, 169, 255, 0.26)',
    fillEnd: 'rgba(127, 169, 255, 0.02)',
    glow: 'rgba(127, 169, 255, 0.18)'
  },
  violet: {
    equity: '#b798ff',
    benchmark: '#6cc9ff',
    fillStart: 'rgba(183, 152, 255, 0.28)',
    fillEnd: 'rgba(183, 152, 255, 0.02)',
    glow: 'rgba(183, 152, 255, 0.18)'
  },
  emerald: {
    equity: '#6edd8b',
    benchmark: '#e4bf67',
    fillStart: 'rgba(110, 221, 139, 0.24)',
    fillEnd: 'rgba(110, 221, 139, 0.02)',
    glow: 'rgba(110, 221, 139, 0.18)'
  }
};

function hashValue(seed: string) {
  let hash = 0;
  for (let index = 0; index < seed.length; index += 1) {
    hash = (hash * 31 + seed.charCodeAt(index)) >>> 0;
  }
  return hash;
}

function formatCompactNumber(value: number) {
  return new Intl.NumberFormat('en-US').format(value);
}

function deriveTone(model: Pick<CommunityModel, 'name' | 'tags'>): ChartTone {
  const text = `${model.name} ${model.tags.join(' ')}`.toLowerCase();
  if (text.includes('bond') || text.includes('credit') || text.includes('lbo') || text.includes('ipo'))
    return 'amber';
  if (text.includes('ai') || text.includes('valuation') || text.includes('growth')) return 'blue';
  if (text.includes('electricity') || text.includes('energy')) return 'emerald';
  if (text.includes('monte') || text.includes('vix') || text.includes('volatility')) return 'teal';
  return ['amber', 'teal', 'blue', 'violet', 'emerald'][hashValue(text) % 5] as ChartTone;
}

function buildPreviewSeries(seed: string, benchmarkLabel = 'SPY') {
  const hash = hashValue(`${seed}-${benchmarkLabel}`);
  const labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  let equity = 100;
  let benchmark = 100;

  return labels.map((label, index) => {
    const wave = Math.sin((index + 1) * ((hash % 7) + 2) * 0.35);
    const drift = 2.1 + (hash % 5) * 0.35;
    const shock = ((hash >> (index % 12)) % 9) * 0.18 - 0.45;
    const benchDrift = 1.15 + (hash % 3) * 0.18;
    equity += drift + wave * 2.2 + shock;
    benchmark += benchDrift + Math.cos((index + 1) * 0.42) * 0.8;
    const drawdown = Math.min(0, equity - Math.max(100, equity));
    return {
      label,
      equity: Number(equity.toFixed(2)),
      benchmark: Number(benchmark.toFixed(2)),
      drawdown: Number(drawdown.toFixed(2))
    };
  });
}

function deriveEngagement(model: Pick<CommunityModel, 'id' | 'name' | 'score'>) {
  const seed = hashValue(`${model.id}-${model.name}-${model.score}`);
  return {
    likes: 380 + (seed % 1450),
    views: 4800 + ((seed * 13) % 19000)
  };
}

function buildBuilderPreviewModel({
  name,
  author,
  summary,
  code,
  ticker,
  template,
  result
}: {
  name: string;
  author: string;
  summary: string;
  code: string;
  ticker: string;
  template: BuilderTemplate;
  result: BuilderResult | null;
}): CommunityModel {
  const benchmark = result?.ticker || result?.profile?.benchmark || ticker || defaultTickerForTemplate(template);
  const previewProfile = {
    ...template.previewProfile,
    benchmark
  };

  return {
    id: 'builder-preview',
    name: name.trim() || template.name,
    author: author.trim() || 'Research Desk',
    summary: summary.trim() || template.summary,
    score: 0,
    created_at: new Date().toISOString(),
    tags: template.tags,
    stats: result?.stats || template.previewStats,
    code,
    ticker: benchmark,
    profile: result?.profile || previewProfile,
    series:
      result?.series ||
      buildPreviewSeries(name.trim() || template.name, benchmark),
    highlights:
      result?.highlights || [
        `Built from ${template.tags[0]} foundation`,
        `Uses ${template.previewProfile.engine.toLowerCase()}`,
        `Preview benchmark: ${benchmark}`
      ],
    status: result?.status || template.status
  };
}

function TrendChart({
  series,
  compact = false,
  tone = 'violet'
}: {
  series?: Array<{ label: string; equity: number; benchmark: number; drawdown: number }>;
  compact?: boolean;
  tone?: ChartTone;
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
  const gradientId = `equity-fill-${tone}-${compact ? 'compact' : 'full'}-${Math.round(series[0].equity)}-${Math.round(series[series.length - 1].equity)}`;
  const palette = TONE_PALETTES[tone];
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
          <stop offset="0%" stopColor={palette.fillStart} />
          <stop offset="100%" stopColor={palette.fillEnd} />
        </linearGradient>
        <filter id={`glow-${gradientId}`}>
          <feGaussianBlur stdDeviation={compact ? '2' : '3'} result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
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
      <path d={benchmarkPath} className="chartBenchmarkLine" style={{ stroke: palette.benchmark }} />
      <path
        d={areaPath}
        className="chartEquityLine"
        style={{ stroke: palette.equity, filter: `url(#glow-${gradientId})` }}
      />
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

function ResearchModelCard({
  model,
  action,
  preview = false
}: {
  model: CommunityModel;
  action?: React.ReactNode;
  preview?: boolean;
}) {
  const tone = deriveTone(model);
  const palette = TONE_PALETTES[tone];
  const facts = Object.entries(model.profile || {}).slice(0, 5);
  const stats = Object.entries(model.stats || {}).slice(0, 4);
  const engagement = deriveEngagement(model);
  const previewSeries =
    model.series?.length
      ? model.series
      : buildPreviewSeries(model.name, model.profile?.benchmark || 'SPY');

  return (
    <article className={preview ? 'researchModelCard researchModelCardPreview' : 'researchModelCard'}>
      <div className={`researchTerminal researchTerminal-${tone}`}>
        <div className="researchTerminalBar">
          <div className="researchTerminalTabs">
            <span className="researchChip">QFIN</span>
            {model.tags.slice(0, 2).map((tag) => (
              <span key={tag} className="researchChip muted">
                {tag}
              </span>
            ))}
          </div>
          <div className="researchTerminalMeta">
            <span className="researchMetaDot" style={{ background: palette.equity }} />
            <span>updated {relativeTime(model.created_at)}</span>
          </div>
        </div>

        <div className="researchMetricStrip">
          {stats.map(([label, value]) => (
            <div key={label} className="researchMetricCell">
              <span>{formatMetricLabel(label)}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>

        <div className="researchVisualRow">
          <div className="researchPrimaryChart">
            <div className="researchChartMeta">
              <span>Strategy curve</span>
              <strong>{model.profile?.benchmark || 'SPY'} benchmark</strong>
            </div>
            <TrendChart series={previewSeries} compact tone={tone} />
          </div>

          <div className="researchSideFacts">
            {facts.map(([label, value]) => (
              <div key={label} className="researchFactRow">
                <span>{formatMetricLabel(label)}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
        </div>

        {!!model.highlights?.length && (
          <div className="researchHighlightRow">
            {model.highlights.slice(0, 2).map((highlight) => (
              <span key={highlight}>{highlight}</span>
            ))}
          </div>
        )}
      </div>

      <div className="researchCardBody">
        <h3>{model.name}</h3>
        <p>{model.summary}</p>
        <div className="researchCardFooter">
          <div className="researchAuthorRow">
            <span>@{model.author}</span>
            <span>{formatCompactNumber(engagement.likes)} saves</span>
            <span>{formatCompactNumber(engagement.views)} views</span>
          </div>
          {action ? <div className="researchCardAction">{action}</div> : null}
        </div>
      </div>
    </article>
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

function IconSidebar({ direction }: { direction: 'open' | 'close' }) {
  const chevron = direction === 'open' ? 'M10 8l4 4-4 4' : 'M14 8l-4 4 4 4';
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4.5 5.5h15v13h-15v-13Z" />
      <path d="M9 5.5v13" />
      <path d={chevron} />
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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [backendStatus, setBackendStatus] = useState('Checking QFin backend...');
  const [backendOnline, setBackendOnline] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [shelfItems, setShelfItems] = useState<PersonalShelfItem[]>(() => readPersonalShelf());
  const [watchTopic, setWatchTopic] = useState('');

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
  const [expandedThreadId, setExpandedThreadId] = useState<string | null>(null);
  const [commentAuthor, setCommentAuthor] = useState('QuantGuest');
  const [commentDrafts, setCommentDrafts] = useState<Record<string, string>>({});

  const [models, setModels] = useState<CommunityModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);

  const [builderTemplateName, setBuilderTemplateName] = useState(TEMPLATE_SNIPPETS[0].name);
  const [builderName, setBuilderName] = useState(TEMPLATE_SNIPPETS[0].name);
  const [builderSummary, setBuilderSummary] = useState(TEMPLATE_SNIPPETS[0].summary);
  const [builderTicker, setBuilderTicker] = useState(defaultTickerForTemplate(TEMPLATE_SNIPPETS[0]));
  const [builderCode, setBuilderCode] = useState(TEMPLATE_SNIPPETS[0].code);
  const [builderOutput, setBuilderOutput] = useState(
    'Output appears here after Run template or Run privately.'
  );
  const [builderResult, setBuilderResult] = useState<BuilderResult | null>(null);
  const [builderAuthor, setBuilderAuthor] = useState('James');
  const activeTemplate =
    TEMPLATE_SNIPPETS.find((template) => template.name === builderTemplateName) || TEMPLATE_SNIPPETS[0];
  const builderPreviewModel = buildBuilderPreviewModel({
    name: builderName,
    author: builderAuthor,
    summary: builderSummary,
    code: builderCode,
    ticker: builderTicker,
    template: activeTemplate,
    result: builderResult
  });

  function applyTemplate(template: BuilderTemplate) {
    setBuilderTemplateName(template.name);
    setBuilderName(template.name);
    setBuilderSummary(template.summary);
    setBuilderTicker(defaultTickerForTemplate(template));
    setBuilderCode(template.code);
    setBuilderResult(null);
    setBuilderOutput('Template loaded. Refine the canvas, run the model, or publish it to the gallery.');
    setCommunityTab('builder');
  }

  async function checkBackend() {
    try {
      if (await qfinApi.checkHealth()) {
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

  useEffect(() => {
    writePersonalShelf(shelfItems);
  }, [shelfItems]);

  function addShelfItem(item: PersonalShelfItem) {
    setShelfItems((current) => [item, ...current.filter((existing) => existing.id !== item.id)].slice(0, 80));
  }

  function saveConversationToShelf() {
    if (!messages.length) return;
    const firstUserMessage = messages.find((message) => message.role === 'user');
    const answer = latestAssistantAnswer(messages);
    const topic =
      window.prompt('Save this conversation under what topic?', firstUserMessage?.content.slice(0, 80) || 'Research note') ||
      '';
    if (!topic.trim()) return;

    addShelfItem({
      id: makeId(),
      kind: 'conversation',
      title: topic.trim(),
      subtitle: 'Saved QFin conversation',
      topic: topic.trim(),
      body: answer?.content || messages.map((message) => `${message.role}: ${message.content}`).join('\n\n'),
      created_at: new Date().toISOString(),
      tags: ['chat', 'research']
    });
    setView('reports');
  }

  function addWatchlistTopic() {
    const topic = watchTopic.trim();
    if (!topic) return;
    addShelfItem({
      id: makeId(),
      kind: 'watchlist',
      title: topic,
      subtitle: 'Watchlist topic',
      topic,
      body: `Keep an eye on ${topic}. This can be a stock, sector, macro theme, crypto asset, bond market, model idea, or any topic you want to follow.`,
      created_at: new Date().toISOString(),
      tags: ['watchlist']
    });
    setWatchTopic('');
  }

  function removeShelfItem(itemId: string) {
    setShelfItems((current) => current.filter((item) => item.id !== itemId));
  }

  function saveModelToShelf(model: CommunityModel, kind: Extract<ShelfItemKind, 'model' | 'model_run'>, body: string) {
    addShelfItem({
      id: makeId(),
      kind,
      title: model.name,
      subtitle:
        kind === 'model_run'
          ? `Private run for ${model.ticker || model.profile?.benchmark || 'custom topic'}`
          : 'Private builder model',
      topic: model.ticker || model.profile?.benchmark || model.name,
      body,
      created_at: new Date().toISOString(),
      tags: model.tags,
      stats: model.stats
    });
  }

  async function sendMessage(input = prompt) {
    const cleanInput = input.trim();
    const attachment = selectedFile;
    if ((!cleanInput && !attachment) || loading) return;
    const effectiveInput = cleanInput || 'Analyze the attached file.';

    setPrompt('');
    setSelectedFile(null);
    setView('home');

    const assistantId = makeId();

    setMessages((current) => [
      ...current,
      {
        id: makeId(),
        role: 'user',
        content: attachment ? `${effectiveInput}\n\nAttached: ${attachment.name}` : effectiveInput
      },
      { id: assistantId, role: 'assistant', content: 'QFin is thinking...' }
    ]);

    setLoading(true);

    try {
      const finalText = (await qfinApi.requestAgentReply(effectiveInput, attachment)) || FAILURE_MESSAGE;

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

    try {
      setNews(await qfinApi.getNews(category));
    } catch {
      setNewsError('News unavailable. Please retry.');
    } finally {
      setNewsLoading(false);
    }
  }

  async function loadForum() {
    setForumLoading(true);
    try {
      const data = await qfinApi.getForum();
      setForumThreads(data.threads);
      setTopThreads(data.topToday);
    } finally {
      setForumLoading(false);
    }
  }

  async function postThread() {
    if (!threadTitle.trim() || !threadBody.trim()) return;
    await qfinApi.createThread({
      title: threadTitle,
      body: threadBody,
      author: threadAuthor
    });
    setThreadTitle('');
    setThreadBody('');
    loadForum();
  }

  async function voteThread(threadId: string, direction: 'up' | 'down') {
    await qfinApi.voteThread(threadId, direction);
    loadForum();
  }

  async function postComment(threadId: string) {
    const body = (commentDrafts[threadId] || '').trim();
    if (!body) return;
    await qfinApi.createComment(threadId, { body, author: commentAuthor });
    setCommentDrafts((current) => ({ ...current, [threadId]: '' }));
    setExpandedThreadId(threadId);
    loadForum();
  }

  async function loadModels() {
    setModelsLoading(true);
    try {
      setModels(await qfinApi.getModels());
    } finally {
      setModelsLoading(false);
    }
  }

  function currentBuilderRequest() {
    return {
      name: builderName,
      code: builderCode,
      author: builderAuthor,
      summary: builderSummary.trim() || activeTemplate.summary,
      ticker: builderTicker.trim() || defaultTickerForTemplate(activeTemplate)
    };
  }

  async function runBuilder(mode: 'run' | 'private') {
    if (!builderName.trim() || !builderCode.trim()) return;
    const data = await qfinApi.runBuilder(currentBuilderRequest(), mode);

    if (mode === 'private') {
      const result = data.result;
      setBuilderResult(result);
      saveModelToShelf(
        {
          ...builderPreviewModel,
          ...data.model,
          stats: result.stats,
          profile: result.profile,
          series: result.series,
          highlights: result.highlights,
          status: result.status,
          ticker: result.ticker || builderTicker
        },
        'model_run',
        `${result.summary}\n\nAnnual return: ${result.stats.annual_return}\nSharpe: ${result.stats.sharpe}\nMax drawdown: ${result.stats.max_drawdown}\nTurnover: ${result.stats.turnover}\nWin rate: ${result.stats.win_rate}\n\n${(result.notes || []).join('\n')}`
      );
      setBuilderOutput(
        `${result.summary}\n\nSaved to Reports & Watchlist as ${data.model?.name || builderName}.\nAnnual return: ${result.stats.annual_return}\nSharpe: ${result.stats.sharpe}\nMax drawdown: ${result.stats.max_drawdown}\nTurnover: ${result.stats.turnover}\nWin rate: ${result.stats.win_rate}`
      );
      return;
    }

    const result = data.result;
    setBuilderResult(result);
    setBuilderOutput(
      `${result.summary}\n\nAnnual return: ${result.stats.annual_return}\nSharpe: ${result.stats.sharpe}\nMax drawdown: ${result.stats.max_drawdown}\nTurnover: ${result.stats.turnover}\nWin rate: ${result.stats.win_rate}\n\n${(result.notes || []).join('\n')}`
    );
  }

  async function publishBuilderModel() {
    if (!builderName.trim() || !builderCode.trim()) return;
    const data = await qfinApi.publishBuilder(currentBuilderRequest());
    setBuilderResult(null);
    setBuilderOutput(
      `Published to community models.\n\nModel: ${data.model?.name || builderName}\nAuthor: ${data.model?.author || builderAuthor}\nScore: ${data.model?.score ?? 0}`
    );
    setCommunityTab('models');
    loadModels();
  }

  async function savePrivateBuilder() {
    if (!builderName.trim() || !builderCode.trim()) return;
    const data = await qfinApi.savePrivateBuilder(currentBuilderRequest());
    setBuilderResult(null);
    saveModelToShelf(
      {
        ...builderPreviewModel,
        ...data.model
      },
      'model',
      `${data.model?.summary || builderSummary || activeTemplate.summary}\n\nPrivate draft saved from Builder Studio. Use Run privately when you want QFin to attach a backtest-style result to this report item.`
    );
    setBuilderOutput(
      `Saved to Reports & Watchlist.\n\nModel: ${data.model?.name || builderName}\nAuthor: ${data.model?.author || builderAuthor}\nCreated: ${data.model?.created_at || 'just now'}`
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
    <div className={`appShell ${sidebarCollapsed ? 'sidebarCollapsed' : ''}`}>
      <aside className="sidebar">
        <div className="brandBlock">
          <div className="brandIcon">
            <IconLogo />
          </div>
          <div>
            <strong>QFin</strong>
            <span>Terminal</span>
          </div>
          <button
            type="button"
            className="sidebarToggleButton"
            onClick={() => setSidebarCollapsed(true)}
            aria-label="Hide navigation"
            aria-expanded="true"
            title="Hide navigation"
          >
            <IconSidebar direction="close" />
          </button>
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

          <button
            type="button"
            className={view === 'reports' ? 'active' : ''}
            onClick={() => setView('reports')}
          >
            <IconFolder />
            Reports
          </button>
        </nav>

        <p className="sidebarNote">
          AI-powered financial intelligence. Not investment advice.
        </p>
      </aside>

      <main className="mainSurface">
        {sidebarCollapsed && (
          <button
            type="button"
            className="sidebarReopenButton"
            onClick={() => setSidebarCollapsed(false)}
            aria-label="Open navigation"
            aria-expanded="false"
            title="Open navigation"
          >
            <IconSidebar direction="open" />
          </button>
        )}
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
                onClick={() => setView('reports')}
              >
                <IconFolder />
                Reports & Watchlist
              </button>
            </header>

            <section className="homeHero">
              <div className="chartBand" aria-hidden="true" />
              <div className="heroCopy">
                <h1>Ask QFin. Explore Community.</h1>
                <p>GLM handles the language. QFin routes the finance work and brings back the data.</p>
              </div>
            </section>

            <section className="chatSurface" aria-label="QFin chat">
              {!!messages.length && (
                <div className="chatActions">
                  <button type="button" onClick={saveConversationToShelf}>
                    Save conversation
                  </button>
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
                  placeholder="Ask QFin anything. For finance questions, it will route the data work and let the AI analyst write the final answer."
                />

                <div className="composerFooter">
                  <label className="uploadButton">
                    <input
                      type="file"
                      accept=".pdf,.csv,.xls,.xlsx,.docx,.txt,.md,.rtf,.png,.jpg,.jpeg,.webp,.gif"
                      onClick={(event) => {
                        event.currentTarget.value = '';
                      }}
                      onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
                    />
                    <span>+</span>
                    {selectedFile?.name || 'Attach PDF, sheet, document, or image'}
                  </label>

                  <button
                    type="submit"
                    className="sendButton"
                    disabled={loading || (!prompt.trim() && !selectedFile)}
                    aria-label="Send prompt"
                  >
                    <IconSend />
                  </button>
                </div>
              </form>

              <p className="supportText">
                Basic chat routes to GLM. Finance questions route through QFin tools and come back as a final narrated answer.
              </p>
            </section>
          </>
        )}

        {view === 'reports' && (
          <section className="reportsPage">
            <header className="reportsHero">
              <div>
                <p>Private Workspace</p>
                <h1>Reports & Watchlist</h1>
                <span>
                  Save any company, sector, crypto idea, macro question, AI conversation, or private trading model you want to revisit.
                </span>
              </div>
              <button type="button" className="watchlistButton" onClick={() => setView('home')}>
                Ask QFin
              </button>
            </header>

            <article className="watchlistComposerCard">
              <div>
                <span>Track anything</span>
                <h2>Add a watchlist topic</h2>
                <p>
                  This does not have to be a ticker. Try "Alibaba", "AI chips", "Indonesia banks",
                  "10-year Treasury yields", "BTC liquidity", or "Monte Carlo strategy ideas".
                </p>
              </div>
              <div className="watchlistComposerRow">
                <input
                  value={watchTopic}
                  onChange={(event) => setWatchTopic(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault();
                      addWatchlistTopic();
                    }
                  }}
                  placeholder="Stock, sector, strategy, macro theme, anything..."
                />
                <button type="button" className="darkButton" onClick={addWatchlistTopic}>
                  <IconPlusBox />
                  Add
                </button>
              </div>
            </article>

            <section className="shelfSummaryGrid">
              <article>
                <strong>{shelfItems.filter((item) => item.kind === 'conversation').length}</strong>
                <span>Saved conversations</span>
              </article>
              <article>
                <strong>{shelfItems.filter((item) => item.kind === 'watchlist').length}</strong>
                <span>Watchlist topics</span>
              </article>
              <article>
                <strong>{shelfItems.filter((item) => item.kind === 'model' || item.kind === 'model_run').length}</strong>
                <span>Private models</span>
              </article>
            </section>

            {!shelfItems.length ? (
              <article className="emptyState reportsEmpty">
                <h2>Your private shelf is empty</h2>
                <p>
                  Save a QFin conversation, add a watchlist topic, or use Save privately / Run privately
                  in Builder Studio to start building your research library.
                </p>
                <button type="button" onClick={() => setView('community')}>
                  Open Community Builder
                </button>
              </article>
            ) : (
              <section className="shelfGrid">
                {shelfItems.map((item) => (
                  <article key={item.id} className={`shelfCard shelfCard-${item.kind}`}>
                    <div className="shelfCardHeader">
                      <span>{shelfKindLabel(item.kind)}</span>
                      <button type="button" onClick={() => removeShelfItem(item.id)}>
                        Remove
                      </button>
                    </div>
                    <h2>{item.title}</h2>
                    <p className="shelfSubtitle">{item.subtitle}</p>
                    <p>{item.body}</p>
                    {item.stats && (
                      <div className="shelfStats">
                        {Object.entries(item.stats).slice(0, 5).map(([key, value]) => (
                          <div key={key}>
                            <span>{formatMetricLabel(key)}</span>
                            <strong>{value}</strong>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="tagRow">
                      {(item.tags || [item.topic || 'research']).slice(0, 4).map((tag) => (
                        <span key={tag} className="tagPill">
                          {tag}
                        </span>
                      ))}
                    </div>
                    <div className="threadMeta">
                      <span>{relativeTime(item.created_at)}</span>
                      {item.topic && <span>{item.topic}</span>}
                    </div>
                  </article>
                ))}
              </section>
            )}
          </section>
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
                          <button
                            type="button"
                            className="threadDiscussButton"
                            onClick={() => setExpandedThreadId((current) => current === thread.id ? null : thread.id)}
                          >
                            {expandedThreadId === thread.id ? 'Close discussion' : `Discuss (${thread.comment_count || 0})`}
                          </button>
                          {expandedThreadId === thread.id && (
                            <section className="threadDiscussion" aria-label={`Discussion for ${thread.title}`}>
                              <div className="commentList">
                                {(thread.comments || []).length === 0 ? (
                                  <p className="commentEmpty">No replies yet. Be the first to add a useful perspective.</p>
                                ) : (
                                  (thread.comments || []).map((comment) => (
                                    <article key={comment.id} className="commentCard">
                                      <div className="commentMeta">
                                        <strong>{comment.author}</strong>
                                        <span>{relativeTime(comment.created_at)}</span>
                                      </div>
                                      <p>{comment.body}</p>
                                    </article>
                                  ))
                                )}
                              </div>
                              <div className="commentComposer">
                                <input
                                  className="forumAuthorInput"
                                  value={commentAuthor}
                                  onChange={(event) => setCommentAuthor(event.target.value)}
                                  placeholder="Your name"
                                />
                                <textarea
                                  className="forumTextArea commentTextArea"
                                  value={commentDrafts[thread.id] || ''}
                                  onChange={(event) => setCommentDrafts((current) => ({ ...current, [thread.id]: event.target.value }))}
                                  placeholder="Add a constructive reply."
                                />
                                <button type="button" className="threadDiscussButton" onClick={() => postComment(thread.id)}>
                                  Post reply
                                </button>
                              </div>
                            </section>
                          )}
                        </div>
                      </article>
                    ))}
                  </section>
                )}
              </section>
            )}

            {communityTab === 'models' && (
              <section className="communityStack">
                <div className="sectionHeader sectionHeaderWithCopy">
                  <div>
                    <h2>Model gallery</h2>
                    <p>
                      Chart-first research terminals, deal boards, simulators, and macro monitors
                      published by the community.
                    </p>
                  </div>
                  <button type="button" className="galleryLaunchButton" onClick={() => setCommunityTab('builder')}>
                    Open builder studio
                  </button>
                </div>

                {modelsLoading && (
                  <article className="emptyState">
                    <h2>Loading models</h2>
                    <p>Fetching community-published trading models.</p>
                  </article>
                )}

                {!modelsLoading && (
                  <section className="modelDeckGrid">
                    {models.map((model) => (
                      <ResearchModelCard
                        key={model.id}
                        model={model}
                        action={
                          <button
                            type="button"
                            className="galleryActionButton"
                            onClick={() => {
                              const matchedTemplate =
                                TEMPLATE_SNIPPETS.find((template) => template.name === model.name) ||
                                activeTemplate;
                              setBuilderTemplateName(matchedTemplate.name);
                              setBuilderName(model.name);
                              setBuilderAuthor(model.author);
                              setBuilderSummary(model.summary);
                              setBuilderTicker(model.ticker || model.profile?.benchmark || defaultTickerForTemplate(matchedTemplate));
                              setBuilderCode(model.code);
                              setBuilderResult({
                                name: model.name,
                                author: model.author,
                                summary: model.summary,
                                ticker: model.ticker,
                                stats: model.stats,
                                profile: model.profile,
                                series: model.series,
                                highlights: model.highlights,
                                status: model.status,
                                validation: [],
                                notes: []
                              });
                              setCommunityTab('builder');
                            }}
                          >
                            Load in builder
                          </button>
                        }
                      />
                    ))}
                  </section>
                )}
              </section>
            )}

            {communityTab === 'builder' && (
              <section className="builderStudioShell">
                <article className="modelEditor builderWorkbench">
                  <div className="modelToolbar">
                    <div>
                      <h2>Builder studio</h2>
                      <p className="builderToolbarNote">
                        Design a publishable research terminal, wire the logic, and validate the
                        output before sending it to the gallery.
                      </p>
                    </div>
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

                  <div className="builderStudioSplit">
                    <div className="builderCodePane">
                      <div className="builderMetaPanel">
                        <label className="builderFieldGroup">
                          <span>Model title</span>
                          <input
                            className="forumTitleInput"
                            value={builderName}
                            onChange={(event) => setBuilderName(event.target.value)}
                            placeholder="Model name"
                          />
                        </label>
                        <label className="builderFieldGroup">
                          <span>Author</span>
                          <input
                            className="forumAuthorInput"
                            value={builderAuthor}
                            onChange={(event) => setBuilderAuthor(event.target.value)}
                            placeholder="Author"
                          />
                        </label>
                        <label className="builderFieldGroup">
                          <span>Apply to ticker</span>
                          <input
                            className="forumAuthorInput"
                            value={builderTicker}
                            onChange={(event) => setBuilderTicker(event.target.value.toUpperCase())}
                            placeholder="SPY"
                          />
                        </label>
                        <label className="builderFieldGroup builderFieldSpan">
                          <span>Research note</span>
                          <textarea
                            className="builderSummaryInput"
                            value={builderSummary}
                            onChange={(event) => setBuilderSummary(event.target.value)}
                            placeholder="Short model thesis for the published card"
                          />
                        </label>
                      </div>

                      <textarea
                        className="codeEditor terminalCodeEditor"
                        value={builderCode}
                        onChange={(event) => setBuilderCode(event.target.value)}
                        spellCheck={false}
                      />
                    </div>

                    <div className="builderCanvasPane">
                      <div className="builderCanvasIntro">
                        <span>Foundation preview</span>
                        <h3>{activeTemplate.name}</h3>
                        <p>
                          The builder should produce the same kind of dense chart-first card that
                          appears in the model gallery.
                        </p>
                      </div>

                      <ResearchModelCard model={builderPreviewModel} preview />
                      <BuilderOutputPanel builderOutput={builderOutput} builderResult={builderResult} />
                    </div>
                  </div>
                </article>

                <aside className="templatePanel builderLibrary">
                  <div className="builderLibraryHeader">
                    <h2>Foundations</h2>
                    <p>
                      Start from a research surface, then adapt it into your own gallery-ready
                      terminal.
                    </p>
                  </div>
                  <div className="templateGallery">
                    {TEMPLATE_SNIPPETS.map((template) => (
                      <button
                        key={template.name}
                        type="button"
                        className="templateShowcase"
                        onClick={() => applyTemplate(template)}
                      >
                        <strong>{template.name}</strong>
                        <span>{template.description}</span>
                        <div className="templateShowcaseMeta">
                          {template.tags.map((tag) => (
                            <em key={tag}>{tag}</em>
                          ))}
                        </div>
                      </button>
                    ))}
                  </div>
                  <div className="builderPrinciples">
                    <h3>Publishing bar</h3>
                    <ul>
                      <li>Preview must be chart-first and instantly readable.</li>
                      <li>Model cards need a thesis, benchmark, and risk framing.</li>
                      <li>Builder output should be good enough to ship into the gallery.</li>
                    </ul>
                  </div>
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

