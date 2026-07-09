import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

const API = "http://localhost:8000";

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [lowStock, setLowStock] = useState([]);
  const [recentActivity, setRecentActivity] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    const load = async () => {
      try {
        const [statsRes, lowRes, histRes] = await Promise.all([
          fetch(`${API}/history/stats`),
          fetch(`${API}/products/low-stock`),
          fetch(`${API}/history?limit=10`),
        ]);
        setStats(await statsRes.json());
        setLowStock(await lowRes.json());
        setRecentActivity(await histRes.json());
      } catch {
        console.error("Failed to load dashboard data");
      }
    };
    load();
  }, []);

  return (
    <section>
      <header style={{ marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: "1.5rem" }}>Dashboard Overview</h1>
        <p className="muted" style={{ margin: "4px 0 0 0" }}>Snapshot of your inventory</p>
      </header>

      {stats && (
        <div style={{ display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", marginBottom: 20 }}>
          <div className="card" style={{ padding: 18, borderTop: "3px solid #60a5fa" }}>
            <div className="muted" style={{ fontSize: "0.85rem" }}>Total Products</div>
            <div style={{ fontSize: "1.8rem", fontWeight: 700, marginTop: 4 }}>{stats.total_products}</div>
          </div>
          <div className="card" style={{ padding: 18, borderTop: "3px solid #34d399" }}>
            <div className="muted" style={{ fontSize: "0.85rem" }}>Total Stock</div>
            <div style={{ fontSize: "1.8rem", fontWeight: 700, marginTop: 4 }}>{stats.total_stock}</div>
          </div>
          <div className="card" style={{ padding: 18, borderTop: `3px solid ${stats.low_stock_count > 0 ? "#ef4444" : "#34d399"}` }}>
            <div className="muted" style={{ fontSize: "0.85rem" }}>Low Stock Items</div>
            <div style={{
              fontSize: "1.8rem",
              fontWeight: 700,
              marginTop: 4,
              color: stats.low_stock_count > 0 ? "#ef4444" : "inherit",
            }}>
              {stats.low_stock_count}
            </div>
            {stats.low_stock_count > 0 && (
              <button
                className="btn btn-sm"
                style={{ marginTop: 8, fontSize: "0.8rem" }}
                onClick={() => navigate("/products?low_stock=true")}
              >
                View items
              </button>
            )}
          </div>
          <div className="card" style={{ padding: 18, borderTop: "3px solid #fbbf24" }}>
            <div className="muted" style={{ fontSize: "0.85rem" }}>Activity (7 days)</div>
            <div style={{ fontSize: "1.8rem", fontWeight: 700, marginTop: 4 }}>{stats.recent_activity}</div>
          </div>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div>
          <div className="card" style={{ padding: 16 }}>
            <h2 style={{ margin: "0 0 12px 0", fontSize: "1rem" }}>Low Stock Alerts</h2>
            {lowStock.length === 0 ? (
              <p className="muted">All products are adequately stocked</p>
            ) : (
              <div style={{ display: "grid", gap: 6 }}>
                {lowStock.slice(0, 5).map((p) => (
                  <div key={p.id} style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "8px 10px",
                    borderRadius: 8,
                    background: "rgba(239, 68, 68, 0.08)",
                    fontSize: "0.9rem",
                  }}>
                    <div>
                      <strong>{p.name}</strong>
                      <span className="muted" style={{ marginLeft: 6, fontSize: "0.8rem" }}>{p.sku}</span>
                    </div>
                    <div style={{ fontWeight: 700, color: "#ef4444" }}>
                      {p.quantity} / {p.low_stock}
                    </div>
                  </div>
                ))}
                {lowStock.length > 5 && (
                  <button className="btn btn-sm btn-ghost" onClick={() => navigate("/products?low_stock=true")}>
                    View all {lowStock.length} low stock items
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        <div>
          <div className="card" style={{ padding: 16 }}>
            <h2 style={{ margin: "0 0 12px 0", fontSize: "1rem" }}>Recent Activity</h2>
            {recentActivity.length === 0 ? (
              <p className="muted">No recent activity</p>
            ) : (
              <div style={{ display: "grid", gap: 6 }}>
                {recentActivity.map((a, i) => (
                  <div key={i} style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "6px 10px",
                    borderRadius: 8,
                    background: "color-mix(in srgb, var(--text-dark) 3%, transparent)",
                    fontSize: "0.85rem",
                  }}>
                    <div>
                      <strong>{a.name}</strong>
                      <span className="muted" style={{ marginLeft: 6 }}>{a.action_type}</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      {a.delta !== 0 && (
                        <span style={{ fontWeight: 600, color: a.delta > 0 ? "#34d399" : "#ef4444" }}>
                          {a.delta > 0 ? "+" : ""}{a.delta}
                        </span>
                      )}
                      <span className="muted" style={{ fontSize: "0.75rem" }}>
                        {a.created_at ? new Date(a.created_at + "Z").toLocaleDateString() : ""}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <button
              className="btn btn-sm btn-ghost"
              style={{ marginTop: 8 }}
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
