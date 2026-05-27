import React, { useState, useEffect } from "react";
import {
  TrendingUp,
  Activity,
  BarChart3,
  Play,
  AlertTriangle,
  Send,
  MessageSquare,
  LayoutGrid
} from "lucide-react";
import TickerDashboard from "./TickerDashboard";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
  PieChart,
  Pie,
  ReferenceLine,
  Legend
} from "recharts";

const API_BASE = "http://localhost:8000/api/v1";

export default function App() {
  const [activeTab, setActiveTab] = useState<"scanner" | "backtester" | "dashboard">("dashboard");
  const [backendStatus, setBackendStatus] = useState<"connecting" | "online" | "offline">("connecting");

  // Scanner state
  const [scanSymbol, setScanSymbol] = useState("AAPL");
  const [scanDate, setScanDate] = useState("2026-05-22");
  const [scanSummary, setScanSummary] = useState<any>(null);
  const [scanTrades, setScanTrades] = useState<any[]>([]);
  const [scanLoading, setScanLoading] = useState(false);
  const [scanError, setScanError] = useState("");

  // Backtester state
  const [btSymbols, setBtSymbols] = useState("AAPL");
  const [btStartDate, setBtStartDate] = useState("2026-01-01");
  const [btEndDate, setBtEndDate] = useState("2026-05-20");
  const [btStrategy, setBtStrategy] = useState("dark_pool_spike");
  const [btThreshold, setBtThreshold] = useState(0.40);
  const [btLoading, setBtLoading] = useState(false);
  const [btResults, setBtResults] = useState<any>(null);
  const [btError, setBtError] = useState("");

  // Discord Alert state
  const [discordMsg, setDiscordMsg] = useState("");
  const [discordSending, setDiscordSending] = useState(false);
  const [discordSentMessage, setDiscordSentMessage] = useState("");

  // Check backend health on mount
  useEffect(() => {
    fetch("http://localhost:8000/")
      .then((res) => res.json())
      .then((data) => {
        if (data.status === "online") {
          setBackendStatus("online");
        } else {
          setBackendStatus("offline");
        }
      })
      .catch(() => setBackendStatus("offline"));
  }, []);

  const runScanner = async (e: React.FormEvent) => {
    e.preventDefault();
    setScanLoading(true);
    setScanError("");
    setScanSummary(null);
    setScanTrades([]);

    try {
      const resSummary = await fetch(`${API_BASE}/darkpool/summary?symbol=${scanSymbol}&date=${scanDate}`);
      if (!resSummary.ok) throw new Error("Failed to load dark pool summary");
      const summaryData = await resSummary.json();
      setScanSummary(summaryData);

      const resTrades = await fetch(`${API_BASE}/darkpool/trades?symbol=${scanSymbol}&date=${scanDate}&limit=50`);
      if (resTrades.ok) {
        const tradesData = await resTrades.json();
        setScanTrades(tradesData.trades);
      }
    } catch (err: any) {
      setScanError(err.message || "An error occurred fetching scanner data.");
    } finally {
      setScanLoading(false);
    }
  };

  const runBacktester = async (e: React.FormEvent) => {
    e.preventDefault();
    setBtLoading(true);
    setBtError("");
    setBtResults(null);

    const payload = {
      symbols: btSymbols.split(",").map(s => s.trim().toUpperCase()),
      start_date: btStartDate,
      end_date: btEndDate,
      strategy_name: btStrategy,
      strategy_params: btStrategy === "dark_pool_spike" ? {
        dark_ratio_threshold: Number(btThreshold)
      } : {
        fast_period: 10,
        slow_period: 30
      },
      initial_cash: 100000.0
    };

    try {
      const response = await fetch(`${API_BASE}/backtest/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Backtest calculation failed.");
      }
      setBtResults(data);
    } catch (err: any) {
      setBtError(err.message || "An error occurred during backtesting.");
    } finally {
      setBtLoading(false);
    }
  };

  const sendDiscordAlert = async (msg: string) => {
    setDiscordSending(true);
    setDiscordSentMessage("");
    try {
      // Connect to bot receiver
      const response = await fetch("http://localhost:5000/alert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg })
      });
      const data = await response.json();
      if (response.ok && data.success) {
        setDiscordSentMessage("✅ Alert pushed to Discord successfully!");
      } else {
        setDiscordSentMessage(`❌ Failed: ${data.error || "Bot server offline"}`);
      }
    } catch (err) {
      setDiscordSentMessage("❌ Error: Could not connect to Discord Bot helper (localhost:5000)");
    } finally {
      setDiscordSending(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Navbar */}
      <header className="glass-panel" style={{ margin: "16px 24px", padding: "16px 24px", borderRadius: "12px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div style={{ width: "40px", height: "40px", borderRadius: "8px", background: "linear-gradient(135deg, #8b5cf6 0%, #3b82f6 100%)", display: "flex", alignItems: "center", justifyItems: "center", justifyContent: "center" }}>
            <Activity size={24} color="white" />
          </div>
          <div>
            <h1 style={{ fontSize: "1.4rem", fontWeight: 800 }} className="gradient-text">DARK POOL DATA</h1>
            <span style={{ fontSize: "0.75rem", color: "hsl(var(--text-muted))" }}>INSTITUTIONAL LIQUIDITY TRACKER</span>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav style={{ display: "flex", gap: "8px" }}>
          <button className={`tab-btn ${activeTab === "dashboard" ? "active" : ""}`} onClick={() => setActiveTab("dashboard")}>
            <LayoutGrid size={16} style={{ marginRight: "6px", verticalAlign: "middle" }} /> Ticker Dashboard
          </button>
          <button className={`tab-btn ${activeTab === "backtester" ? "active" : ""}`} onClick={() => setActiveTab("backtester")}>
            <BarChart3 size={16} style={{ marginRight: "6px", verticalAlign: "middle" }} /> Indicator Visualizer
          </button>
          <button className={`tab-btn ${activeTab === "scanner" ? "active" : ""}`} onClick={() => setActiveTab("scanner")}>
            <TrendingUp size={16} style={{ marginRight: "6px", verticalAlign: "middle" }} /> Dark Pool Scanner
          </button>
        </nav>

        {/* Status Indicators */}
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{
              width: "8px", 
              height: "8px", 
              borderRadius: "50%", 
              backgroundColor: backendStatus === "online" ? "#10b981" : backendStatus === "offline" ? "#ef4444" : "#f59e0b"
            }} />
            <span style={{ fontSize: "0.8rem", textTransform: "capitalize", color: "hsl(var(--text-muted))" }}>
              API: {backendStatus}
            </span>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main style={{ flex: 1, padding: "0 24px 32px 24px", maxWidth: "1400px", width: "100%", margin: "0 auto" }}>

        {/* VIEW 1: TICKER DASHBOARD */}
        {activeTab === "dashboard" && <TickerDashboard />}

        {/* VIEW 2: DARK POOL SCANNER */}
        {activeTab === "scanner" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
            
            {/* Scan Query Panel */}
            <div className="glass-panel" style={{ padding: "20px" }}>
              <form onSubmit={runScanner} style={{ display: "flex", flexWrap: "wrap", gap: "16px", alignItems: "flex-end" }}>
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
                  {scanLoading ? "Analyzing..." : "Analyze TRF Activity"}
                </button>
              </form>
            </div>

            {scanError && (
              <div className="glass-panel" style={{ padding: "16px", borderColor: "rgba(239, 68, 68, 0.4)", display: "flex", gap: "12px", alignItems: "center" }}>
                <AlertTriangle color="#ef4444" />
                <span style={{ fontSize: "0.9rem", color: "#f87171" }}>{scanError}</span>
              </div>
            )}

            {/* Results Grid */}
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
                  
                  {/* Recharts Pie Chart representing Lit vs Off-Exchange Volume */}
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
                                    onClick={() => sendDiscordAlert(`🚨 INSTITUTIONAL SPIKE DETECTED on ${scanSymbol}: Block trade of ${b.size.toLocaleString()} shares at $${b.price.toFixed(2)} ($${b.value.toLocaleString()} total value).`)}
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
        )}

        {/* VIEW 3: INDICATOR VISUALIZER */}
        {activeTab === "backtester" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
            
            <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "24px", alignItems: "stretch" }}>
              {/* Form configuration panel */}
              <div className="glass-panel" style={{ padding: "24px" }}>
                <h3 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "20px" }}>Configure Indicator Visualizer</h3>
                <form onSubmit={runBacktester} style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "20px", alignItems: "flex-end" }}>
                  
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <label style={{ fontSize: "0.8rem", color: "hsl(var(--text-muted))" }}>Asset Symbol</label>
                    <input 
                      type="text" 
                      className="input-field" 
                      value={btSymbols} 
                      onChange={(e) => setBtSymbols(e.target.value)} 
                      placeholder="AAPL"
                      required
                    />
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <label style={{ fontSize: "0.8rem", color: "hsl(var(--text-muted))" }}>Start Date</label>
                    <input 
                      type="date" 
                      className="input-field" 
                      value={btStartDate} 
                      onChange={(e) => setBtStartDate(e.target.value)}
                      required
                    />
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <label style={{ fontSize: "0.8rem", color: "hsl(var(--text-muted))" }}>End Date</label>
                    <input 
                      type="date" 
                      className="input-field" 
                      value={btEndDate} 
                      onChange={(e) => setBtEndDate(e.target.value)}
                      required
                    />
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <label style={{ fontSize: "0.8rem", color: "hsl(var(--text-muted))" }}>Analysis Indicator</label>
                    <select 
                      className="input-field" 
                      value={btStrategy} 
                      onChange={(e) => setBtStrategy(e.target.value)}
                      style={{ background: "#0a0f1d" }}
                    >
                      <option value="dark_pool_spike">Dark Pool Spikes & Ratio</option>
                      <option value="sma_cross">SMA Golden/Death Crossover</option>
                    </select>
                  </div>

                  {btStrategy === "dark_pool_spike" && (
                    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                      <label style={{ fontSize: "0.8rem", color: "hsl(var(--text-muted))" }}>Dark Ratio Threshold</label>
                      <input 
                        type="number" 
                        step="0.05"
                        min="0.1"
                        max="0.9"
                        className="input-field" 
                        value={btThreshold} 
                        onChange={(e) => setBtThreshold(Number(e.target.value))}
                      />
                    </div>
                  )}

                  <button type="submit" className="btn-primary" style={{ height: "40px", justifyContent: "center" }} disabled={btLoading}>
                    <Play size={16} /> {btLoading ? "Calculating..." : "Generate Visualizations"}
                  </button>
                </form>
              </div>

              {/* Discord Broadcaster panel */}
              <div className="glass-panel" style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "16px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <MessageSquare size={18} color="#a78bfa" />
                  <h3 style={{ fontSize: "1.1rem", fontWeight: 700 }}>Discord Broadcaster</h3>
                </div>
                <p style={{ fontSize: "0.85rem", color: "hsl(var(--text-muted))" }}>
                  Routinely push updates or custom indicators directly to your Discord community.
                </p>
                <textarea 
                  className="input-field" 
                  rows={4}
                  style={{ width: "100%", resize: "none", fontSize: "0.85rem" }}
                  placeholder="Type an alert message e.g. 'AAPL Block trade spike detected! 15K shares off-exchange.'"
                  value={discordMsg}
                  onChange={(e) => setDiscordMsg(e.target.value)}
                />
                <button 
                  className="btn-primary" 
                  onClick={() => sendDiscordAlert(discordMsg)}
                  disabled={discordSending || !discordMsg.trim()}
                  style={{ justifyContent: "center" }}
                >
                  <Send size={16} /> {discordSending ? "Broadcasting..." : "Publish Indicator"}
                </button>
                {discordSentMessage && (
                  <span style={{ fontSize: "0.8rem", marginTop: "4px", color: discordSentMessage.includes("✅") ? "#34d399" : "#f87171" }}>
                    {discordSentMessage}
                  </span>
                )}
              </div>
            </div>

            {btError && (
              <div className="glass-panel" style={{ padding: "16px", borderColor: "rgba(239, 68, 68, 0.4)", display: "flex", gap: "12px", alignItems: "center" }}>
                <AlertTriangle color="#ef4444" />
                <span style={{ fontSize: "0.9rem", color: "#f87171" }}>{btError}</span>
              </div>
            )}

            {/* Analysis Results Dashboard */}
            {btResults && (
              <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
                
                {/* Mode description alert */}
                <div className="glass-panel" style={{ padding: "12px 20px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: "0.85rem", color: "hsl(var(--text-muted))" }}>
                    Indicator Data Source: <strong style={{ color: "#a78bfa" }}>{btResults.data_source}</strong>
                  </span>
                  <span className="badge badge-success">Ingestion Complete</span>
                </div>

                {/* Indicator KPIs */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "20px" }}>
                  <div className="glass-panel" style={{ padding: "20px" }}>
                    <span style={{ fontSize: "0.8rem", color: "hsl(var(--text-muted))" }}>Average Price</span>
                    <h3 style={{ fontSize: "1.8rem", fontWeight: 700, fontFamily: "var(--font-display)", marginTop: "4px" }}>
                      ${btResults.metrics.avg_price.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                    </h3>
                  </div>
                  <div className="glass-panel" style={{ padding: "20px" }}>
                    <span style={{ fontSize: "0.8rem", color: "hsl(var(--text-muted))" }}>
                      {btStrategy === "dark_pool_spike" ? "Max Dark Pool Ratio" : "Max Fast SMA"}
                    </span>
                    <h3 style={{ 
                      fontSize: "1.8rem", 
                      fontWeight: 700, 
                      fontFamily: "var(--font-display)", 
                      marginTop: "4px",
                      color: "#a78bfa"
                    }}>
                      {btStrategy === "dark_pool_spike" 
                        ? `${(btResults.metrics.max_indicator * 100).toFixed(2)}%`
                        : `$${btResults.metrics.max_indicator.toLocaleString("en-US", { minimumFractionDigits: 2 })}`
                      }
                    </h3>
                  </div>
                  <div className="glass-panel" style={{ padding: "20px" }}>
                    <span style={{ fontSize: "0.8rem", color: "hsl(var(--text-muted))" }}>Triggered Alerts</span>
                    <h3 style={{ fontSize: "1.8rem", fontWeight: 700, color: "#10b981", fontFamily: "var(--font-display)", marginTop: "4px" }}>
                      {btResults.metrics.total_signals}
                    </h3>
                  </div>
                  <div className="glass-panel" style={{ padding: "20px" }}>
                    <span style={{ fontSize: "0.8rem", color: "hsl(var(--text-muted))" }}>Active Analysis</span>
                    <h3 style={{ fontSize: "1.8rem", fontWeight: 700, fontFamily: "var(--font-display)", marginTop: "4px" }}>
                      {btStrategy === "dark_pool_spike" ? "Dark Ratio" : "SMA Cross"}
                    </h3>
                  </div>
                </div>

                {/* Price and Indicator Curves Chart */}
                <div className="glass-panel" style={{ padding: "24px", minHeight: "380px" }}>
                  <h4 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "16px" }}>Price & Indicator Visualization</h4>
                  <div style={{ width: "100%", height: 320 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={btResults.series}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
                        <XAxis 
                          dataKey="timestamp" 
                          tickFormatter={(str) => {
                            try { return str.split("T")[0]; } catch(e) { return str; }
                          }}
                          stroke="hsl(var(--text-muted))"
                          fontSize={11}
                        />
                        
                        {/* Dual Y-Axes Setup */}
                        <YAxis yAxisId="left" stroke="#3b82f6" fontSize={11} domain={['auto', 'auto']} label={{ value: 'Stock Price ($)', angle: -90, position: 'insideLeft', fill: '#3b82f6', style: {fontSize: 10} }} />
                        {btStrategy === "dark_pool_spike" ? (
                          <YAxis yAxisId="right" orientation="right" stroke="#8b5cf6" fontSize={11} domain={[0, 1]} tickFormatter={(val) => `${(val*100).toFixed(0)}%`} label={{ value: 'Dark Pool Ratio', angle: 90, position: 'insideRight', fill: '#8b5cf6', style: {fontSize: 10} }} />
                        ) : (
                          <YAxis yAxisId="right" orientation="right" stroke="#10b981" fontSize={11} domain={['auto', 'auto']} label={{ value: 'SMA Value ($)', angle: 90, position: 'insideRight', fill: '#10b981', style: {fontSize: 10} }} />
                        )}
                        
                        <Tooltip 
                          contentStyle={{ backgroundColor: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "8px" }}
                          labelFormatter={(str) => {
                            try { return str.split("T")[0]; } catch(e) { return str; }
                          }}
                          formatter={(value: any, name: any) => {
                            if (name === "price") return [`$${value.toFixed(2)}`, "Stock Price"];
                            if (name === "indicator_1") {
                              return btStrategy === "dark_pool_spike" 
                                ? [`${(value * 100).toFixed(2)}%`, "Dark Ratio"] 
                                : [`$${value.toFixed(2)}`, "Fast SMA"];
                            }
                            if (name === "indicator_2") {
                              return btStrategy === "dark_pool_spike" 
                                ? [`${(value * 100).toFixed(2)}%`, "Threshold"] 
                                : [`$${value.toFixed(2)}`, "Slow SMA"];
                            }
                            return [value, name];
                          }}
                        />
                        
                        <Legend wrapperStyle={{ fontSize: 12, marginTop: 10 }} />
                        
                        {/* Lines for Stock Price */}
                        <Line yAxisId="left" type="monotone" dataKey="price" name="price" stroke="#3b82f6" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
                        
                        {/* Lines for Indicators */}
                        {btStrategy === "dark_pool_spike" ? (
                          <>
                            <Line yAxisId="right" type="monotone" dataKey="indicator_1" name="indicator_1" stroke="#8b5cf6" strokeWidth={2} dot={false} />
                            <ReferenceLine yAxisId="right" y={btThreshold} stroke="#ef4444" strokeDasharray="3 3" label={{ value: 'Threshold', fill: '#ef4444', fontSize: 10 }} />
                          </>
                        ) : (
                          <>
                            <Line yAxisId="left" type="monotone" dataKey="indicator_1" name="indicator_1" stroke="#10b981" strokeWidth={1.5} dot={false} />
                            <Line yAxisId="left" type="monotone" dataKey="indicator_2" name="indicator_2" stroke="#f59e0b" strokeWidth={1.5} dot={false} />
                          </>
                        )}
                        
                        {/* Vertical Signal Lines */}
                        {btResults.signals.map((sig: any, idx: number) => (
                          <ReferenceLine 
                            key={idx}
                            yAxisId="left"
                            x={sig.timestamp} 
                            stroke={sig.type === "BUY" || sig.type === "SPIKE" ? "rgba(16, 185, 129, 0.4)" : "rgba(239, 68, 68, 0.4)"} 
                            strokeDasharray="4 4"
                          />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Signals Table */}
                <div className="glass-panel" style={{ padding: "24px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                    <h4 style={{ fontSize: "1rem", fontWeight: 700 }}>Triggered Indicator Signals</h4>
                    <span className="badge badge-darkpool">Total: {btResults.signals.length} alerts</span>
                  </div>
                  {btResults.signals.length === 0 ? (
                    <p style={{ fontSize: "0.85rem", color: "hsl(var(--text-muted))" }}>No indicators crossed the thresholds in this period.</p>
                  ) : (
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem", textAlign: "left" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid hsl(var(--border-color))", color: "hsl(var(--text-muted))" }}>
                          <th style={{ padding: "10px" }}>Date</th>
                          <th style={{ padding: "10px" }}>Signal</th>
                          <th style={{ padding: "10px" }}>Asset Price</th>
                          <th style={{ padding: "10px" }}>Details</th>
                          <th style={{ padding: "10px" }}>Broadcaster Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {btResults.signals.map((sig: any, idx: number) => (
                          <tr key={idx} style={{ borderBottom: "1px solid rgba(255,255,255,0.02)" }}>
                            <td style={{ padding: "12px 10px" }}>
                              {sig.timestamp.split("T")[0]} {sig.timestamp.split("T")[1]?.substring(0, 5)}
                            </td>
                            <td style={{ padding: "12px 10px" }}>
                              <span className={`badge ${sig.type === "BUY" || sig.type === "SPIKE" ? "badge-success" : "badge-danger"}`}>
                                {sig.type}
                              </span>
                            </td>
                            <td style={{ padding: "12px 10px", fontWeight: 600 }}>${sig.price.toFixed(2)}</td>
                            <td style={{ padding: "12px 10px" }}>{sig.description}</td>
                            <td style={{ padding: "12px 10px" }}>
                              <button 
                                className="badge"
                                style={{ background: "rgba(167, 139, 250, 0.2)", border: "1px solid #a78bfa", color: "#c084fc", cursor: "pointer", padding: "4px 8px", borderRadius: "4px" }}
                                onClick={() => {
                                  setDiscordMsg(`🚨 ALERT [${btResults.symbol}]: ${sig.description}`);
                                  // Scroll to the Broadcaster panel
                                  window.scrollTo({ top: 0, behavior: 'smooth' });
                                }}
                              >
                                Send to Broadcaster
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>

              </div>
            )}

          </div>
        )}

      </main>

      {/* Footer */}
      <footer style={{ padding: "24px", textAlign: "center", borderTop: "1px solid var(--glass-border)", color: "hsl(var(--text-muted))", fontSize: "0.8rem" }}>
        DarkPoolData Platform • Powered by Massive.com API & Python Core Engine • Localhost Environment
      </footer>
    </div>
  );
}
