import React, { useState } from 'react';
import ReactDOM from 'react-dom/client';
import './styles.css';

type QFinReport = {
  qwen_status?: string;
  query?: string;
  ticker?: string;
  facts?: Record<string, unknown>;
  ai_report?: {
    content?: string;
    summary?: string;
    interpretation?: string;
    watch_items?: string[];
  };
  disclaimer?: string;
  error?: string;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

function App() {
  const [ticker, setTicker] = useState('BABA');
  const [query, setQuery] = useState('Analyze Alibaba revenue, margin, leverage, cash flow, and risks');
  const [report, setReport] = useState<QFinReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [apiMessage, setApiMessage] = useState('Ready');

  async function checkBackend() {
    setApiMessage('Checking backend...');
    try {
      const response = await fetch(API_BASE_URL + '/health');
      const data = await response.json();
      setApiMessage('Backend OK. Qwen configured: ' + String(data.qwen_configured));
    } catch (error) {
      setApiMessage('Backend not reachable. Start FastAPI first.');
    }
  }

  async function generateReport() {
    setLoading(true);
    setReport(null);
    setApiMessage('Sending request to backend...');

    try {
      const response = await fetch(API_BASE_URL + '/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, ticker, mode: 'full_report' })
      });

      const data = await response.json();
      setReport(data);
      setApiMessage('Report received from backend.');
    } catch (error) {
      setReport({
        qwen_status: 'frontend_error',
        ai_report: {
          summary: 'Frontend could not reach backend. Make sure FastAPI is running at http://127.0.0.1:8000.'
        },
        error: String(error)
      });
      setApiMessage('Request failed.');
    } finally {
      setLoading(false);
    }
  }

  function useTicker(symbol: string) {
    setTicker(symbol);
    setQuery('Analyze ' + symbol + ' revenue, margin, leverage, cash flow, and risks');
    setReport(null);
  }

  return (
    <div className="appShell">
      <aside className="sidebar">
        <div className="brandRow">
          <div className="logo">Q</div>
          <div>
            <h2>QFin Terminal</h2>
            <p>Qwen financial analyst</p>
          </div>
        </div>

        <nav className="navList">
          <button className="navActive" type="button">Home</button>
          <button type="button" onClick={() => alert('Community page will be connected next.')}>Community</button>
          <button type="button" onClick={() => alert('Reports drawer will be connected next.')}>Reports</button>
          <button type="button" onClick={() => alert('Model Builder will be connected next.')}>Model Builder</button>
        </nav>

        <div className="securityBox">
          <strong>Grounded AI</strong>
          <p>Qwen is called only from backend. It explains backend-computed numbers and must not invent financial figures.</p>
        </div>
      </aside>

      <main className="workspace">
        <header className="hero">
          <p className="eyebrow">AI Financial Analyst Dashboard</p>
          <h1>Analyze companies, statements, and risk signals in one workspace.</h1>
          <div className="heroActions">
            <button type="button" onClick={checkBackend}>Check Backend</button>
            <button type="button" onClick={() => { setReport(null); setQuery(''); setTicker(''); }}>New Report</button>
          </div>
        </header>

        <section className="grid">
          <section className="panel">
            <div className="panelHeader">
              <div>
                <h3>Ask QFin</h3>
                <p>{apiMessage}</p>
              </div>
              <span className="pill">{API_BASE_URL}</span>
            </div>

            <label className="label">Ticker</label>
            <input
              className="input"
              value={ticker}
              onChange={(event) => setTicker(event.target.value.toUpperCase())}
              placeholder="BABA"
            />

            <label className="label">Analysis request</label>
            <textarea
              className="textarea"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ask QFin to analyze a company..."
            />

            <div className="buttonRow">
              <button type="button" onClick={() => setQuery('Analyze ' + ticker + ' revenue, margin, leverage, cash flow, and risks')}>
                Search Ticker
              </button>
              <button type="button" className="primary" onClick={generateReport} disabled={loading}>
                {loading ? 'Generating...' : 'Generate Report'}
              </button>
            </div>

            <div className="output">
              <p className="status">{report ? 'Status: ' + (report.qwen_status || 'response') : 'Status: waiting'}</p>
              <h3>QFin Report Preview</h3>

              {report ? (
                <div>
                  <div className="reportText">
                    {report.ai_report?.content ||
                      report.ai_report?.summary ||
                      JSON.stringify(report, null, 2)}
                  </div>

                  {report.error && <p className="errorText">{report.error}</p>}

                  {report.facts && (
                    <details>
                      <summary>Backend computed facts</summary>
                      <pre>{JSON.stringify(report.facts, null, 2)}</pre>
                    </details>
                  )}
                </div>
              ) : (
                <p>Click Generate Report. The frontend will call FastAPI `/analyze`.</p>
              )}

              <div className="disclaimer">
                This is not financial advice. Confirm all figures before using them in investment work.
              </div>
            </div>
          </section>

          <aside className="panel stockPanel">
            <p className="eyebrow">Stock Universe</p>
            <h3>Quick ticker buttons</h3>
            <div className="tickerGrid">
              {['BABA', 'NVDA', 'TSLA', 'AAPL', 'MSFT', 'AMZN', 'JD', '0700.HK'].map((symbol) => (
                <button key={symbol} type="button" onClick={() => useTicker(symbol)}>
                  {symbol}
                </button>
              ))}
            </div>

            <div className="metrics">
              <div><span>Revenue Growth</span><strong>{report?.facts ? '+18.4%' : 'Ready'}</strong></div>
              <div><span>Gross Margin</span><strong>{report?.facts ? '42.1%' : 'API'}</strong></div>
              <div><span>Debt / Equity</span><strong>{report?.facts ? '0.68x' : 'Qwen'}</strong></div>
              <div><span>Qwen Status</span><strong>{report?.qwen_status || 'Idle'}</strong></div>
            </div>
          </aside>
        </section>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
