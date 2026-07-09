import { useEffect, useState } from "react";

const API = "http://localhost:8000";

const ACTION_COLORS = {
  CREATE: { bg: "rgba(52, 211, 153, 0.15)", color: "#34d399" },
  UPDATE: { bg: "rgba(96, 165, 250, 0.15)", color: "#60a5fa" },
  DELETE: { bg: "rgba(239, 68, 68, 0.15)", color: "#ef4444" },
  ARCHIVE: { bg: "rgba(251, 191, 36, 0.15)", color: "#fbbf24" },
  STOCK_IN: { bg: "rgba(52, 211, 153, 0.15)", color: "#34d399" },
  STOCK_OUT: { bg: "rgba(239, 68, 68, 0.15)", color: "#ef4444" },
  STOCK_ADJUST: { bg: "rgba(251, 191, 36, 0.15)", color: "#fbbf24" },
};

export default function Activity() {
  const [log, setLog] = useState([]);
  const [stats, setStats] = useState(null);
  const [actionFilter, setActionFilter] = useState("");

  const fetchData = () => {
    const params = new URLSearchParams({ limit: "200" });
    if (actionFilter) params.set("action_type", actionFilter);
    fetch(`${API}/history?${params}`).then((r) => r.json()).then(setLog).catch(() => {});
    fetch(`${API}/history/stats`).then((r) => r.json()).then(setStats).catch(() => {});
  };

  useEffect(() => { fetchData(); }, [actionFilter]);

  const actionTypes = [...new Set(log.map((l) => l.action_type))];

  return (
    <section>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "1.5rem" }}>Activity Log</h1>
          <p className="muted" style={{ margin: "4px 0 0 0" }}>Track all inventory changes</p>
        </div>
      </div>

      {stats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 16 }}>
          <div className="card" style={{ padding: 14 }}>
            <div className="muted" style={{ fontSize: "0.8rem" }}>Total Products</div>
            <div style={{ fontSize: "1.5rem", fontWeight: 700 }}>{stats.total_products}</div>
          </div>
          <div className="card" style={{ padding: 14 }}>
            <div className="muted" style={{ fontSize: "0.8rem" }}>Total Stock</div>
            <div style={{ fontSize: "1.5rem", fontWeight: 700 }}>{stats.total_stock}</div>
          </div>
          <div className="card" style={{ padding: 14 }}>
            <div className="muted" style={{ fontSize: "0.8rem" }}>Low Stock Items</div>
            <div style={{ fontSize: "1.5rem", fontWeight: 700, color: stats.low_stock_count > 0 ? "#ef4444" : "inherit" }}>{stats.low_stock_count}</div>
          </div>
          <div className="card" style={{ padding: 14 }}>
            <div className="muted" style={{ fontSize: "0.8rem" }}>Activity (7 days)</div>
            <div style={{ fontSize: "1.5rem", fontWeight: 700 }}>{stats.recent_activity}</div>
          </div>
        </div>
      )}

      <div className="card" style={{ padding: 12, marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span className="muted" style={{ fontSize: "0.85rem" }}>Filter by action:</span>
          <select className="select" value={actionFilter} onChange={(e) => setActionFilter(e.target.value)} style={{ width: "auto", minWidth: 140 }}>
            <option value="">All actions</option>
            {actionTypes.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: "auto" }}>
        {log.length === 0 ? (
          <div style={{ padding: 32, textAlign: "center" }}>
            <p className="muted">No activity recorded yet</p>
          </div>
        ) : (
          <div style={{ minWidth: 600 }}>
            {log.map((l, i) => {
              const colors = ACTION_COLORS[l.action_type] || ACTION_COLORS.STOCK_ADJUST;
              return (
                <div key={l.id || i} style={{
                  display: "grid",
                  gridTemplateColumns: "120px 1fr auto",
                  gap: 12,
                  padding: "12px 16px",
                  borderBottom: i < log.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none",
                  alignItems: "center",
                  fontSize: "0.9rem",
                }}>
                  <div className="muted" style={{ fontSize: "0.8rem", whiteSpace: "nowrap" }}>
                    {l.created_at ? new Date(l.created_at + "Z").toLocaleString() : "-"}
                  </div>
                  <div>
                    <strong>{l.name}</strong>
                    <span className="muted" style={{ marginLeft: 8, fontSize: "0.8rem" }}>{l.sku}</span>
                    {l.reason && (
                      <span className="muted" style={{ marginLeft: 8, fontSize: "0.8rem" }}>
                        — {l.reason}
                      </span>
                    )}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    {l.delta !== 0 && (
                      <span style={{ fontWeight: 700, color: l.delta > 0 ? "#34d399" : "#ef4444" }}>
                        {l.delta > 0 ? "+" : ""}{l.delta}
                      </span>
                    )}
                    <span className="badge" style={{ background: colors.bg, color: colors.color }}>
                      {l.action_type}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
