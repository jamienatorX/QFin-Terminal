# QFin Terminal — Full Component System

This document defines the UI system for QFin Terminal so the Lovable frontend can implement a polished fintech dashboard consistent with the Figma direction.

## 1. Product Positioning

QFin Terminal is an AI financial analyst and quantitative finance workspace. The interface should feel like a modern Bloomberg / TradingView / institutional research terminal, but simplified for students, analysts, and hackathon judges.

Core use cases:
- Chat with QFin AI
- Analyze a public company by ticker or company name
- Generate structured financial reports
- Read Community market news by category
- Review ratio cards, risk flags, and valuation snapshots
- Save reports and watchlist items later through Supabase

## 2. Visual Style

Theme: dark-mode fintech terminal.

Design mood:
- Professional
- High-contrast
- Data-heavy but clean
- Qwen/Alibaba future-finance feeling
- Neon blue highlights, not too many colors
- Card-based layout with rounded corners
- Avoid childish icons or colorful gradients

## 3. Color Tokens

Use these Tailwind-compatible colors:

```css
--qfin-bg: #080B12;
--qfin-panel: #0E1422;
--qfin-card: #101827;
--qfin-card-2: #141F34;
--qfin-border: #263246;
--qfin-text: #EAF2FF;
--qfin-muted: #93A4BD;
--qfin-subtle: #64748B;
--qfin-blue: #37A2FF;
--qfin-cyan: #4DEBFF;
--qfin-green: #31D98B;
--qfin-red: #FF5A6A;
--qfin-amber: #FFB84D;
--qfin-purple: #9D7CFF;
```

Recommended mapping:
- Background: `#080B12`
- Sidebar / header: `#0E1422`
- Cards: `#101827`
- Active cards: `#141F34`
- Borders: `#263246`
- Primary action: `#37A2FF`
- Positive status: `#31D98B`
- Negative status: `#FF5A6A`
- Neutral-watch status: `#FFB84D`

## 4. Typography

Use Inter or system sans-serif.

Scale:
- Display: 34px, Bold
- H1: 28px, Bold
- H2: 22px, Semi Bold
- H3/Card title: 18px, Semi Bold
- Body: 14px, Regular
- Small body: 13px, Regular
- Label: 12px, Semi Bold
- Micro label: 11px, Semi Bold
- Metric number: 28–32px, Bold

## 5. Layout System

Desktop layout:

```text
┌─────────────────────────────────────────────────────────────┐
│ Sidebar │ Main Workspace                         │ Right Bar │
│ 240px   │ flexible                               │ 320px     │
└─────────────────────────────────────────────────────────────┘
```

Spacing:
- App padding: 24px
- Card padding: 16–24px
- Component gap: 12–18px
- Section gap: 24px
- Border radius: 16–20px

Responsive:
- Desktop: sidebar + main + right panel
- Tablet: sidebar collapses, right panel becomes bottom cards
- Mobile: single column, bottom nav, cards stacked

## 6. Core Components

### 6.1 App Shell

Purpose: Main product container.

Structure:
- Left sidebar
- Top header
- Main content area
- Optional right analytics panel

Props:
- `activeSection`
- `systemStatus`
- `marketDataStatus`
- `children`

### 6.2 Sidebar

Items:
- AI Chat
- Analyze Company
- Community News
- Portfolio
- Report Vault
- Settings

Active item style:
- Background: `#141F34`
- Left border or glow: `#37A2FF`
- Text: `#EAF2FF`

Inactive item:
- Transparent or panel color
- Text: `#93A4BD`

### 6.3 Top Header

Content:
- Page title
- Search input or quick command
- Status chips:
  - QFin Online
  - Market Data Connected
  - News Engine Active

### 6.4 Status Chip

Variants:
- `positive`: green
- `negative`: red
- `neutral`: blue or muted
- `watch`: amber

Example labels:
- QFin Online
- Qwen Connected
- News Engine Active
- Data Delayed
- Supabase Connected

### 6.5 Button

Variants:
- Primary: blue fill
- Secondary: dark card fill, blue border
- Ghost: transparent, border only
- Danger: red muted fill

Sizes:
- Small: 32px height
- Medium: 40px height
- Large: 48px height

### 6.6 Chat Input

Placeholder examples:
- `analyze Microsoft`
- `compare Nvidia and AMD`
- `explain VaR`
- `show Crypto news`

Rules:
- Send exact raw user message to backend.
- Do not add frontend prompt wrappers.
- Use `/chat/stream` for normal chat.

### 6.7 Chat Message Bubble

User bubble:
- Blue background
- White text
- Right-aligned

AI bubble:
- Card background
- Left-aligned
- Label: QFin Terminal
- Supports markdown headers, tables, and bullet lists
- Use `white-space: pre-wrap`

Greeting fallback:

```text
Hello, I am QFin Terminal, your AI financial analyst and quantitative finance agent. You are welcome to ask me to analyze a company, compare stocks, explain financial ratios, build a valuation view, review risks, generate market news, or answer quant finance questions.
```

### 6.8 Financial Metric Card

Fields:
- Label
- Value
- Period note
- Status chip
- Optional mini trend

