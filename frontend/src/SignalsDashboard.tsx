import React, { useEffect, useRef, useState } from "react";
import { Activity, Radio, Zap, Clock, Gauge, Database, ChevronDown, ChevronRight, TrendingUp, TrendingDown, Minus, CircleDot } from "lucide-react";

const API_BASE = "http://localhost:8000/api/v1";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type Horizon = { stamped: number; hit_rate: number | null; avg_return: number | null };
type RuleStat = {
  id: string;
  name: string;
  enabled: boolean;
  side_label: string | null;
  cooldown_s: number;
  logic: any;
  signal_count: number;
  signals_today: number;
  last_ts: number | null;
  horizons: { "5m": Horizon; "30m": Horizon; "1d": Horizon };
};
type Health = {
  tickers_tracked: number;
  active_tickers: number;
  signals_today: number;
  last_signal_ts: number | null;
  total_signals: number;
  ws_feed: string;
  events_per_sec: number;
  events_per_min: number;
  total_events: number;
  last_event_ts: number | null;
  market_status: "open" | "closed" | "extended-hours" | "unknown" | string;
  market_status_checked_at: number | null;
  market_server_time: string | null;
};

const MARKET_STATUS_DISPLAY: Record<string, { label: string; color: string }> = {
  open:              { label: "Open",    color: "#34d399" },
  "extended-hours":  { label: "Pre/Post", color: "#fbbf24" },
  closed:            { label: "Closed",  color: "#94a3b8" },
  unknown:           { label: "Unknown", color: "#f87171" },
};
type RecentSignal = {
  rule_name: string;
  symbol: string;
  ts: number;
  side_label: string | null;
  price: number;
  message: string;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmtTs(ts: number | null): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString([], {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}
function fmtTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
function fmtRet(v: number | null | undefined): React.ReactNode {
  if (v === null || v === undefined) return <span style={{ color: "hsl(var(--text-muted))" }}>—</span>;
  const pos = v >= 0;
  return <span style={{ color: pos ? "#10b981" : "#ef4444" }}>{pos ? "+" : ""}{v.toFixed(2)}%</span>;
}
function fmtHit(v: number | null): React.ReactNode {
  if (v === null || v === undefined) return <span style={{ color: "hsl(var(--text-muted))" }}>—</span>;
  const good = v >= 50;
  return <span style={{ color: good ? "#34d399" : "#fbbf24" }}>{v.toFixed(0)}%</span>;
}
function SideBadge({ s }: { s: string | null }) {
  const v = s === "bull" || s === "bear" ? s : "neutral";
  const map = {
    bull:    { bg: "rgba(16,185,129,0.12)", color: "#34d399", border: "rgba(16,185,129,0.3)", icon: <TrendingUp size={10} style={{ marginRight: 3 }} /> },
    bear:    { bg: "rgba(239,68,68,0.12)",  color: "#f87171", border: "rgba(239,68,68,0.3)",  icon: <TrendingDown size={10} style={{ marginRight: 3 }} /> },
    neutral: { bg: "rgba(148,163,184,0.12)", color: "#94a3b8", border: "rgba(148,163,184,0.3)", icon: <Minus size={10} style={{ marginRight: 3 }} /> },
  } as const;
  const c = map[v];
  return <span className="badge" style={{ background: c.bg, color: c.color, border: `1px solid ${c.border}` }}>{c.icon}{v}</span>;
}

/** Compact, human-readable summary of a rule's condition tree. */
function summarizeLogic(node: any): string {
  if (!node || typeof node !== "object") return "—";
  if (node.metric) {
    const w = node.window_s ? `(${node.window_s}s)` : "";
    return `${node.metric}${w} ${node.cmp} ${node.value}`;
  }
  if (node.op && Array.isArray(node.children)) {
    const op = String(node.op).toUpperCase();
    if (op === "NOT") return `NOT ${summarizeLogic(node.children[0])}`;
    return node.children.map(summarizeLogic).join(` ${op} `);
  }
  return "—";
}

// ---------------------------------------------------------------------------
// Health strip
// ---------------------------------------------------------------------------
function compactNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function HealthChip({ icon, label, value, color, onClick, expanded }: {
  icon: React.ReactNode; label: string; value: React.ReactNode; color?: string;
  onClick?: () => void; expanded?: boolean;
}) {
  return (
    <div className="glass-panel"
      onClick={onClick}
      style={{ padding: "14px 18px", display: "flex", alignItems: "center", gap: 12, flex: 1, minWidth: 160, cursor: onClick ? "pointer" : "default" }}>
      <div style={{ color: color ?? "#a78bfa" }}>{icon}</div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: "0.72rem", color: "hsl(var(--text-muted))", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
        <div style={{ fontSize: "1.25rem", fontWeight: 700, fontFamily: "var(--font-display)", color: color ?? "inherit" }}>{value}</div>
      </div>
      {onClick && (expanded ? <ChevronDown size={16} color="hsl(var(--text-muted))" /> : <ChevronRight size={16} color="hsl(var(--text-muted))" />)}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SignalsDashboard
// ---------------------------------------------------------------------------
export default function SignalsDashboard() {
  const [health, setHealth] = useState<Health | null>(null);
  const [rules, setRules] = useState<RuleStat[]>([]);
  const [rulesLoading, setRulesLoading] = useState(true);
  const [recent, setRecent] = useState<RecentSignal[]>([]);

  // Expandable tracked-tickers panel
  const [showTickers, setShowTickers] = useState(false);
  const [tickerList, setTickerList] = useState<string[]>([]);
  const [activeSet, setActiveSet] = useState<Set<string>>(new Set());
  const [tickersLoading, setTickersLoading] = useState(false);

  // Health strip — poll every 10s
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      fetch(`${API_BASE}/dashboard/health`)
        .then((r) => r.json())
        .then((d) => { if (!cancelled) setHealth(d); })
        .catch(() => { /* leave stale */ });
    };
    load();
    const id = setInterval(load, 10_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // Rule stats — poll every 30s
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      fetch(`${API_BASE}/rules/stats`)
        .then((r) => r.json())
        .then((d) => { if (!cancelled) { setRules(d.rules || []); setRulesLoading(false); } })
        .catch(() => { if (!cancelled) setRulesLoading(false); });
    };
    load();
    const id = setInterval(load, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // Tracked tickers — fetched lazily when the panel is first expanded
  useEffect(() => {
    if (!showTickers || tickerList.length > 0) return;
    setTickersLoading(true);
    Promise.all([
      fetch(`${API_BASE}/dashboard/universe`).then((r) => r.json()),
      fetch(`${API_BASE}/dashboard/snapshot?limit=5000&sort=dp_trades&order=desc`).then((r) => r.json()),
    ])
      .then(([uni, snap]) => {
        const tickers: string[] = uni.tickers || [];
        const active = new Set<string>(
          (snap.rows || [])
            .filter((row: any) => (row.dp_trades || 0) > 0)
            .map((row: any) => row.symbol)
        );
        setTickerList(tickers);
        setActiveSet(active);
      })
      .catch(() => { /* ignore */ })
      .finally(() => setTickersLoading(false));
  }, [showTickers, tickerList.length]);

  // Recent signals — live SSE
  const recentRef = useRef<RecentSignal[]>([]);
  useEffect(() => {
    fetch(`${API_BASE}/alerts/recent?limit=15`)
      .then((r) => r.json())
      .then((d) => { recentRef.current = d.alerts || []; setRecent([...recentRef.current]); })
      .catch(() => { /* ignore */ });

    const es = new EventSource(`${API_BASE}/alerts/stream`);
    es.onmessage = (ev) => {
      try {
        const sig: RecentSignal = JSON.parse(ev.data);
        const next = [sig, ...recentRef.current].slice(0, 15);
        recentRef.current = next;
        setRecent([...next]);
      } catch { /* ignore */ }
    };
    return () => { es.close(); };
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

      {/* Engine-health strip */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <HealthChip icon={<Radio size={20} />} label="Tickers Tracked"
          value={health ? `${health.active_tickers}/${health.tickers_tracked}` : "—"}
          onClick={() => setShowTickers((v) => !v)} expanded={showTickers} />
        <HealthChip icon={<Zap size={20} />} label="Trades/sec"
          value={health ? health.events_per_sec : "—"} color="#fbbf24" />
        <HealthChip icon={<Database size={20} />} label="Total Ingested"
          value={health ? compactNum(health.total_events) : "—"} color="#60a5fa" />
        <HealthChip icon={<Zap size={20} />} label="Signals Today"
          value={health ? health.signals_today : "—"} color="#34d399" />
        <HealthChip icon={<Activity size={20} />} label="Total Signals"
          value={health ? health.total_signals : "—"} />
        <HealthChip icon={<Clock size={20} />} label="Last Signal"
          value={health ? fmtTs(health.last_signal_ts) : "—"} />
        <HealthChip icon={<Gauge size={20} />} label="WS Feed"
          value={health ? health.ws_feed : "—"} color="#60a5fa" />
        {(() => {
          const status = health?.market_status ?? "unknown";
          const display = MARKET_STATUS_DISPLAY[status] ?? MARKET_STATUS_DISPLAY.unknown;
          return (
            <HealthChip icon={<CircleDot size={20} />} label="Market"
              value={health ? display.label : "—"} color={display.color} />
          );
        })()}
      </div>

      {/* Expandable tracked-tickers panel */}
      {showTickers && (
        <div className="glass-panel" style={{ padding: 20 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
            <Radio size={18} color="#a78bfa" />
            <h3 style={{ fontSize: "1rem", fontWeight: 700 }}>Tracked Universe</h3>
            <span style={{ fontSize: "0.75rem", color: "hsl(var(--text-muted))" }}>
              {tickerList.length} symbols · <span style={{ color: "#34d399" }}>{activeSet.size} active</span> (logged dark trades)
            </span>
          </div>
          {tickersLoading ? (
            <div style={{ padding: 24, textAlign: "center", color: "hsl(var(--text-muted))" }}>Loading universe…</div>
          ) : (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, maxHeight: 280, overflowY: "auto" }}>
              {tickerList.map((sym) => {
                const active = activeSet.has(sym);
                return (
                  <span key={sym} style={{
                    fontFamily: "var(--font-display)", fontSize: "0.78rem", fontWeight: 600,
                    padding: "3px 9px", borderRadius: 6,
                    background: active ? "rgba(52,211,153,0.15)" : "rgba(255,255,255,0.04)",
                    color: active ? "#34d399" : "hsl(var(--text-muted))",
                    border: `1px solid ${active ? "rgba(52,211,153,0.3)" : "rgba(255,255,255,0.06)"}`,
                  }}>{sym}</span>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Rule-centric performance table */}
      <div className="glass-panel" style={{ padding: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
          <Activity size={20} color="#a78bfa" />
          <h3 style={{ fontSize: "1.1rem", fontWeight: 700 }}>Signal Rules Performance</h3>
          <span style={{ fontSize: "0.78rem", color: "hsl(var(--text-muted))" }}>
            lifetime hit-rate & avg forward return per rule
          </span>
        </div>
        {rulesLoading ? (
          <div style={{ padding: 32, textAlign: "center", color: "hsl(var(--text-muted))" }}>Loading rules…</div>
        ) : rules.length === 0 ? (
          <div style={{ padding: 32, textAlign: "center", color: "hsl(var(--text-muted))" }}>No rules defined yet.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid hsl(var(--border-color))", color: "hsl(var(--text-muted))", fontSize: "0.7rem", letterSpacing: "0.05em" }}>
                  <th style={{ padding: "10px 8px", textAlign: "left" }}>RULE</th>
                  <th style={{ padding: "10px 8px", textAlign: "left" }}>SIDE</th>
                  <th style={{ padding: "10px 8px", textAlign: "left" }}>STATE</th>
                  <th style={{ padding: "10px 8px", textAlign: "left" }}>CONDITION</th>
                  <th style={{ padding: "10px 8px", textAlign: "right" }}>TODAY</th>
                  <th style={{ padding: "10px 8px", textAlign: "right" }}>TOTAL</th>
                  <th style={{ padding: "10px 8px", textAlign: "center" }} colSpan={2}>+5m</th>
                  <th style={{ padding: "10px 8px", textAlign: "center" }} colSpan={2}>+30m</th>
                  <th style={{ padding: "10px 8px", textAlign: "center" }} colSpan={2}>+1d</th>
                </tr>
                <tr style={{ borderBottom: "1px solid hsl(var(--border-color))", color: "hsl(var(--text-muted))", fontSize: "0.62rem" }}>
                  <th colSpan={6}></th>
                  <th style={{ padding: "2px 8px", textAlign: "center" }}>hit</th>
                  <th style={{ padding: "2px 8px", textAlign: "center" }}>avg</th>
                  <th style={{ padding: "2px 8px", textAlign: "center" }}>hit</th>
                  <th style={{ padding: "2px 8px", textAlign: "center" }}>avg</th>
                  <th style={{ padding: "2px 8px", textAlign: "center" }}>hit</th>
                  <th style={{ padding: "2px 8px", textAlign: "center" }}>avg</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((r) => (
                  <tr key={r.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)", opacity: r.enabled ? 1 : 0.5 }}>
                    <td style={{ padding: "10px 8px", fontWeight: 600 }}>{r.name}</td>
                    <td style={{ padding: "10px 8px" }}><SideBadge s={r.side_label} /></td>
                    <td style={{ padding: "10px 8px" }}>
                      <span style={{ fontSize: "0.75rem", color: r.enabled ? "#34d399" : "hsl(var(--text-muted))" }}>
                        {r.enabled ? "● enabled" : "○ disabled"}
                      </span>
                    </td>
                    <td style={{ padding: "10px 8px", fontSize: "0.75rem", color: "hsl(var(--text-muted))", maxWidth: 260, fontFamily: "var(--font-display)" }}>
                      {summarizeLogic(r.logic)}
                    </td>
                    <td style={{ padding: "10px 8px", textAlign: "right", fontWeight: 600 }}>{r.signals_today}</td>
                    <td style={{ padding: "10px 8px", textAlign: "right", color: "hsl(var(--text-muted))" }}>{r.signal_count}</td>
                    <td style={{ padding: "10px 8px", textAlign: "center" }}>{fmtHit(r.horizons["5m"].hit_rate)}</td>
                    <td style={{ padding: "10px 8px", textAlign: "center" }}>{fmtRet(r.horizons["5m"].avg_return)}</td>
                    <td style={{ padding: "10px 8px", textAlign: "center" }}>{fmtHit(r.horizons["30m"].hit_rate)}</td>
                    <td style={{ padding: "10px 8px", textAlign: "center" }}>{fmtRet(r.horizons["30m"].avg_return)}</td>
                    <td style={{ padding: "10px 8px", textAlign: "center" }}>{fmtHit(r.horizons["1d"].hit_rate)}</td>
                    <td style={{ padding: "10px 8px", textAlign: "center" }}>{fmtRet(r.horizons["1d"].avg_return)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Recent signals (live) */}
      <div className="glass-panel" style={{ padding: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
          <Zap size={18} color="#34d399" />
          <h3 style={{ fontSize: "1.1rem", fontWeight: 700 }}>Recent Signals</h3>
        </div>
        {recent.length === 0 ? (
          <div style={{ padding: 24, textAlign: "center", color: "hsl(var(--text-muted))", fontSize: "0.9rem" }}>
            Waiting for signals…
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {recent.map((s, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 10px", borderBottom: "1px solid rgba(255,255,255,0.03)", fontSize: "0.85rem" }}>
                <span style={{ color: "hsl(var(--text-muted))", fontSize: "0.75rem", whiteSpace: "nowrap", width: 72 }}>{fmtTime(s.ts)}</span>
                <span style={{ fontWeight: 700, width: 60 }}>{s.symbol}</span>
                <SideBadge s={s.side_label} />
                <span style={{ color: "hsl(var(--text-muted))", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.message}</span>
                <span style={{ fontFamily: "var(--font-display)" }}>${s.price.toFixed(2)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

    </div>
  );
}
