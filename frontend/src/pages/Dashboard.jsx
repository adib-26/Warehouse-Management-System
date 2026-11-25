import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { authFetch } from "../api";
import LedgerList from "../components/LedgerList";
import { formatQuantity } from "../format";
import PageHeader from "../components/PageHeader";

const PLACEHOLDER = "—";

/** Fill ratio of on-hand against the low-stock level, clamped to 0–100. */
function fillPercent(quantity, threshold) {
  const amount = Number(quantity);
  const limit = Number(threshold);
  if (!Number.isFinite(amount) || amount <= 0) return 0;
  if (!Number.isFinite(limit) || limit <= 0) return 100;
  return Math.min(100, Math.max(0, (amount / limit) * 100));
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [lowStock, setLowStock] = useState([]);
  const [recentActivity, setRecentActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [statsRes, lowRes, histRes] = await Promise.all([
          authFetch(`/stats`),
          authFetch(`/products?low_stock=true`),
          authFetch(`/movements?limit=10`),
        ]);
        if (!statsRes.ok || !lowRes.ok || !histRes.ok) throw new Error("Request failed");
        const [statsData, lowData, histData] = await Promise.all([
          statsRes.json(),
          lowRes.json(),
          histRes.json(),
        ]);
        if (!active) return;
        setStats(statsData);
        setLowStock(lowData.data);
        setRecentActivity(histData.data);
        setError(null);
      } catch {
        if (active) setError("Could not load dashboard data. Check the API connection and reload.");
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => { active = false; };
  }, []);

  const lowCount = stats?.low_stock_count ?? 0;
  const asOf = new Date().toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  // Values render as dashes until the figures arrive, so the cards keep their
  // height instead of appearing and shifting the page.
  const cards = [
    { label: "Total Products", value: stats?.total_products, accent: "var(--blue)" },
    { label: "Total Stock Units", value: stats?.total_stock, accent: "var(--green)" },
    { label: "Low Stock Items", value: stats?.low_stock_count, accent: lowCount > 0 ? "var(--red)" : "var(--green)", alarm: lowCount > 0 },
    { label: "Activity (7 days)", value: stats?.recent_activity, accent: "var(--yellow)" },
  ];

  return (
    <section aria-busy={loading}>
      <PageHeader
        eyebrow="Overview"
        title="Dashboard"
        subtitle={`Stock position as of ${asOf}`}
      />

      {error && (
        <div className="alert alert-error" role="alert" style={{ marginBottom: 20 }}>
          <span>{error}</span>
          <button className="btn btn-ghost btn-xs" onClick={() => window.location.reload()}>Reload</button>
        </div>
      )}

      <div className="grid-auto" style={{ marginBottom: 24 }}>
        {cards.map(card => (
          <div className="card stat-card" key={card.label} style={{ borderTopColor: card.accent }}>
            <div className="stat-label">{card.label}</div>
            <div className="stat-value" style={card.alarm ? { color: "var(--red)" } : undefined}>
              {card.value === undefined || card.value === null ? PLACEHOLDER : formatQuantity(card.value)}
            </div>
            {card.label === "Low Stock Items" && lowCount > 0 && (
              <button
                className="btn btn-danger btn-xs"
                style={{ marginTop: 8 }}
                onClick={() => navigate("/products?low_stock=true")}
              >
                View items
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-body">
            <h2 className="section-title">Low Stock Alerts</h2>
            {lowStock.length === 0 ? (
              <div className="empty-state" style={{ padding: 24 }}>
                <div className="empty-state-text">
                  {loading ? "Checking stock levels..." : "Every product is above its minimum"}
                </div>
              </div>
            ) : (
              <div style={{ display: "grid", gap: 10 }}>
                <ul className="ledger-list">
                  {lowStock.slice(0, 5).map(p => (
                    <li className="ledger-row ledger-row--alert ledger-row--stacked" key={p.id}>
                      <span className="ledger-row__id">
                        <span className="ledger-row__name">{p.name}</span>
                        <span className="muted ledger-row__sku">{p.sku}</span>
                      </span>
                      <span className="ledger-num ledger-num--down">
                        {formatQuantity(p.quantity)} / {formatQuantity(p.low_stock)}
                      </span>
                      {/* Decorative: the same figures are already given as text. */}
                      <div className="meter" aria-hidden="true">
                        <div className="meter__fill" style={{ width: `${fillPercent(p.quantity, p.low_stock)}%` }} />
                      </div>
                    </li>
                  ))}
                </ul>
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
            <h2 className="section-title">Recent Activity</h2>
            <LedgerList
              items={recentActivity}
              emptyText={loading ? "Loading movements..." : "No recent activity"}
            />
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
