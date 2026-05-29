# ROADMAP — Darkpool Signal Platform Redesign

> **Living progress tracker.** Update the checkboxes as work lands so this task is resumable if interrupted. Agents: read this first, then `AGENTS.md`.
> Status legend: `[ ]` not started · `[~]` in progress · `[x]` done.

## Goal

Ingest darkpool (TRF) data → fire tickers when composable rules trigger (whale buys, sweeps, price action, dark-pool ratio, net flow…) → deliver alerts to **in-app feed + Discord + persisted history** → measure profitability via **signal-quality forward returns + Portfolio P&L** backtesting and a **composable Strategy Lab** UI.

## Architecture (the one idea)

A **Rule = a composable `Condition` tree evaluated against a stream of `MarketEvent`s.** The same `RuleEngine` runs:
- **Live**: `stream.py` (WS) → `RuleEngine.process()` → `Signal`s → `AlertDispatcher` (SSE + Discord + SQLite).
- **Backtest**: `APIDataProvider` (historical trades) → `RuleEngine` → forward-return stats + `Portfolio` P&L.

Persisted live alerts get **forward-return stamped** over time, so live signals become an evaluable dataset identical to backtest output.

---

## Progress

### Phase 0 — Docs & handoff  `[x]`
- [x] Rename `CLAUDE.md` → `AGENTS.md`
- [x] Create this `ROADMAP.md` tracker
- [x] Point `AGENTS.md` at ROADMAP + rule-engine architecture
- [x] Update `README.md` with redesign direction

### Phase 1 — Rules core (`backend/app/rules/`)  `[x]`  → PR #2
- [x] `events.py` — `MarketEvent`, `TickerState` (running totals + recent-trades deque + session OHLC). Generalizes `services/aggregator.py` math.
- [x] `metrics.py` — metric catalog: `trade_notional, trade_size, side, is_block, net_flow_notional, session_total_notional, block_count, daily_change_pct, price_move_pct(w), trade_count_window(w), notional_window(w), ask_notional_window(w)`; `METRICS` registry + `catalog()` for the builder UI. (NOTE: `dark_ratio`/`volume_vs_avg` deferred — need full lit+dark feed; engine currently fed TRF-only like the dashboard.)
- [x] `conditions.py` — composable tree: leaf `{metric, window_s?, cmp, value}`, composite `{op: and|or|not, children}`; `compile_condition()` + `evaluate(event, state)` + `validate_logic()`.
- [x] `rule.py` — `Rule` (id, name, enabled, severity, side_label, kind, cooldown_s, logic) + `Signal`; `matches()` / `make_signal()` / `to_dict` / `from_dict`.
- [x] `engine.py` — `RuleEngine` (per-ticker `TickerState` + active rules, `process()`, per-(rule,symbol) cooldown, `set_rules()`, `snapshot()`, `preview()`).
- [x] `builtins.py` — seed rules as Condition trees (Whale Buy, Block, Bullish Sweep, Price Breakout, Bearish Net Flow).
- [x] `tests/` — 11 pytest cases (whale ask/bid, cooldown, sweep window, price move, composite or/not, serialization round-trip). **Verified:** `pytest backend/app/rules/tests` → 11 passed.

### Phase 2 — Unify aggregator into engine state  `[x]`
- [x] Fold `DashboardAggregator` (`services/aggregator.py`) into `TickerState`; engine owns state.
- [x] `/dashboard/*` endpoints read engine snapshot. **Verified:** dashboard snapshot returns live numbers.

### Phase 3 — Live alerting  `[x]`
- [x] `services/alerts.py` — `AlertDispatcher` fan-out to SSE + Discord (`DiscordNotifier`) + SQLite `alerts` table.
- [x] Forward-return stamper background task (+5m/+30m/+1d via `massive` REST).
- [x] `stream.py` feeds engine; signals → dispatcher.
- [x] `api/alerts.py` — `GET /alerts/stream` (SSE), `/alerts/recent`, `/alerts/history`.
- [x] `main.py` lifespan wiring.

### Phase 4 — Rule CRUD + Strategy Lab API  `[x]`
- [x] `services/rules_store.py` — SQLite `rules` table; seed builtins on first boot.
- [x] `api/rules.py` — `GET/POST/PATCH/DELETE /rules`, `GET /rules/metrics`, `POST /rules/preview`. Hot-reload engine on mutation.

### Phase 5 — Rule backtesting  `[x]`
- [x] `services/backtest_rules.py` — replay historical trades → signals; forward-return stats; `Portfolio` wired for equity/Sharpe/drawdown.
- [x] `api/backtest.py` — `POST /backtest/rules` returns `{signals, forward_return_stats, equity_curve, portfolio_metrics}`.

### Phase 6 — Frontend tabs  `[x]`
- [x] `AlertsFeed.tsx` — live SSE feed + `/alerts/history` profitability table with forward-return columns.
- [x] `StrategyLab.tsx` — composable rule builder (metric ▸ cmp ▸ value ▸ window; AND/OR groups; JSON escape hatch; preview; enable/disable toggle).
- [x] `RuleBacktest.tsx` — portfolio metric cards + forward-return stats table + Recharts equity curve + signal log.
- [x] Wire all tabs into `App.tsx` (6-tab nav: Dashboard · Alerts · Strategy Lab · Rule Backtest · Indicator Visualizer · Scanner). **Verified:** `npm run build --prefix frontend` passes clean.

### Phase 7 — Final docs + verify  `[x]`
- [x] Update `README.md` + `AGENTS.md` with final endpoints/architecture.
- [x] ROADMAP fully up to date.

### Phase 8 — Multi-Tenant Rule Indexing & Deduplication  `[x]`
- [x] `backend/app/rules/index.py` — Dynamic 1D index tree grouping leaf conditions, using `bisect` for fast $O(\log N)$ range inequalities and Hash Maps for $O(1)$ equality checks.
- [x] `backend/app/rules/evaluator.py` — Boolean propagation network (`EvalNode` and compilers) to evaluate flattened rule logic with logical short-circuiting.
- [x] Leaf Deduplication with 2-Decimal Precision rounding to maximize condition reuse.
- [x] Eager Metric Caching in `RuleEngine` to calculate metrics exactly once per market tick.
- [x] Optimization benchmark testing with 1,000 rules processing ticks in under 0.6ms.

---

## Config keys added (`backend/app/core/config.py`)
`ALERTS_FORWARD_HORIZONS_MIN=[5,30,1440]`, `ALERTS_DEFAULT_COOLDOWN_S=300`, `ALERTS_SSE_QUEUE_MAX=1000`, `BACKTEST_DEFAULT_NOTIONAL=10000` (all env-overridable).

## Out of scope (separate efforts)
- NBBO quote-join for exact at-bid/at-ask (v1.1; tick-test for now) — see chat history.
- Supabase auth gate (`AUTH.md`) and prod deploy (`DEPLOYMENT.md`).
- Live paper-trading via `Portfolio` (backtest-only for now).
