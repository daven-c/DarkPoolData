import { useCallback, useEffect, useState } from "react";
import { BarChart3, Eye, FlaskConical, Plus, Save, Trash2, ToggleLeft, ToggleRight } from "lucide-react";
import RuleBacktest from "./RuleBacktest";

const API_BASE = "http://localhost:8000/api/v1";

type MetricSpec = {
  key: string;
  label: string;
  value_type: string; // "number" | "enum" | "bool"
  params: { name: string; type: string; default: number }[];
  enum_values: string[] | null;
  help: string;
};

type RuleRow = {
  id: string;
  name: string;
  enabled: boolean;
  side_label: string | null;
  kind: string;
  cooldown_s: number;
  logic: object;
  is_builtin: boolean;
};

type ConditionLeaf = {
  metric: string;
  cmp: string;
  value: string | number;
  window_s?: number;
};

const CMPS = [">=", ">", "<=", "<", "==", "!="];
const KINDS = ["SIGNAL", "WHALE", "SWEEP", "BREAKOUT", "BLOCK", "FLOW"];
const SIDES = ["", "bull", "bear"];

function SideDot({ s }: { s: string | null }) {
  const v = s === "bull" || s === "bear" ? s : "neutral";
  const colors: Record<string, string> = { bull: "#34d399", bear: "#f87171", neutral: "#94a3b8" };
  return <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: colors[v], marginRight: 5 }} />;
}

function emptyLeaf(metrics: MetricSpec[]): ConditionLeaf {
  return { metric: metrics[0]?.key ?? "trade_notional", cmp: ">=", value: 0 };
}

