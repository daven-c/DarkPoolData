import { useEffect, useRef, useState } from "react";
import { Activity, Clock, Filter, Minus, TrendingDown, TrendingUp } from "lucide-react";

import { API_BASE } from "./api";

const MAX_LIVE = 100;

type Signal = {
  rule_id: string;
  rule_name: string;
  symbol: string;
  ts: number;
  kind: string;
  side_label: string | null;
  price: number;
  message: string;
  // history only
  id?: string;
  forward_5m?: number | null;
  forward_30m?: number | null;
  forward_1d?: number | null;
};

function fmtTs(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
function fmtDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString([], { month: "short", day: "numeric" });
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
    <span className="badge" style={{ background: c.bg, color: c.color, border: `1px solid ${c.border}` }}>
      {c.icon}{v}
    </span>
  );
}

function SignalRow({ sig, showFwd = false }: { sig: Signal; showFwd?: boolean }) {
  return (
    <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
      <td style={{ padding: "10px 8px", whiteSpace: "nowrap", fontSize: "0.78rem", color: "hsl(var(--text-muted))" }}>
        <div>{fmtTs(sig.ts)}</div>
        <div style={{ fontSize: "0.72rem" }}>{fmtDate(sig.ts)}</div>
      </td>
      <td style={{ padding: "10px 8px", fontWeight: 700 }}>{sig.symbol}</td>
      <td style={{ padding: "10px 8px" }}>{sig.rule_name}</td>
      <td style={{ padding: "10px 8px" }}><SideBadge s={sig.side_label} /></td>
      <td style={{ padding: "10px 8px", fontFamily: "var(--font-display)" }}>${sig.price.toFixed(2)}</td>
      {showFwd && (
        <>
          <td style={{ padding: "10px 8px", textAlign: "center" }}>{fmtRet(sig.forward_5m)}</td>
          <td style={{ padding: "10px 8px", textAlign: "center" }}>{fmtRet(sig.forward_30m)}</td>
          <td style={{ padding: "10px 8px", textAlign: "center" }}>{fmtRet(sig.forward_1d)}</td>
        </>
      )}
    </tr>
  );
}

