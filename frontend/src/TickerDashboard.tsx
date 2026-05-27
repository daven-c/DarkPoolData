import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Download, HelpCircle } from "lucide-react";

const API_BASE = "http://localhost:8000/api/v1";

type Row = {
  symbol: string;
  total_amount: number;
  daily_change_pct: number | null;
  at_ask: number;
  at_bid: number;
  net_value: number;
  dp_trades: number;
  block_trades: number;
};

type SortKey =
  | "symbol"
  | "total_amount"
  | "daily_change_pct"
  | "at_ask"
  | "at_bid"
  | "net_value"
  | "dp_trades"
  | "block_trades";

const PAGE_SIZE = 15;
const INITIAL_FETCH_LIMIT = 5000; // matches DASHBOARD_MAX_LIMIT in backend Settings

function hashHue(symbol: string): number {
  let h = 0;
  for (let i = 0; i < symbol.length; i++) {
    h = (h * 31 + symbol.charCodeAt(i)) >>> 0;
  }
  return h % 360;
}

function formatMoney(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${(n / 1e3).toFixed(2)}K`;
  return n.toFixed(2);
}

function formatPct(n: number | null): string {
  if (n === null || !isFinite(n)) return "—";
  return `${n.toFixed(2)}%`;
}

function downloadRowCsv(row: Row) {
  const headers = [
    "symbol",
    "total_amount",
    "daily_change_pct",
    "at_ask",
    "at_bid",
    "net_value",
    "dp_trades",
    "block_trades",
  ];
  const values = headers.map((h) => String((row as any)[h] ?? ""));
  const csv = `${headers.join(",")}\n${values.join(",")}\n`;
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${row.symbol}_darkpool.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function TickerLogo({ symbol }: { symbol: string }) {
  const hue = hashHue(symbol);
  const letters = symbol.slice(0, symbol.length >= 4 ? 2 : 1);
  return (
    <div
      aria-label={symbol}
      style={{
        width: 28,
        height: 28,
        borderRadius: "50%",
        background: `linear-gradient(135deg, hsl(${hue} 70% 55%) 0%, hsl(${(hue + 40) % 360} 65% 40%) 100%)`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
        fontSize: letters.length === 1 ? "0.78rem" : "0.65rem",
        fontWeight: 700,
        letterSpacing: "0.02em",
        color: "white",
        textShadow: "0 1px 1px rgba(0,0,0,0.35)",
      }}
    >
      {letters}
    </div>
  );
}

function SortHeader({
  label,
  field,
  sort,
  setSort,
  tooltip,
}: {
  label: string;
  field: SortKey;
  sort: { key: SortKey; order: "asc" | "desc" };
  setSort: (s: { key: SortKey; order: "asc" | "desc" }) => void;
  tooltip?: string;
}) {
  const active = sort.key === field;
  return (
    <th
      style={{
        padding: "12px 8px",
        textAlign: "left",
        cursor: "pointer",
        userSelect: "none",
        whiteSpace: "nowrap",
        color: active ? "#fff" : "hsl(var(--text-muted))",
        fontSize: "0.72rem",
        letterSpacing: "0.08em",
        fontWeight: 600,
      }}
      onClick={() =>
        setSort({ key: field, order: active && sort.order === "desc" ? "asc" : "desc" })
      }
    >
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        {label}
        {tooltip && <HelpCircle size={11} style={{ opacity: 0.6 }} />}
        {active && (sort.order === "desc" ? <ArrowDown size={11} /> : <ArrowUp size={11} />)}
      </span>
    </th>
  );
}

export default function TickerDashboard() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<{ key: SortKey; order: "asc" | "desc" }>({
    key: "total_amount",
    order: "desc",
  });
  const rowsByKey = useRef<Map<string, Row>>(new Map());

  // Initial snapshot
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`${API_BASE}/dashboard/snapshot?page=1&limit=${INITIAL_FETCH_LIMIT}&sort=total_amount&order=desc`)
      .then((r) => {
        if (!r.ok) throw new Error(`snapshot ${r.status}`);
        return r.json();
      })
      .then((data) => {
        if (cancelled) return;
        const next = new Map<string, Row>();
        for (const row of data.rows as Row[]) next.set(row.symbol, row);
        rowsByKey.current = next;
        setRows(Array.from(next.values()));
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e.message || "Failed to load dashboard snapshot");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Livestream via SSE
  useEffect(() => {
    const es = new EventSource(`${API_BASE}/dashboard/stream`);
    es.onmessage = (ev) => {
      try {
        const delta = JSON.parse(ev.data) as Row;
        rowsByKey.current.set(delta.symbol, delta);
        setRows(Array.from(rowsByKey.current.values()));
      } catch {
        /* ignore */
      }
    };
    es.onerror = () => {
      // EventSource auto-retries; don't surface as fatal
    };
    return () => es.close();
  }, []);

  const sortedRows = useMemo(() => {
    const copy = [...rows];
    const { key, order } = sort;
    copy.sort((a, b) => {
      const av = (a as any)[key];
      const bv = (b as any)[key];
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      if (typeof av === "string") return order === "desc" ? bv.localeCompare(av) : av.localeCompare(bv);
      return order === "desc" ? bv - av : av - bv;
    });
    return copy;
  }, [rows, sort]);

  const total = sortedRows.length;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, pages);
  const start = (safePage - 1) * PAGE_SIZE;
  const visible = sortedRows.slice(start, start + PAGE_SIZE);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="glass-panel" style={{ padding: 24 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div>
            <h3 style={{ fontSize: "1.1rem", fontWeight: 700 }}>Darkpool Ticker Dashboard</h3>
            <span style={{ fontSize: "0.75rem", color: "hsl(var(--text-muted))" }}>
              Livestreaming TRF activity • Top {total} tickers by prior-day dollar volume
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.75rem", color: "hsl(var(--text-muted))" }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: "#10b981" }} />
            Live
          </div>
        </div>

        {error && (
          <div style={{ padding: 12, color: "#f87171", fontSize: "0.85rem" }}>{error}</div>
        )}
        {loading && !error && (
          <div style={{ padding: 12, color: "hsl(var(--text-muted))", fontSize: "0.85rem" }}>
            Loading initial snapshot…
          </div>
        )}

        {!loading && !error && (
          <>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.88rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid hsl(var(--border-color))" }}>
                    <SortHeader label="SYMBOL" field="symbol" sort={sort} setSort={setSort} />
                    <SortHeader label="TOTAL AMOUNT" field="total_amount" sort={sort} setSort={setSort} />
                    <SortHeader label="DAILY AMOUNT CHANGE" field="daily_change_pct" sort={sort} setSort={setSort} />
                    <SortHeader label="AT ASK" field="at_ask" sort={sort} setSort={setSort} tooltip="approx via Lee-Ready tick test" />
                    <SortHeader label="AT BID" field="at_bid" sort={sort} setSort={setSort} tooltip="approx via Lee-Ready tick test" />
                    <SortHeader label="NET VALUE" field="net_value" sort={sort} setSort={setSort} tooltip="AT ASK − AT BID" />
                    <SortHeader label="DP TRADES" field="dp_trades" sort={sort} setSort={setSort} />
                    <SortHeader label="BLOCK TRADES" field="block_trades" sort={sort} setSort={setSort} tooltip="size ≥ 10,000 shares" />
                    <th style={{ padding: "12px 8px", textAlign: "left", color: "hsl(var(--text-muted))", fontSize: "0.72rem", letterSpacing: "0.08em", fontWeight: 600 }}>CSV</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((r) => {
                    const changePos = (r.daily_change_pct ?? 0) >= 0;
                    const netPos = r.net_value >= 0;
                    return (
                      <tr key={r.symbol} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                        <td style={{ padding: "12px 8px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <TickerLogo symbol={r.symbol} />
                            <span style={{ fontWeight: 600 }}>{r.symbol}</span>
                          </div>
                        </td>
                        <td style={{ padding: "12px 8px" }}>{formatMoney(r.total_amount)}</td>
                        <td style={{ padding: "12px 8px", color: r.daily_change_pct === null ? "hsl(var(--text-muted))" : changePos ? "#10b981" : "#ef4444" }}>
                          {formatPct(r.daily_change_pct)}
                        </td>
                        <td style={{ padding: "12px 8px" }}>{formatMoney(r.at_ask)}</td>
                        <td style={{ padding: "12px 8px" }}>{formatMoney(r.at_bid)}</td>
                        <td style={{ padding: "12px 8px", color: netPos ? "#10b981" : "#ef4444" }}>
                          {netPos ? "" : "-"}{formatMoney(Math.abs(r.net_value))}
                        </td>
                        <td style={{ padding: "12px 8px" }}>{r.dp_trades}</td>
                        <td style={{ padding: "12px 8px" }}>{r.block_trades}</td>
                        <td style={{ padding: "12px 8px" }}>
                          <button
                            onClick={() => downloadRowCsv(r)}
                            style={{ background: "transparent", border: "none", color: "#60a5fa", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4 }}
                            title="Export row as CSV"
                          >
                            <Download size={14} />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 16, fontSize: "0.8rem", color: "hsl(var(--text-muted))" }}>
              <span>
                Showing {total === 0 ? 0 : start + 1} to {Math.min(start + PAGE_SIZE, total)} of {total} entries
              </span>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  className="tab-btn"
                  disabled={safePage <= 1}
                  onClick={() => setPage(safePage - 1)}
                  style={{ opacity: safePage <= 1 ? 0.4 : 1 }}
                >
                  Prev
                </button>
                <span style={{ alignSelf: "center" }}>
                  Page {safePage} / {pages}
                </span>
                <button
                  className="tab-btn"
                  disabled={safePage >= pages}
                  onClick={() => setPage(safePage + 1)}
                  style={{ opacity: safePage >= pages ? 0.4 : 1 }}
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
