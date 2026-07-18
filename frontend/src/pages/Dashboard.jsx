import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { authFetch } from "../api";

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [lowStock, setLowStock] = useState([]);
  const [recentActivity, setRecentActivity] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    const load = async () => {
      try {
        const [statsRes, lowRes, histRes] = await Promise.all([
          authFetch(`/stats`),
          authFetch(`/products?low_stock=true`),
          authFetch(`/movements?limit=10`),
        ]);
        setStats(await statsRes.json());
        setLowStock((await lowRes.json()).data);
        setRecentActivity((await histRes.json()).data);
      } catch {
        console.error("Failed to load dashboard data");
      }
    };
    load();
  }, []);

  return (
    <section>
      <div className="page-header">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-subtitle">Overview of your warehouse inventory</p>
        </div>
      </div>

      {stats && (
        <div className="grid-auto" style={{ marginBottom: 24 }}>
          <div className="card stat-card" style={{ borderTopColor: "var(--blue)" }}>
            <div className="stat-label">Total Products</div>
            <div className="stat-value">{stats.total_products}</div>
          </div>
          <div className="card stat-card" style={{ borderTopColor: "var(--green)" }}>
            <div className="stat-label">Total Stock Units</div>
            <div className="stat-value">{stats.total_stock}</div>
          </div>
          <div className="card stat-card" style={{ borderTopColor: stats.low_stock_count > 0 ? "var(--red)" : "var(--green)" }}>
            <div className="stat-label">Low Stock Items</div>
            <div className="stat-value" style={{ color: stats.low_stock_count > 0 ? "var(--red)" : "inherit" }}>
              {stats.low_stock_count}
            </div>
            {stats.low_stock_count > 0 && (
              <button className="btn btn-danger btn-xs" style={{ marginTop: 8 }} onClick={() => navigate("/products?low_stock=true")}>
                View items
              </button>
            )}
          </div>
          <div className="card stat-card" style={{ borderTopColor: "var(--yellow)" }}>
            <div className="stat-label">Activity (7 days)</div>
            <div className="stat-value">{stats.recent_activity}</div>
          </div>
        </div>
      )}

      <div className="grid-2">
        <div className="card">
          <div className="card-body">
            <h3 className="section-title">Low Stock Alerts</h3>
            {lowStock.length === 0 ? (
              <div className="empty-state" style={{ padding: 24 }}>
                <div className="empty-state-text">All products are adequately stocked</div>
              </div>
            ) : (
              <div style={{ display: "grid", gap: 8 }}>
                {lowStock.slice(0, 5).map(p => (
                  <div key={p.id} style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "12px 14px",
                    borderRadius: "var(--radius-sm)",
                    background: "var(--red-bg)",
                    border: "1px solid rgba(239, 68, 68, 0.15)",
                  }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "0.875rem" }}>{p.name}</div>
                      <div className="muted" style={{ fontSize: "0.75rem" }}>{p.sku}</div>
                    </div>
                    <div style={{ fontWeight: 700, color: "var(--red)", fontSize: "0.9375rem" }}>
                      {p.quantity} / {p.low_stock}
                    </div>
                  </div>
                ))}
                {lowStock.length > 5 && (
                  <button className="btn btn-ghost btn-xs" onClick={() => navigate("/products?low_stock=true")}>
                    View all {lowStock.length} low stock items
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-body">
            <h3 className="section-title">Recent Activity</h3>
            {recentActivity.length === 0 ? (
              <div className="empty-state" style={{ padding: 24 }}>
                <div className="empty-state-text">No recent activity</div>
              </div>
            ) : (
              <div style={{ display: "grid", gap: 6 }}>
                {recentActivity.map((a, i) => (
                  <div key={i} style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "10px 14px",
                    borderRadius: "var(--radius-sm)",
                    background: "var(--bg-surface-elevated)",
                    fontSize: "0.875rem",
                  }}>
                    <div>
                      <span style={{ fontWeight: 600 }}>{a.name}</span>
                      <span className="muted" style={{ marginLeft: 8, fontSize: "0.8rem" }}>{a.action_type}</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      {a.delta !== 0 && (
                        <span style={{ fontWeight: 700, color: a.delta > 0 ? "var(--green)" : "var(--red)", fontSize: "0.8125rem" }}>
                          {a.delta > 0 ? "+" : ""}{a.delta}
                        </span>
                      )}
                      <span className="muted" style={{ fontSize: "0.75rem", whiteSpace: "nowrap" }}>
                        {a.created_at ? new Date(a.created_at + "Z").toLocaleDateString() : ""}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <button
              className="btn btn-ghost btn-xs"
              style={{ marginTop: 12 }}
              onClick={() => navigate("/activity")}
            >
              View full activity log
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
