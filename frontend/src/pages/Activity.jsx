import { useEffect, useState } from "react";
import { authFetch } from "../api";

const ACTION_STYLES = {
  CREATE: { bg: "var(--green-bg)", color: "var(--green)", label: "Created" },
  UPDATE: { bg: "var(--blue-bg)", color: "var(--blue)", label: "Updated" },
  DELETE: { bg: "var(--red-bg)", color: "var(--red)", label: "Deleted" },
  ARCHIVE: { bg: "var(--yellow-bg)", color: "var(--yellow)", label: "Archived" },
  STOCK_IN: { bg: "var(--green-bg)", color: "var(--green)", label: "Stock In" },
  STOCK_OUT: { bg: "var(--red-bg)", color: "var(--red)", label: "Stock Out" },
  STOCK_ADJUST: { bg: "var(--yellow-bg)", color: "var(--yellow)", label: "Adjusted" },
};

export default function Activity() {
  const [log, setLog] = useState([]);
  const [stats, setStats] = useState(null);
  const [actionFilter, setActionFilter] = useState("");

  const fetchData = () => {
    const params = new URLSearchParams({ limit: "200" });
    if (actionFilter) params.set("action_type", actionFilter);
    authFetch(`/movements?${params}`).then(r => r.json()).then(d => setLog(d.data)).catch(() => {});
    authFetch(`/stats`).then(r => r.json()).then(setStats).catch(() => {});
  };

  useEffect(() => { fetchData(); }, [actionFilter]);

  const actionTypes = [...new Set(log.map(l => l.action_type))];

  return (
    <section>
      <div className="page-header">
        <div>
          <h1 className="page-title">Activity Log</h1>
          <p className="page-subtitle">Track all inventory changes</p>
        </div>
      </div>

      {stats && (
        <div className="grid-auto" style={{ marginBottom: 24 }}>
          <div className="card stat-card" style={{ borderTopColor: "var(--blue)", padding: "16px 20px" }}>
            <div className="stat-label">Total Products</div>
            <div className="stat-value" style={{ fontSize: "1.5rem" }}>{stats.total_products}</div>
          </div>
          <div className="card stat-card" style={{ borderTopColor: "var(--green)", padding: "16px 20px" }}>
            <div className="stat-label">Total Stock</div>
            <div className="stat-value" style={{ fontSize: "1.5rem" }}>{stats.total_stock}</div>
          </div>
          <div className="card stat-card" style={{ borderTopColor: stats.low_stock_count > 0 ? "var(--red)" : "var(--green)", padding: "16px 20px" }}>
            <div className="stat-label">Low Stock Items</div>
            <div className="stat-value" style={{ fontSize: "1.5rem", color: stats.low_stock_count > 0 ? "var(--red)" : "inherit" }}>{stats.low_stock_count}</div>
          </div>
          <div className="card stat-card" style={{ borderTopColor: "var(--yellow)", padding: "16px 20px" }}>
            <div className="stat-label">Activity (7 days)</div>
            <div className="stat-value" style={{ fontSize: "1.5rem" }}>{stats.recent_activity}</div>
          </div>
        </div>
      )}

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-body" style={{ paddingBottom: 12 }}>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <span className="muted" style={{ fontSize: "0.8125rem" }}>Filter:</span>
            <select className="select" value={actionFilter} onChange={e => setActionFilter(e.target.value)} style={{ width: "auto", minWidth: 160 }}>
              <option value="">All actions</option>
              {actionTypes.map(a => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
            <span className="muted" style={{ marginLeft: "auto" }}>{log.length} record{log.length !== 1 ? "s" : ""}</span>
          </div>
        </div>
      </div>

      <div className="table-container">
        {log.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-text">No activity recorded yet</div>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th style={{ width: 160 }}>Timestamp</th>
                <th>Product</th>
                <th>Action</th>
                <th style={{ textAlign: "right" }}>Delta</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {log.map(l => {
                const style = ACTION_STYLES[l.action_type] || ACTION_STYLES.STOCK_ADJUST;
                return (
                  <tr key={l.id}>
                    <td style={{ fontSize: "0.8125rem", color: "var(--muted)", whiteSpace: "nowrap" }}>
                      {l.created_at ? new Date(l.created_at + "Z").toLocaleString() : "-"}
                    </td>
                    <td>
                      <div style={{ fontWeight: 600 }}>{l.name}</div>
                      <div className="muted" style={{ fontSize: "0.75rem" }}>{l.sku}</div>
                    </td>
                    <td>
                      <span className="badge" style={{ background: style.bg, color: style.color }}>
                        {style.label}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      {l.delta !== 0 ? (
                        <span style={{ fontWeight: 700, color: l.delta > 0 ? "var(--green)" : "var(--red)" }}>
                          {l.delta > 0 ? "+" : ""}{l.delta}
                        </span>
                      ) : (
                        <span className="muted">-</span>
                      )}
                    </td>
                    <td style={{ color: "var(--text-secondary)", fontSize: "0.8125rem" }}>
                      {l.reason || "-"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