export default function StrategyLab() {
  const [metrics, setMetrics] = useState<MetricSpec[]>([]);
  const [rules, setRules] = useState<RuleRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Builder state
  const [editId, setEditId] = useState<string | null>(null);
  const [name, setName] = useState("My Rule");
  const [kind, setKind] = useState("SIGNAL");
  const [sideLabel, setSideLabel] = useState("");
  const [cooldown, setCooldown] = useState(300);
  const [groupOp, setGroupOp] = useState<"and" | "or">("and");
  const [conditions, setConditions] = useState<ConditionLeaf[]>([]);
  const [useRawJson, setUseRawJson] = useState(false);
  const [rawJson, setRawJson] = useState("");
  const [jsonError, setJsonError] = useState("");

  // Preview state
  const [previewing, setPreviewing] = useState(false);
  const [previewMatches, setPreviewMatches] = useState<string[] | null>(null);

  // Save state
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  // Lab sub-view: author rules ("builder") vs. backtest them ("backtest")
  const [labView, setLabView] = useState<"builder" | "backtest">("builder");
  const [backtestRuleId, setBacktestRuleId] = useState<string | undefined>(undefined);

  const loadAll = useCallback(() => {
    setLoading(true);
    Promise.all([
      fetch(`${API_BASE}/rules/metrics`).then(r => r.json()),
      fetch(`${API_BASE}/rules`).then(r => r.json()),
    ]).then(([mData, rData]) => {
      const m: MetricSpec[] = mData.metrics ?? [];
      setMetrics(m);
      setRules(rData.rules ?? []);
      if (conditions.length === 0) setConditions([emptyLeaf(m)]);
      setLoading(false);
    }).catch(() => { setError("Failed to load rules"); setLoading(false); });
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  function resetForm() {
    setEditId(null);
    setName("My Rule");
    setKind("SIGNAL");
    setSideLabel("");
    setCooldown(300);
    setGroupOp("and");
    setConditions([emptyLeaf(metrics)]);
    setUseRawJson(false);
    setRawJson("");
    setJsonError("");
    setPreviewMatches(null);
    setSaveMsg("");
  }

  function loadForEdit(r: RuleRow) {
    setEditId(r.id);
    setName(r.name);
    setKind(r.kind);
    setSideLabel(r.side_label ?? "");
    setCooldown(r.cooldown_s);
    // Try to parse logic into flat conditions, fall back to raw JSON
    const logic = r.logic as any;
    if (logic.op && (logic.op === "and" || logic.op === "or") && Array.isArray(logic.children)) {
      const leaves = logic.children.filter((c: any) => c.metric);
      if (leaves.length === logic.children.length) {
        setGroupOp(logic.op as "and" | "or");
        setConditions(leaves.map((c: any) => ({ ...c, value: c.value ?? 0 })));
        setUseRawJson(false);
        setRawJson("");
        setPreviewMatches(null);
        setSaveMsg("");
        return;
      }
    }
    if (logic.metric) {
      setConditions([logic]);
      setGroupOp("and");
      setUseRawJson(false);
      setRawJson("");
      setPreviewMatches(null);
      setSaveMsg("");
      return;
    }
    // Complex tree — fall back to raw JSON
    setUseRawJson(true);
    setRawJson(JSON.stringify(logic, null, 2));
    setConditions([]);
    setPreviewMatches(null);
    setSaveMsg("");
  }

  function buildLogic(): object | null {
    if (useRawJson) {
      try {
        const parsed = JSON.parse(rawJson);
        setJsonError("");
        return parsed;
      } catch {
        setJsonError("Invalid JSON");
        return null;
      }
    }
    if (conditions.length === 0) return null;
    const leaves = conditions.map(c => {
      const leaf: any = { metric: c.metric, cmp: c.cmp, value: Number(c.value) };
      if (c.window_s) leaf.window_s = Number(c.window_s);
      return leaf;
    });
    return leaves.length === 1 ? leaves[0] : { op: groupOp, children: leaves };
  }

  async function handlePreview() {
    const logic = buildLogic();
    if (!logic) return;
    setPreviewing(true);
    setPreviewMatches(null);
    try {
      const r = await fetch(`${API_BASE}/rules/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ logic, side_label: sideLabel || null, kind, cooldown_s: cooldown }),
      });
      const d = await r.json();
      if (!r.ok) { setSaveMsg(`Preview error: ${d.detail}`); }
      else setPreviewMatches(d.matched ?? []);
    } catch (e: any) { setSaveMsg(e.message); }
    finally { setPreviewing(false); }
  }

  async function handleSave() {
    const logic = buildLogic();
    if (!logic) return;
    setSaving(true);
    setSaveMsg("");
    const body = {
      name, logic,
      enabled: true,
      side_label: sideLabel || null,
      kind,
      cooldown_s: cooldown,
    };
    try {
      const url = editId ? `${API_BASE}/rules/${editId}` : `${API_BASE}/rules`;
      const method = editId ? "PATCH" : "POST";
      const r = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await r.json();
      if (!r.ok) { setSaveMsg(`Error: ${d.detail}`); }
      else { setSaveMsg(editId ? "Rule updated!" : "Rule created!"); loadAll(); if (!editId) resetForm(); }
    } catch (e: any) { setSaveMsg(e.message); }
    finally { setSaving(false); }
  }

  async function toggleEnabled(rule: RuleRow) {
    await fetch(`${API_BASE}/rules/${rule.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !rule.enabled }),
    });
    loadAll();
  }

  async function deleteRule(id: string) {
    if (!confirm("Delete this rule?")) return;
    await fetch(`${API_BASE}/rules/${id}`, { method: "DELETE" });
    loadAll();
    if (editId === id) resetForm();
  }

  function addCondition() { setConditions(c => [...c, emptyLeaf(metrics)]); }
  function removeCondition(i: number) { setConditions(c => c.filter((_, j) => j !== i)); }
  function updateCondition(i: number, field: keyof ConditionLeaf, val: any) {
    setConditions(c => c.map((item, j) => j === i ? { ...item, [field]: val } : item));
  }

  const metricByKey = Object.fromEntries(metrics.map(m => [m.key, m]));

  if (loading) return <div className="glass-panel" style={{ padding: 32, textAlign: "center", color: "hsl(var(--text-muted))" }}>Loading…</div>;
  if (error) return <div className="glass-panel" style={{ padding: 24, color: "#f87171" }}>{error}</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* Header */}
      <div className="glass-panel" style={{ padding: "18px 24px", display: "flex", alignItems: "center", gap: 10 }}>
        <FlaskConical size={20} color="#a78bfa" />
        <div>
          <h3 style={{ fontSize: "1.1rem", fontWeight: 700 }}>Strategy Lab</h3>
          <span style={{ fontSize: "0.75rem", color: "hsl(var(--text-muted))" }}>
            Author rules and backtest them — rules here drive the live signal engine
          </span>
        </div>
        <div style={{ display: "flex", gap: 4, marginLeft: "auto" }}>
          {(["builder", "backtest"] as const).map(v => (
            <button key={v}
              className={`tab-btn ${labView === v ? "active" : ""}`}
              onClick={() => { if (v === "builder") setBacktestRuleId(undefined); setLabView(v); }}
            >
              {v === "builder"
                ? <><FlaskConical size={13} style={{ marginRight: 5, verticalAlign: "middle" }} />Builder</>
                : <><BarChart3 size={13} style={{ marginRight: 5, verticalAlign: "middle" }} />Backtest</>}
            </button>
          ))}
        </div>
      </div>

      {labView === "backtest" ? (
        <RuleBacktest initialRuleId={backtestRuleId} />
      ) : (
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.4fr", gap: 20, alignItems: "start" }}>

        {/* Rules list */}
        <div className="glass-panel" style={{ padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <h4 style={{ fontSize: "0.95rem", fontWeight: 700 }}>Platform Rules</h4>
            <button className="btn-primary" style={{ padding: "6px 14px", fontSize: "0.8rem" }} onClick={resetForm}>
              <Plus size={13} /> New
            </button>
          </div>
          {rules.length === 0 ? (
            <p style={{ fontSize: "0.85rem", color: "hsl(var(--text-muted))" }}>No rules yet.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {rules.map(r => (
                <div key={r.id}
                  style={{
                    padding: "10px 14px",
                    borderRadius: 10,
                    border: `1px solid ${editId === r.id ? "rgba(139,92,246,0.5)" : "hsl(var(--border-color))"}`,
                    background: editId === r.id ? "rgba(139,92,246,0.08)" : "rgba(15,23,42,0.3)",
                    cursor: "pointer",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                  onClick={() => loadForEdit(r)}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <SideDot s={r.side_label} />
                      <span style={{ fontWeight: 600, fontSize: "0.88rem", color: r.enabled ? "hsl(var(--text-main))" : "hsl(var(--text-muted))" }}>
                        {r.name}
                      </span>
                      {r.is_builtin && <span style={{ fontSize: "0.65rem", color: "#a78bfa", opacity: 0.7 }}>builtin</span>}
                    </div>
                    <div style={{ fontSize: "0.72rem", color: "hsl(var(--text-muted))", marginTop: 2 }}>
                      {r.kind} · cooldown {r.cooldown_s}s
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                    <button
                      title="Backtest this rule"
                      onClick={e => { e.stopPropagation(); setBacktestRuleId(r.id); setLabView("backtest"); }}
                      style={{ background: "transparent", border: "none", cursor: "pointer", color: "#a78bfa", opacity: 0.8, display: "flex" }}
                    >
                      <BarChart3 size={15} />
                    </button>
                    <button
                      title={r.enabled ? "Disable" : "Enable"}
                      onClick={e => { e.stopPropagation(); toggleEnabled(r); }}
                      style={{ background: "transparent", border: "none", cursor: "pointer", color: r.enabled ? "#10b981" : "hsl(var(--text-muted))", display: "flex" }}
                    >
                      {r.enabled ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
                    </button>
                    <button
                      title="Delete"
                      onClick={e => { e.stopPropagation(); deleteRule(r.id); }}
                      style={{ background: "transparent", border: "none", cursor: "pointer", color: "#ef4444", opacity: 0.6, display: "flex" }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Builder */}
        <div className="glass-panel" style={{ padding: 24 }}>
          <h4 style={{ fontSize: "0.95rem", fontWeight: 700, marginBottom: 16 }}>
            {editId ? "Edit Rule" : "New Rule"}
          </h4>

          {/* Rule metadata */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
            <div>
              <label style={{ fontSize: "0.75rem", color: "hsl(var(--text-muted))", display: "block", marginBottom: 4 }}>Name</label>
              <input className="input-field" style={{ width: "100%" }} value={name} onChange={e => setName(e.target.value)} />
            </div>
            <div>
              <label style={{ fontSize: "0.75rem", color: "hsl(var(--text-muted))", display: "block", marginBottom: 4 }}>Kind</label>
              <select className="input-field" style={{ width: "100%", background: "#0a0f1d" }} value={kind} onChange={e => setKind(e.target.value)}>
                {KINDS.map(k => <option key={k} value={k}>{k}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: "0.75rem", color: "hsl(var(--text-muted))", display: "block", marginBottom: 4 }}>Side Label</label>
              <select className="input-field" style={{ width: "100%", background: "#0a0f1d" }} value={sideLabel} onChange={e => setSideLabel(e.target.value)}>
                <option value="">— neutral —</option>
                {SIDES.filter(s => s).map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: "0.75rem", color: "hsl(var(--text-muted))", display: "block", marginBottom: 4 }}>Cooldown (seconds)</label>
              <input className="input-field" style={{ width: "100%" }} type="number" min={0} value={cooldown} onChange={e => setCooldown(Number(e.target.value))} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", justifyContent: "flex-end" }}>
              <label style={{ fontSize: "0.75rem", color: "hsl(var(--text-muted))", display: "block", marginBottom: 4 }}>Logic Mode</label>
              <button
                className={useRawJson ? "btn-primary" : "tab-btn"}
                style={{ fontSize: "0.8rem", padding: "8px 14px", height: 38 }}
                onClick={() => {
                  if (!useRawJson) {
                    const l = buildLogic();
                    setRawJson(l ? JSON.stringify(l, null, 2) : "{}");
                  }
                  setUseRawJson(!useRawJson);
                  setJsonError("");
                }}
              >
                {useRawJson ? "Builder mode" : "Raw JSON mode"}
              </button>
            </div>
          </div>

          {/* Condition builder */}
          {!useRawJson ? (
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                <span style={{ fontSize: "0.8rem", fontWeight: 600 }}>Conditions</span>
                {conditions.length > 1 && (
                  <div style={{ display: "flex", gap: 4 }}>
                    {(["and", "or"] as const).map(op => (
                      <button key={op}
                        onClick={() => setGroupOp(op)}
                        style={{
                          padding: "3px 10px", borderRadius: 6, fontSize: "0.75rem", fontWeight: 700, cursor: "pointer",
                          background: groupOp === op ? "#8b5cf6" : "transparent",
                          border: `1px solid ${groupOp === op ? "#8b5cf6" : "hsl(var(--border-color))"}`,
                          color: groupOp === op ? "white" : "hsl(var(--text-muted))",
                        }}
                      >
                        {op.toUpperCase()}
                      </button>
                    ))}
                  </div>
                )}
                <button className="tab-btn" style={{ marginLeft: "auto", fontSize: "0.78rem", padding: "4px 10px" }} onClick={addCondition}>
                  <Plus size={12} /> Add condition
                </button>
              </div>

              {conditions.map((c, i) => {
                const spec = metricByKey[c.metric];
                const hasWindow = spec?.params?.some(p => p.name === "window_s");
                return (
                  <div key={i} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8, flexWrap: "wrap" }}>
                    {i > 0 && (
                      <span style={{ fontSize: "0.72rem", fontWeight: 700, color: "#a78bfa", width: 26, textAlign: "center" }}>
                        {groupOp.toUpperCase()}
                      </span>
                    )}
                    {/* Metric */}
                    <select
                      className="input-field"
                      style={{ background: "#0a0f1d", fontSize: "0.82rem", flex: "1 1 180px", minWidth: 140 }}
                      value={c.metric}
                      onChange={e => updateCondition(i, "metric", e.target.value)}
                    >
                      {metrics.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
                    </select>

                    {/* Comparator */}
                    {spec?.value_type !== "enum" && spec?.value_type !== "bool" && (
                      <select
                        className="input-field"
                        style={{ background: "#0a0f1d", width: 64, fontSize: "0.82rem" }}
                        value={c.cmp}
                        onChange={e => updateCondition(i, "cmp", e.target.value)}
                      >
                        {CMPS.map(op => <option key={op} value={op}>{op}</option>)}
                      </select>
                    )}

                    {/* Value */}
                    {spec?.value_type === "enum" ? (
                      <select
                        className="input-field"
                        style={{ background: "#0a0f1d", width: 80, fontSize: "0.82rem" }}
                        value={String(c.value)}
                        onChange={e => { updateCondition(i, "value", e.target.value); updateCondition(i, "cmp", "=="); }}
                      >
                        {(spec.enum_values ?? []).map(v => <option key={v} value={v}>{v}</option>)}
                      </select>
                    ) : spec?.value_type === "bool" ? (
                      <select
                        className="input-field"
                        style={{ background: "#0a0f1d", width: 80, fontSize: "0.82rem" }}
                        value={String(c.value)}
                        onChange={e => { updateCondition(i, "value", e.target.value === "true"); updateCondition(i, "cmp", "=="); }}
                      >
                        <option value="true">true</option>
                        <option value="false">false</option>
                      </select>
                    ) : (
                      <input
                        className="input-field"
                        type="number"
                        style={{ width: 100, fontSize: "0.82rem" }}
                        value={c.value}
                        onChange={e => updateCondition(i, "value", e.target.value)}
                      />
                    )}

                    {/* Window (optional) */}
                    {hasWindow && (
                      <input
                        className="input-field"
                        type="number"
                        placeholder="window_s"
                        style={{ width: 90, fontSize: "0.82rem" }}
                        value={c.window_s ?? ""}
                        onChange={e => updateCondition(i, "window_s", e.target.value ? Number(e.target.value) : undefined)}
                      />
                    )}

                    {conditions.length > 1 && (
                      <button onClick={() => removeCondition(i)} style={{ background: "transparent", border: "none", color: "#ef4444", cursor: "pointer", opacity: 0.7, display: "flex" }}>
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: "0.75rem", color: "hsl(var(--text-muted))", display: "block", marginBottom: 6 }}>Logic JSON</label>
              <textarea
                className="input-field"
                rows={6}
                style={{ width: "100%", resize: "vertical", fontFamily: "monospace", fontSize: "0.8rem" }}
                value={rawJson}
                onChange={e => { setRawJson(e.target.value); setJsonError(""); }}
              />
              {jsonError && <p style={{ color: "#f87171", fontSize: "0.75rem", marginTop: 4 }}>{jsonError}</p>}
            </div>
          )}

          {/* Preview matches */}
          {previewMatches !== null && (
            <div style={{ padding: "10px 14px", borderRadius: 8, background: "rgba(139,92,246,0.08)", border: "1px solid rgba(139,92,246,0.2)", marginBottom: 14, fontSize: "0.82rem" }}>
              {previewMatches.length === 0
                ? <span style={{ color: "hsl(var(--text-muted))" }}>No tickers match right now.</span>
                : <span><strong style={{ color: "#a78bfa" }}>{previewMatches.length} match{previewMatches.length !== 1 ? "es" : ""}</strong>: {previewMatches.join(", ")}</span>
              }
            </div>
          )}

          {/* Save message */}
          {saveMsg && (
            <div style={{ padding: "8px 12px", borderRadius: 8, marginBottom: 12, fontSize: "0.82rem",
              background: saveMsg.startsWith("Error") ? "rgba(239,68,68,0.1)" : "rgba(16,185,129,0.1)",
              color: saveMsg.startsWith("Error") ? "#f87171" : "#34d399",
              border: `1px solid ${saveMsg.startsWith("Error") ? "rgba(239,68,68,0.2)" : "rgba(16,185,129,0.2)"}`,
            }}>
              {saveMsg}
            </div>
          )}

          {/* Actions */}
          <div style={{ display: "flex", gap: 10 }}>
            <button className="btn-primary" style={{ flex: 1, justifyContent: "center" }} onClick={handlePreview} disabled={previewing}>
              <Eye size={15} /> {previewing ? "Previewing…" : "Preview Now"}
            </button>
            <button className="btn-primary" style={{ flex: 1, justifyContent: "center" }} onClick={handleSave} disabled={saving}>
              <Save size={15} /> {saving ? "Saving…" : editId ? "Update Rule" : "Create Rule"}
            </button>
            {editId && (
              <button className="tab-btn" style={{ padding: "8px 16px" }} onClick={resetForm}>Cancel</button>
            )}
          </div>
        </div>
      </div>
      )}
    </div>
  );
}