export default function AlertsFeed() {
  const [view, setView] = useState<"live" | "history">("live");
  const [live, setLive] = useState<Signal[]>([]);
  const [connected, setConnected] = useState(false);
  const [history, setHistory] = useState<Signal[]>([]);
  const [histLoading, setHistLoading] = useState(false);

  // Filters
  const [filterSym, setFilterSym] = useState("");
  const [filterRule, setFilterRule] = useState("");

  const liveRef = useRef<Signal[]>([]);

  // SSE live stream
  useEffect(() => {
    const es = new EventSource(`${API_BASE}/alerts/stream`);
    es.onopen = () => setConnected(true);
    es.onmessage = (ev) => {
      try {
        const sig: Signal = JSON.parse(ev.data);
        const next = [sig, ...liveRef.current].slice(0, MAX_LIVE);
        liveRef.current = next;
        setLive([...next]);
      } catch { /* ignore */ }
    };
    es.onerror = () => setConnected(false);
    return () => { es.close(); setConnected(false); };
  }, []);

  // Fetch history when switching to that view
  useEffect(() => {
    if (view !== "history") return;
    setHistLoading(true);
    const params = new URLSearchParams({ limit: "200" });
    if (filterSym) params.set("symbol", filterSym.toUpperCase());
    if (filterRule) params.set("rule_name", filterRule);
    fetch(`${API_BASE}/alerts/history?${params}`)
      .then((r) => r.json())
      .then((d) => { setHistory(d.alerts || []); setHistLoading(false); })
      .catch(() => setHistLoading(false));
  }, [view, filterSym, filterRule]);

  const filteredLive = live.filter((s) => {
    if (filterSym && !s.symbol.includes(filterSym.toUpperCase())) return false;
    if (filterRule && !s.rule_name.toLowerCase().includes(filterRule.toLowerCase())) return false;
    return true;
  });

  // Hit-rate summary for history
  const hitStats = history.length > 0 ? (() => {
    const stamped5m = history.filter(s => s.forward_5m !== null && s.forward_5m !== undefined);
    const stamped30m = history.filter(s => s.forward_30m !== null && s.forward_30m !== undefined);
    const hit5m = stamped5m.filter(s => (s.forward_5m ?? 0) > 0).length;
    const hit30m = stamped30m.filter(s => (s.forward_30m ?? 0) > 0).length;
    return {
      total: history.length,
      stamped5m: stamped5m.length,
      hit5m: stamped5m.length > 0 ? (hit5m / stamped5m.length * 100).toFixed(1) : null,
      stamped30m: stamped30m.length,
      hit30m: stamped30m.length > 0 ? (hit30m / stamped30m.length * 100).toFixed(1) : null,
    };
  })() : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

      {/* Header + sub-tabs */}
      <div className="glass-panel" style={{ padding: "20px 24px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Activity size={20} color="#a78bfa" />
            <h3 style={{ fontSize: "1.1rem", fontWeight: 700 }}>Signal Alerts Feed</h3>
            <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: "0.75rem", color: connected ? "#10b981" : "hsl(var(--text-muted))" }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: connected ? "#10b981" : "hsl(var(--text-muted))" }} />
              {connected ? "Live" : "Connecting…"}
            </span>
          </div>
          <div style={{ display: "flex", gap: 4 }}>
            {(["live", "history"] as const).map((v) => (
              <button key={v} className={`tab-btn ${view === v ? "active" : ""}`} onClick={() => setView(v)}>
                {v === "live" ? "Live Feed" : "History & Returns"}
              </button>
            ))}
          </div>
        </div>

        {/* Filter row */}
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <Filter size={14} color="hsl(var(--text-muted))" />
          <input
            className="input-field"
            placeholder="Symbol filter"
            value={filterSym}
            onChange={(e) => setFilterSym(e.target.value.toUpperCase())}
            style={{ width: 130 }}
          />
          <input
            className="input-field"
            placeholder="Rule name filter"
            value={filterRule}
            onChange={(e) => setFilterRule(e.target.value)}
            style={{ width: 200 }}
          />
          {view === "history" && (
            <button className="btn-primary" style={{ padding: "7px 16px", fontSize: "0.85rem" }}
              onClick={() => { setView("live"); setTimeout(() => setView("history"), 0); }}>
              Refresh
            </button>
          )}
        </div>
      </div>

      {/* History hit-rate summary */}
      {view === "history" && hitStats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 16 }}>
          {[
            { label: "Total Signals", value: hitStats.total, color: "#a78bfa" },
            { label: "Hit Rate +5m", value: hitStats.hit5m ? `${hitStats.hit5m}%` : "—", color: "#10b981" },
            { label: "Hit Rate +30m", value: hitStats.hit30m ? `${hitStats.hit30m}%` : "—", color: "#10b981" },
            { label: "Stamped (+5m)", value: `${hitStats.stamped5m} / ${hitStats.total}`, color: "hsl(var(--text-muted))" },
          ].map((c) => (
            <div key={c.label} className="glass-panel" style={{ padding: "16px 20px" }}>
              <span style={{ fontSize: "0.75rem", color: "hsl(var(--text-muted))" }}>{c.label}</span>
              <div style={{ fontSize: "1.5rem", fontWeight: 700, color: c.color, fontFamily: "var(--font-display)", marginTop: 4 }}>
                {c.value}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Main table */}
      <div className="glass-panel" style={{ padding: 24 }}>
        {view === "live" ? (
          filteredLive.length === 0 ? (
            <div style={{ padding: 32, textAlign: "center", color: "hsl(var(--text-muted))", fontSize: "0.9rem" }}>
              <Clock size={28} style={{ marginBottom: 8, opacity: 0.4 }} /><br />
              Waiting for signals… rules fire when market conditions are met.
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid hsl(var(--border-color))", color: "hsl(var(--text-muted))", fontSize: "0.72rem", letterSpacing: "0.06em" }}>
                    <th style={{ padding: "10px 8px", textAlign: "left" }}>TIME</th>
                    <th style={{ padding: "10px 8px", textAlign: "left" }}>SYMBOL</th>
                    <th style={{ padding: "10px 8px", textAlign: "left" }}>RULE</th>
                    <th style={{ padding: "10px 8px", textAlign: "left" }}>SIDE</th>
                    <th style={{ padding: "10px 8px", textAlign: "left" }}>PRICE</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredLive.map((s, i) => <SignalRow key={i} sig={s} />)}
                </tbody>
              </table>
            </div>
          )
        ) : histLoading ? (
          <div style={{ padding: 32, textAlign: "center", color: "hsl(var(--text-muted))" }}>Loading history…</div>
        ) : history.length === 0 ? (
          <div style={{ padding: 32, textAlign: "center", color: "hsl(var(--text-muted))", fontSize: "0.9rem" }}>
            No historical alerts yet. Signals will appear here once the platform fires them.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid hsl(var(--border-color))", color: "hsl(var(--text-muted))", fontSize: "0.72rem", letterSpacing: "0.06em" }}>
                  <th style={{ padding: "10px 8px", textAlign: "left" }}>TIME</th>
                  <th style={{ padding: "10px 8px", textAlign: "left" }}>SYMBOL</th>
                  <th style={{ padding: "10px 8px", textAlign: "left" }}>RULE</th>
                  <th style={{ padding: "10px 8px", textAlign: "left" }}>SIDE</th>
                  <th style={{ padding: "10px 8px", textAlign: "left" }}>PRICE</th>
                  <th style={{ padding: "10px 8px", textAlign: "center" }}>+5m RET</th>
                  <th style={{ padding: "10px 8px", textAlign: "center" }}>+30m RET</th>
                  <th style={{ padding: "10px 8px", textAlign: "center" }}>+1d RET</th>
                </tr>
              </thead>
              <tbody>
                {history.map((s, i) => <SignalRow key={s.id ?? i} sig={s} showFwd />)}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
