import { useEffect, useState } from "react";
import { AlertTriangle, BarChart3, Play } from "lucide-react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const API_BASE = "http://localhost:8000/api/v1";

type RuleRow = { id: string; name: string; enabled: boolean; severity: string };
type HorizonStat = {
  count: number;
  hit_rate: number;
  avg_return_pct: number;
  median_return_pct: number;
  best_pct: number;
  worst_pct: number;
} | null;
type FwdStats = Record<string, { signal_count: number; "5m": HorizonStat; "30m": HorizonStat; "1d": HorizonStat }>;
type PricePoint = { t: number; price: number };
type PriceSeries = Record<string, PricePoint[]>;
type SignalRow = {
  rule_name: string;
  symbol: string;
  ts: number;
  severity: string;
  side_label: string | null;
  price: number;
};

function fmtReturn(v: number | undefined): React.ReactNode {
  if (v === undefined || v === null) return <span style={{ color: "hsl(var(--text-muted))" }}>—</span>;
  const pos = v >= 0;
  return <span style={{ color: pos ? "#10b981" : "#ef4444" }}>{pos ? "+" : ""}{v.toFixed(2)}%</span>;
}
function fmtClock(t: number): string {
  try {
    return new Date(t * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return String(t); }
}

function StatCell({ s }: { s: HorizonStat }) {
  if (!s) return <td colSpan={3} style={{ padding: "8px", textAlign: "center", color: "hsl(var(--text-muted))", fontSize: "0.78rem" }}>—</td>;
  return (
    <>
      <td style={{ padding: "8px", textAlign: "center" }}>
        <span style={{ color: s.hit_rate >= 0.5 ? "#10b981" : "#ef4444" }}>{(s.hit_rate * 100).toFixed(0)}%</span>
        <span style={{ fontSize: "0.72rem", color: "hsl(var(--text-muted))", marginLeft: 4 }}>({s.count})</span>
      </td>
      <td style={{ padding: "8px", textAlign: "center" }}>{fmtReturn(s.avg_return_pct)}</td>
      <td style={{ padding: "8px", textAlign: "center", fontSize: "0.78rem", color: "hsl(var(--text-muted))" }}>
        {s.best_pct > 0 && <span style={{ color: "#10b981" }}>+{s.best_pct.toFixed(1)}%</span>} / {s.worst_pct < 0 && <span style={{ color: "#ef4444" }}>{s.worst_pct.toFixed(1)}%</span>}
      </td>
    </>
  );
}

/** Price line + signal markers for one symbol. */
function SignalChart({ symbol, prices, signals }: { symbol: string; prices: PricePoint[]; signals: SignalRow[] }) {
  if (prices.length < 2) return null;
  const bull = signals.filter((s) => s.side_label !== "bear").map((s) => ({ t: s.ts, price: s.price }));
  const bear = signals.filter((s) => s.side_label === "bear").map((s) => ({ t: s.ts, price: s.price }));
  const domain = [prices[0].t, prices[prices.length - 1].t];

  return (
    <div className="glass-panel" style={{ padding: 20, minHeight: 300 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <h4 style={{ fontSize: "0.9rem", fontWeight: 700 }}>{symbol} — price &amp; signals</h4>
        <div style={{ display: "flex", gap: 14, fontSize: "0.72rem", color: "hsl(var(--text-muted))" }}>
          <span><span style={{ color: "#10b981" }}>●</span> bull/neutral</span>
          <span><span style={{ color: "#ef4444" }}>●</span> bear</span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
          <XAxis
            type="number"
            dataKey="t"
            domain={domain}
            scale="time"
            tickFormatter={(t) => { try { return new Date(t * 1000).toLocaleDateString([], { month: "short", day: "numeric" }); } catch { return String(t); } }}
            stroke="hsl(var(--text-muted))"
            fontSize={10}
            tick={{ fill: "hsl(var(--text-muted))" }}
          />
          <YAxis
            dataKey="price"
            domain={["auto", "auto"]}
            stroke="#a78bfa"
            fontSize={10}
            tickFormatter={(v) => `$${Number(v).toFixed(0)}`}
            tick={{ fill: "hsl(var(--text-muted))" }}
          />
          <Tooltip
            contentStyle={{ backgroundColor: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, fontSize: "0.82rem" }}
            formatter={(v: any) => [`$${Number(v).toFixed(2)}`, "Price"]}
            labelFormatter={(t: any) => fmtClock(Number(t))}
          />
          <Line data={prices} type="monotone" dataKey="price" stroke="#8b5cf6" strokeWidth={1.5} dot={false} isAnimationActive={false} />
          <Scatter data={bull} dataKey="price" fill="#10b981" isAnimationActive={false} />
          <Scatter data={bear} dataKey="price" fill="#ef4444" isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function RuleBacktest({ initialRuleId }: { initialRuleId?: string } = {}) {
  const [allRules, setAllRules] = useState<RuleRow[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [symbols, setSymbols] = useState("AAPL");
  const [startDate, setStartDate] = useState("2026-01-02");
  const [endDate, setEndDate] = useState("2026-05-23");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    fetch(`${API_BASE}/rules`).then(r => r.json()).then(d => {
      const rules: RuleRow[] = d.rules ?? [];
      setAllRules(rules);
      // When launched from Strategy Lab against a specific rule, preselect just
      // that rule; otherwise default to every enabled rule.
      if (initialRuleId && rules.some(r => r.id === initialRuleId)) {
        setSelectedIds(new Set([initialRuleId]));
      } else {
        setSelectedIds(new Set(rules.filter(r => r.enabled).map(r => r.id)));
      }
    });
  }, [initialRuleId]);

  function toggleRule(id: string) {
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function runBacktest(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    const body = {
      symbols: symbols.split(",").map(s => s.trim().toUpperCase()).filter(Boolean),
      start_date: startDate,
      end_date: endDate,
      rule_ids: selectedIds.size > 0 ? [...selectedIds] : undefined,
    };
    try {
      const r = await fetch(`${API_BASE}/backtest/rules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Backtest failed");
      setResult(d);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const fwd: FwdStats = result?.forward_return_stats ?? {};
  const priceSeries: PriceSeries = result?.price_series ?? {};
  const signals: SignalRow[] = result?.signals ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* Header */}
      <div className="glass-panel" style={{ padding: "18px 24px", display: "flex", alignItems: "center", gap: 10 }}>
        <BarChart3 size={20} color="#a78bfa" />
        <div>
          <h3 style={{ fontSize: "1.1rem", fontWeight: 700 }}>Rule Backtest</h3>
          <span style={{ fontSize: "0.75rem", color: "hsl(var(--text-muted))" }}>
            Replay historical TRF trades through the signal engine — does the signal predict the move?
          </span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.6fr", gap: 20, alignItems: "start" }}>

        {/* Config panel */}
        <div className="glass-panel" style={{ padding: 22 }}>
          <form onSubmit={runBacktest} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div>
              <label style={{ fontSize: "0.75rem", color: "hsl(var(--text-muted))", display: "block", marginBottom: 4 }}>Symbols (comma-separated)</label>
              <input className="input-field" style={{ width: "100%" }} value={symbols} onChange={e => setSymbols(e.target.value)} placeholder="AAPL, MSFT" />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div>
                <label style={{ fontSize: "0.75rem", color: "hsl(var(--text-muted))", display: "block", marginBottom: 4 }}>Start Date</label>
                <input className="input-field" style={{ width: "100%" }} type="date" value={startDate} onChange={e => setStartDate(e.target.value)} required />
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "hsl(var(--text-muted))", display: "block", marginBottom: 4 }}>End Date</label>
                <input className="input-field" style={{ width: "100%" }} type="date" value={endDate} onChange={e => setEndDate(e.target.value)} required />
              </div>
            </div>

            {/* Rule selector */}
            <div>
              <label style={{ fontSize: "0.75rem", color: "hsl(var(--text-muted))", display: "block", marginBottom: 6 }}>Rules to test</label>
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                {allRules.map(r => (
                  <label key={r.id} style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: "0.84rem" }}>
                    <input
                      type="checkbox"
                      checked={selectedIds.has(r.id)}
                      onChange={() => toggleRule(r.id)}
                      style={{ accentColor: "#8b5cf6" }}
                    />
                    <span style={{ color: selectedIds.has(r.id) ? "hsl(var(--text-main))" : "hsl(var(--text-muted))" }}>{r.name}</span>
                  </label>
                ))}
              </div>
            </div>

            <button className="btn-primary" type="submit" disabled={loading} style={{ justifyContent: "center" }}>
              <Play size={15} /> {loading ? "Running backtest…" : "Run Backtest"}
            </button>
          </form>
        </div>

        {/* Results */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

          {error && (
            <div className="glass-panel" style={{ padding: 16, borderColor: "rgba(239,68,68,0.3)", display: "flex", gap: 10, alignItems: "center" }}>
              <AlertTriangle color="#ef4444" size={18} />
              <span style={{ color: "#f87171", fontSize: "0.88rem" }}>{error}</span>
            </div>
          )}

          {loading && (
            <div className="glass-panel" style={{ padding: 40, textAlign: "center", color: "hsl(var(--text-muted))" }}>
              Fetching TRF trades and replaying through rule engine…
            </div>
          )}

          {result && !loading && (
            <>
              {/* Signal count */}
              <div className="glass-panel" style={{ padding: "14px 18px", display: "flex", alignItems: "center", gap: 12 }}>
                <BarChart3 size={18} color="#60a5fa" />
                <span style={{ fontSize: "0.85rem", color: "hsl(var(--text-muted))" }}>Signals fired</span>
                <span style={{ fontSize: "1.25rem", fontWeight: 700, fontFamily: "var(--font-display)", color: "#60a5fa" }}>{result.signal_count}</span>
              </div>

              {/* Price + signal-marker charts (one per symbol) */}
              {Object.entries(priceSeries).map(([sym, pts]) => (
                <SignalChart key={sym} symbol={sym} prices={pts} signals={signals.filter((s) => s.symbol === sym)} />
              ))}

              {/* Forward-return stats table */}
              {Object.keys(fwd).length > 0 && (
                <div className="glass-panel" style={{ padding: 20 }}>
                  <h4 style={{ fontSize: "0.9rem", fontWeight: 700, marginBottom: 14 }}>Forward Return Statistics</h4>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid hsl(var(--border-color))", color: "hsl(var(--text-muted))", fontSize: "0.7rem", letterSpacing: "0.06em" }}>
                          <th style={{ padding: "8px", textAlign: "left" }}>RULE</th>
                          <th style={{ padding: "8px", textAlign: "center" }}>SIGNALS</th>
                          <th style={{ padding: "8px", textAlign: "center" }}>+5m HIT</th>
                          <th style={{ padding: "8px", textAlign: "center" }}>+5m AVG</th>
                          <th style={{ padding: "8px", textAlign: "center" }}>RANGE</th>
                          <th style={{ padding: "8px", textAlign: "center" }}>+30m HIT</th>
                          <th style={{ padding: "8px", textAlign: "center" }}>+30m AVG</th>
                          <th style={{ padding: "8px", textAlign: "center" }}>RANGE</th>
                          <th style={{ padding: "8px", textAlign: "center" }}>+1d HIT</th>
                          <th style={{ padding: "8px", textAlign: "center" }}>+1d AVG</th>
                          <th style={{ padding: "8px", textAlign: "center" }}>RANGE</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(fwd).map(([ruleName, stats]) => (
                          <tr key={ruleName} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                            <td style={{ padding: "8px", fontWeight: 600 }}>{ruleName}</td>
                            <td style={{ padding: "8px", textAlign: "center" }}>{stats.signal_count}</td>
                            <StatCell s={stats["5m"]} />
                            <StatCell s={stats["30m"]} />
                            <StatCell s={stats["1d"]} />
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Signal log (collapsible) */}
              {signals.length > 0 && (
                <details className="glass-panel" style={{ padding: 20 }}>
                  <summary style={{ cursor: "pointer", fontSize: "0.9rem", fontWeight: 700, listStyle: "none", display: "flex", alignItems: "center", gap: 8 }}>
                    <span>Signal Log ({signals.length} signals)</span>
                  </summary>
                  <div style={{ marginTop: 14, maxHeight: 260, overflowY: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.78rem" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid hsl(var(--border-color))", color: "hsl(var(--text-muted))", fontSize: "0.7rem" }}>
                          <th style={{ padding: "6px 8px", textAlign: "left" }}>TIME</th>
                          <th style={{ padding: "6px 8px", textAlign: "left" }}>SYMBOL</th>
                          <th style={{ padding: "6px 8px", textAlign: "left" }}>RULE</th>
                          <th style={{ padding: "6px 8px", textAlign: "left" }}>PRICE</th>
                        </tr>
                      </thead>
                      <tbody>
                        {signals.map((s, i) => (
                          <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.02)" }}>
                            <td style={{ padding: "6px 8px", color: "hsl(var(--text-muted))" }}>{fmtClock(s.ts)}</td>
                            <td style={{ padding: "6px 8px", fontWeight: 600 }}>{s.symbol}</td>
                            <td style={{ padding: "6px 8px" }}>{s.rule_name}</td>
                            <td style={{ padding: "6px 8px" }}>${s.price.toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              )}
            </>
          )}

          {!result && !loading && !error && (
            <div className="glass-panel" style={{ padding: 48, textAlign: "center", color: "hsl(var(--text-muted))" }}>
              <BarChart3 size={36} style={{ marginBottom: 12, opacity: 0.3 }} />
              <div style={{ fontSize: "0.9rem" }}>Configure the backtest and hit Run to see signals marked on the price chart.</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
