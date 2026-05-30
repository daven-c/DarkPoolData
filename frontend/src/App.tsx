import { useState, useEffect } from "react";
import {
  TrendingUp,
  Activity,
  LayoutGrid,
  Bell,
  FlaskConical,
} from "lucide-react";
import SignalsDashboard from "./SignalsDashboard";
import StockExplorer from "./StockExplorer";
import AlertsFeed from "./AlertsFeed";
import StrategyLab from "./StrategyLab";

export default function App() {
  const [activeTab, setActiveTab] = useState<"dashboard" | "alerts" | "strategy" | "scanner">("dashboard");
  const [backendStatus, setBackendStatus] = useState<"connecting" | "online" | "offline">("connecting");

  // Check backend health on mount
  useEffect(() => {
    fetch("http://localhost:8000/")
      .then((res) => res.json())
      .then((data) => setBackendStatus(data.status === "online" ? "online" : "offline"))
      .catch(() => setBackendStatus("offline"));
  }, []);

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
        <nav style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
          <button className={`tab-btn ${activeTab === "dashboard" ? "active" : ""}`} onClick={() => setActiveTab("dashboard")}>
            <LayoutGrid size={15} style={{ marginRight: "5px", verticalAlign: "middle" }} /> Dashboard
          </button>
          <button className={`tab-btn ${activeTab === "alerts" ? "active" : ""}`} onClick={() => setActiveTab("alerts")}>
            <Bell size={15} style={{ marginRight: "5px", verticalAlign: "middle" }} /> Alerts
          </button>
          <button className={`tab-btn ${activeTab === "strategy" ? "active" : ""}`} onClick={() => setActiveTab("strategy")}>
            <FlaskConical size={15} style={{ marginRight: "5px", verticalAlign: "middle" }} /> Strategy Lab
          </button>
          <button className={`tab-btn ${activeTab === "scanner" ? "active" : ""}`} onClick={() => setActiveTab("scanner")}>
            <TrendingUp size={15} style={{ marginRight: "5px", verticalAlign: "middle" }} /> Stock Explorer
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
        {/* VIEW 1: SIGNALS DASHBOARD */}
        {activeTab === "dashboard" && <SignalsDashboard />}

        {/* VIEW 2: ALERTS FEED */}
        {activeTab === "alerts" && <AlertsFeed />}

        {/* VIEW 3: STRATEGY LAB (authoring + backtest) */}
        {activeTab === "strategy" && <StrategyLab />}

        {/* VIEW 4: STOCK EXPLORER */}
        {activeTab === "scanner" && <StockExplorer />}
      </main>

      {/* Footer */}
      <footer style={{ padding: "24px", textAlign: "center", borderTop: "1px solid var(--glass-border)", color: "hsl(var(--text-muted))", fontSize: "0.8rem" }}>
        DarkPoolData Platform • Powered by Massive.com API & Python Core Engine • Localhost Environment
      </footer>
    </div>
  );
}
