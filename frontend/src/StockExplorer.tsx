import React, { useEffect, useState } from "react";
import { AlertTriangle, TrendingUp, TrendingDown, Minus, History } from "lucide-react";
import {
  ResponsiveContainer,
  Tooltip,
  Cell,
  PieChart,
  Pie,
} from "recharts";

import { API_BASE, DISCORD_WEBHOOK_URL } from "./api";

// ---------------------------------------------------------------------------
// Small presentational helpers (mirrors AlertsFeed.tsx)
// ---------------------------------------------------------------------------
type RuleHit = {
  id?: string;
  rule_name: string;
  symbol: string;
  ts: number;
  side_label: string | null;
  price: number;
  forward_5m?: number | null;
  forward_30m?: number | null;
  forward_1d?: number | null;
};

function fmtTs(ts: number): string {
  return new Date(ts * 1000).toLocaleString([], {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}
function fmtRet(v: number | null | undefined): React.ReactNode {
  if (v === null || v === undefined) return <span style={{ color: "hsl(var(--text-muted))" }}>—</span>;
  const pos = v >= 0;
  return <span style={{ color: pos ? "#10b981" : "#ef4444" }}>{pos ? "+" : ""}{v.toFixed(2)}%</span>;
}
function SideBadge({ s }: { s: string | null }) {
  const v = s === "bull" || s === "bear" ? s : "neutral";
  const map = {
    bull:    { bg: "rgba(16,185,129,0.12)", color: "#34d399", border: "rgba(16,185,129,0.3)", icon: <TrendingUp size={10} style={{ marginRight: 3 }} /> },
    bear:    { bg: "rgba(239,68,68,0.12)",  color: "#f87171", border: "rgba(239,68,68,0.3)",  icon: <TrendingDown size={10} style={{ marginRight: 3 }} /> },
    neutral: { bg: "rgba(148,163,184,0.12)", color: "#94a3b8", border: "rgba(148,163,184,0.3)", icon: <Minus size={10} style={{ marginRight: 3 }} /> },
  } as const;
  const c = map[v];
  return (
    <span className="badge" style={{ background: c.bg, color: c.color, border: `1px solid ${c.border}` }}>{c.icon}{v}</span>
  );
}

// ---------------------------------------------------------------------------
// StockExplorer — darkpool deep-dive + rule-fire history for a single symbol
// ---------------------------------------------------------------------------
export default function StockExplorer() {
  const [scanSymbol, setScanSymbol] = useState("AAPL");
  const [scanDate, setScanDate] = useState("2026-05-22");
  const [scanSummary, setScanSummary] = useState<any>(null);
  const [scanTrades, setScanTrades] = useState<any[]>([]);
  const [scanLoading, setScanLoading] = useState(false);
  const [scanError, setScanError] = useState("");

  const [ruleHits, setRuleHits] = useState<RuleHit[]>([]);
  const [hitsLoading, setHitsLoading] = useState(false);

  // Probe whether the selected date is a US trading day so we can warn the
  // user before they hit "Explore" and get an empty-looking result.
  const [calendarWarning, setCalendarWarning] = useState<{ message: string; suggested: string } | null>(null);
  useEffect(() => {
    if (!scanDate) { setCalendarWarning(null); return; }
    let cancelled = false;
    fetch(`${API_BASE}/dashboard/trading-day?date=${scanDate}`)
      .then(r => r.json())
      .then(d => {
        if (cancelled) return;
        if (d.is_trading_day === false && d.next_trading_day) {
          setCalendarWarning({
            message: `${scanDate} is not a US trading day (weekend or market holiday). No TRF trades exist for that date.`,
            suggested: d.next_trading_day,
          });
        } else {
          setCalendarWarning(null);
        }
      })
      .catch(() => setCalendarWarning(null));
    return () => { cancelled = true; };
  }, [scanDate]);

  const sendDiscordAlert = async (msg: string) => {
    try {
      await fetch(DISCORD_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg }),
      });
    } catch { /* best-effort */ }
  };

  const runExplorer = async (e: React.FormEvent) => {
    e.preventDefault();
    setScanLoading(true);
    setScanError("");
    setScanSummary(null);
    setScanTrades([]);
    const sym = scanSymbol.toUpperCase();

    // Rule-fire history (independent of darkpool fetch)
    setHitsLoading(true);
    fetch(`${API_BASE}/alerts/history?symbol=${sym}&limit=200`)
      .then((r) => r.json())
      .then((d) => { setRuleHits(d.alerts || []); setHitsLoading(false); })
      .catch(() => { setRuleHits([]); setHitsLoading(false); });

    try {
      const resSummary = await fetch(`${API_BASE}/darkpool/summary?symbol=${sym}&date=${scanDate}`);
      if (!resSummary.ok) throw new Error("Failed to load dark pool summary");
      setScanSummary(await resSummary.json());

      const resTrades = await fetch(`${API_BASE}/darkpool/trades?symbol=${sym}&date=${scanDate}&limit=50`);
      if (resTrades.ok) {
        const tradesData = await resTrades.json();
        setScanTrades(tradesData.trades);
      }
    } catch (err: any) {
      setScanError(err.message || "An error occurred fetching explorer data.");
    } finally {
      setScanLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>

      {/* Query Panel */}
      <div className="glass-panel" style={{ padding: "20px" }}>
        <form onSubmit={runExplorer} style={{ display: "flex", flexWrap: "wrap", gap: "16px", alignItems: "flex-end" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label style={{ fontSize: "0.8rem", color: "hsl(var(--text-muted))" }}>Stock Symbol</label>
            <input
              type="text"
              className="input-field"
              value={scanSymbol}
              onChange={(e) => setScanSymbol(e.target.value.toUpperCase())}
              style={{ width: "140px" }}
              placeholder="AAPL"
              required
            />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label style={{ fontSize: "0.8rem", color: "hsl(var(--text-muted))" }}>Trading Date</label>
            <input
              type="date"
              className="input-field"
              value={scanDate}
              onChange={(e) => setScanDate(e.target.value)}
              required
            />
          </div>
          <button type="submit" className="btn-primary" style={{ padding: "10px 24px" }} disabled={scanLoading}>
            {scanLoading ? "Analyzing..." : "Explore Symbol"}
          </button>
        </form>
        {calendarWarning && (
          <div style={{ marginTop: 14, padding: "10px 14px", borderRadius: 8,
            background: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.3)",
            display: "flex", alignItems: "center", gap: 10, fontSize: "0.85rem", color: "#fcd34d" }}>
            <AlertTriangle size={16} />
            <span style={{ flex: 1 }}>{calendarWarning.message}</span>
            <button type="button"
              onClick={() => setScanDate(calendarWarning.suggested)}
              style={{ background: "transparent", border: "1px solid rgba(251,191,36,0.4)", color: "#fcd34d",
                padding: "4px 10px", borderRadius: 6, cursor: "pointer", fontSize: "0.8rem" }}
            >
              Use {calendarWarning.suggested}
            </button>
          </div>
        )}
      </div>

      {scanError && (
        <div className="glass-panel" style={{ padding: "16px", borderColor: "rgba(239, 68, 68, 0.4)", display: "flex", gap: "12px", alignItems: "center" }}>
          <AlertTriangle color="#ef4444" />
          <span style={{ fontSize: "0.9rem", color: "#f87171" }}>{scanError}</span>
        </div>
      )}

      {/* Rules fired on this symbol */}
      {(hitsLoading || ruleHits.length > 0 || scanSummary) && (
        <div className="glass-panel" style={{ padding: "24px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "16px" }}>
            <History size={18} color="#a78bfa" />
            <h4 style={{ fontSize: "1rem", fontWeight: 700 }}>Rules Fired on {scanSymbol.toUpperCase()}</h4>
            <span className="badge badge-darkpool">{ruleHits.length} signals</span>
          </div>
          {hitsLoading ? (
            <p style={{ fontSize: "0.85rem", color: "hsl(var(--text-muted))" }}>Loading rule history…</p>
          ) : ruleHits.length === 0 ? (
            <p style={{ fontSize: "0.85rem", color: "hsl(var(--text-muted))" }}>
              No rules have fired on this symbol yet.
            </p>
          ) : (
            <div style={{ maxHeight: "320px", overflowY: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid hsl(var(--border-color))", color: "hsl(var(--text-muted))", fontSize: "0.72rem", letterSpacing: "0.06em" }}>
                    <th style={{ padding: "10px 8px", textAlign: "left" }}>TIME</th>
                    <th style={{ padding: "10px 8px", textAlign: "left" }}>RULE</th>
                    <th style={{ padding: "10px 8px", textAlign: "left" }}>SIDE</th>
                    <th style={{ padding: "10px 8px", textAlign: "left" }}>PRICE</th>
                    <th style={{ padding: "10px 8px", textAlign: "center" }}>+5m</th>
                    <th style={{ padding: "10px 8px", textAlign: "center" }}>+30m</th>
                    <th style={{ padding: "10px 8px", textAlign: "center" }}>+1d</th>
                  </tr>
                </thead>
                <tbody>
                  {ruleHits.map((h, i) => (
                    <tr key={h.id ?? i} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                      <td style={{ padding: "10px 8px", whiteSpace: "nowrap", color: "hsl(var(--text-muted))" }}>{fmtTs(h.ts)}</td>
                      <td style={{ padding: "10px 8px" }}>{h.rule_name}</td>
                      <td style={{ padding: "10px 8px" }}><SideBadge s={h.side_label} /></td>
                      <td style={{ padding: "10px 8px", fontFamily: "var(--font-display)" }}>${h.price.toFixed(2)}</td>
                      <td style={{ padding: "10px 8px", textAlign: "center" }}>{fmtRet(h.forward_5m)}</td>
                      <td style={{ padding: "10px 8px", textAlign: "center" }}>{fmtRet(h.forward_30m)}</td>
                      <td style={{ padding: "10px 8px", textAlign: "center" }}>{fmtRet(h.forward_1d)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Darkpool deep-dive */}
      {scanSummary && (
        <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>

          {/* Stats Summary Cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "20px" }}>
            <div className="glass-panel" style={{ padding: "20px" }}>
              <span style={{ fontSize: "0.8rem", color: "hsl(var(--text-muted))" }}>Dark Pool Ratio (TRF)</span>
              <h3 style={{ fontSize: "1.8rem", fontWeight: 700, color: "#a78bfa", fontFamily: "var(--font-display)", marginTop: "4px" }}>
                {(scanSummary.dark_ratio * 100).toFixed(2)}%
              </h3>
            </div>
            <div className="glass-panel" style={{ padding: "20px" }}>
              <span style={{ fontSize: "0.8rem", color: "hsl(var(--text-muted))" }}>Off-Exchange Volume</span>
              <h3 style={{ fontSize: "1.8rem", fontWeight: 700, fontFamily: "var(--font-display)", marginTop: "4px" }}>
                {scanSummary.dark_volume.toLocaleString()}
              </h3>
            </div>
            <div className="glass-panel" style={{ padding: "20px" }}>
              <span style={{ fontSize: "0.8rem", color: "hsl(var(--text-muted))" }}>Total Trade Volume</span>
              <h3 style={{ fontSize: "1.8rem", fontWeight: 700, fontFamily: "var(--font-display)", marginTop: "4px" }}>
                {scanSummary.total_volume.toLocaleString()}
              </h3>
            </div>
            <div className="glass-panel" style={{ padding: "20px" }}>
              <span style={{ fontSize: "0.8rem", color: "hsl(var(--text-muted))" }}>Avg Dark Pool Price</span>
              <h3 style={{ fontSize: "1.8rem", fontWeight: 700, fontFamily: "var(--font-display)", marginTop: "4px" }}>
                ${scanSummary.avg_dark_price.toFixed(2)}
              </h3>
            </div>
          </div>

          {/* Visualizations & Block Trades Split */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px", alignItems: "start" }}>

            <div className="glass-panel" style={{ padding: "24px", minHeight: "350px", display: "flex", flexDirection: "column" }}>
              <h4 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "16px" }}>Volume Distribution</h4>
              <div style={{ flex: 1, display: "flex", justifyContent: "center", alignItems: "center" }}>
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie
                      data={[
                        { name: "Off-Exchange (TRF)", value: scanSummary.dark_volume },
                        { name: "Lit Exchanges", value: scanSummary.total_volume - scanSummary.dark_volume }
                      ]}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={80}
                      paddingAngle={5}
                      dataKey="value"
                    >
                      <Cell fill="#8b5cf6" />
                      <Cell fill="#3b82f6" />
                    </Pie>
                    <Tooltip formatter={(value: any) => value.toLocaleString()} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div style={{ display: "flex", justifyContent: "center", gap: "24px", fontSize: "0.85rem" }}>
                <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <span style={{ width: "12px", height: "12px", borderRadius: "3px", backgroundColor: "#8b5cf6" }} /> Off-Exchange ({(scanSummary.dark_ratio * 100).toFixed(1)}%)
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <span style={{ width: "12px", height: "12px", borderRadius: "3px", backgroundColor: "#3b82f6" }} /> Lit Exchanges ({((1 - scanSummary.dark_ratio) * 100).toFixed(1)}%)
                </span>
              </div>
            </div>

            {/* Institutional Block Trades Table */}
            <div className="glass-panel" style={{ padding: "24px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                <h4 style={{ fontSize: "1rem", fontWeight: 700 }}>Institutional Block Transactions</h4>
                <span className="badge badge-darkpool">Trades &gt; 5,000 shares</span>
              </div>
              {scanSummary.large_block_trades.length === 0 ? (
                <p style={{ fontSize: "0.85rem", color: "hsl(var(--text-muted))" }}>No block trades matching filter size.</p>
              ) : (
                <div style={{ maxHeight: "250px", overflowY: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid hsl(var(--border-color))", color: "hsl(var(--text-muted))", textAlign: "left" }}>
                        <th style={{ padding: "8px" }}>Time</th>
                        <th style={{ padding: "8px" }}>Size</th>
                        <th style={{ padding: "8px" }}>Price</th>
                        <th style={{ padding: "8px" }}>Value</th>
                        <th style={{ padding: "8px" }}>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {scanSummary.large_block_trades.map((b: any, idx: number) => (
                        <tr key={idx} style={{ borderBottom: "1px solid rgba(255,255,255,0.02)" }}>
                          <td style={{ padding: "10px 8px" }}>{b.time}</td>
                          <td style={{ padding: "10px 8px", fontWeight: 600 }}>{b.size.toLocaleString()}</td>
                          <td style={{ padding: "10px 8px" }}>${b.price.toFixed(2)}</td>
                          <td style={{ padding: "10px 8px", color: "#a78bfa" }}>${b.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                          <td style={{ padding: "10px 8px" }}>
                            <button
                              style={{ background: "transparent", border: "none", color: "#60a5fa", cursor: "pointer", fontSize: "0.75rem", textDecoration: "underline" }}
                              onClick={() => sendDiscordAlert(`🚨 INSTITUTIONAL SPIKE DETECTED on ${scanSymbol.toUpperCase()}: Block trade of ${b.size.toLocaleString()} shares at $${b.price.toFixed(2)} ($${b.value.toLocaleString()} total value).`)}
                            >
                              Push Alert
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

          </div>

          {scanTrades && scanTrades.length > 0 && (
            <div className="glass-panel" style={{ padding: "24px" }}>
              <h4 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "16px" }}>Detailed Trade Ingestion Log</h4>
              <div style={{ maxHeight: "300px", overflowY: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem", textAlign: "left" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid hsl(var(--border-color))", color: "hsl(var(--text-muted))" }}>
                      <th style={{ padding: "10px" }}>Timestamp</th>
                      <th style={{ padding: "10px" }}>Price</th>
                      <th style={{ padding: "10px" }}>Size</th>
                      <th style={{ padding: "10px" }}>Value</th>
                      <th style={{ padding: "10px" }}>Execution Venue</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scanTrades.map((t: any, idx: number) => (
                      <tr key={idx} style={{ borderBottom: "1px solid rgba(255,255,255,0.02)" }}>
                        <td style={{ padding: "10px" }}>{t.timestamp}</td>
                        <td style={{ padding: "10px" }}>${t.price.toFixed(2)}</td>
                        <td style={{ padding: "10px", fontWeight: 600 }}>{t.size.toLocaleString()}</td>
                        <td style={{ padding: "10px" }}>${(t.price * t.size).toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                        <td style={{ padding: "10px" }}>
                          <span className={`badge ${t.trf_id ? "badge-darkpool" : "badge-success"}`}>
                            {t.trf_id ? `Off-Exchange (TRF: ${t.trf_id})` : "Lit Exchange"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

        </div>
      )}

    </div>
  );
}