Examples:
- Revenue Growth: 18.4%, Positive
- Net Margin: 21.7%, Positive
- Debt / Equity: 0.82x, Neutral-Watch
- Free Cash Flow: USD 9.8B, Positive

### 6.9 Risk Flag Card

Fields:
- Risk title
- Severity chip
- Short explanation
- Related metric

Severity:
- Low: green
- Medium: amber
- High: red

### 6.10 News Card

Used in Community tab.

Fields from backend:
- `headline`
- `sentiment`
- `teaser`
- `explanation.what_happened`
- `explanation.why_it_matters`
- `explanation.market_reaction`
- `source.name`
- `source.url`
- optional `data`
- optional `stale`

Card collapsed state:
- Sentiment chip
- Headline
- Teaser
- Source name

Expanded state:
- What happened
- Why it matters
- Market reaction
- Data table/chart if provided
- Source link

### 6.11 News Category Tabs

Tabs:
- Stocks
- Crypto
- Bonds
- ETFs
- Other

API:

```text
GET ${VITE_API_BASE_URL}/community/news/${category}
```

Also supported:

```text
GET ${VITE_API_BASE_URL}/news/${category}
```

### 6.12 Verdict Table

Used in AI report sections.

Columns:
- Area
- Verdict
- Reason
- Data Source

Example rows:
- Revenue Growth | Positive | Latest available growth is above peers | Yahoo Finance
- Balance Sheet | Neutral-Watch | Debt level requires monitoring | Backend data
- Valuation | Neutral | Multiples depend on future growth | Backend data

## 7. Main Screens

### 7.1 AI Chat Screen

Layout:
- Header: AI Financial Analyst
- Welcome card
- Suggested prompts
- Chat history
- Input bar
- Right analytics panel

Suggested prompts:
- Analyze Microsoft
- Analyze Honda
- Analyze Bumi Resources
- Compare Nvidia and AMD
- Explain VaR
- Show Crypto news

### 7.2 Analyze Company Screen

Layout:
- Search input: ticker or company name
- Company overview card
- Market data row
- Financial metric cards
- AI report output
- Risk flag panel

### 7.3 Community News Screen

Layout:
- Category tabs
- 5 news cards
- Each card expandable
- Source link
- Stale badge if `stale: true`
- Retry state if `error: parse_failure`

### 7.4 Portfolio Screen

For later:
- Watchlist table
- Holdings cards
- Risk metrics
- Return chart placeholder

### 7.5 Report Vault Screen

For later:
- Saved reports list
- Search reports
- Open report modal
- Export report button

## 8. Frontend Implementation Rules for Lovable

Critical chat rule:

```ts
await fetch(`${VITE_API_BASE_URL}/chat/stream`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ message: userMessage })
});
```

Never do this:
- Do not add QFin system prompt in frontend
- Do not rewrite `hello`
- Do not send normal chat to `/analyze`
- Do not expect JSON from `/chat/stream`
- Do not show blank response if backend returns empty

News rule:

```ts
await fetch(`${VITE_API_BASE_URL}/community/news/${category}`);
```

Fallback:
- If request fails once, retry once.
- If still fails, show `News unavailable. Please retry.`
- If `stale: true`, show `Last known` badge.
- If `error: parse_failure`, show retry state.

## 9. Lovable Prompt

Paste this into Lovable to apply the design system:

```text
Redesign QFin Terminal using the component system below.

Style: dark fintech terminal, Bloomberg/TradingView inspired, neon blue accent, professional data dashboard.

Use colors:
Background #080B12, Panel #0E1422, Card #101827, Card2 #141F34, Border #263246, Text #EAF2FF, Muted #93A4BD, Blue #37A2FF, Green #31D98B, Red #FF5A6A, Amber #FFB84D, Purple #9D7CFF.

Create an app shell with left sidebar navigation: AI Chat, Analyze Company, Community News, Portfolio, Report Vault, Settings.

Fix the chat behavior. When user types a message, send exactly the raw input to POST ${VITE_API_BASE_URL}/chat/stream with body { "message": userMessage }. Do not rewrite the message. Do not add system prompts. Do not send hello to /analyze. Display the plain text response using white-space: pre-wrap.

If the response is blank, display this fallback: Hello, I am QFin Terminal, your AI financial analyst and quantitative finance agent. You are welcome to ask me to analyze a company, compare stocks, explain financial ratios, build a valuation view, review risks, generate market news, or answer quant finance questions.

Connect Community News to GET ${VITE_API_BASE_URL}/community/news/${category}. Categories are Stocks, Crypto, Bonds, ETFs, Other. Render 5 card-based news items with sentiment chips, headline, teaser, source link, expandable explanation, stale badge, and retry state.

Add reusable components: status chip, primary button, secondary button, chat input, user bubble, AI bubble, financial metric card, risk flag card, news card, verdict table, data source label, and loading skeleton.

Make desktop layout three columns: sidebar 240px, main flexible, right analytics panel 320px. On mobile, use single column and stack cards.
```

## 10. Backend Endpoints

Chat:

```text
POST /chat/stream
```

News:

```text
GET /community/news/Stocks
GET /community/news/Crypto
GET /community/news/Bonds
GET /community/news/ETFs
GET /community/news/Other
```

Alias:

```text
GET /news/Stocks
```
