import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { authFetch } from "../api";
import { actionLabel, formatDelta, formatQuantity, formatShortDateTime, parseApiDate } from "../format";
import PageHeader from "../components/PageHeader";

const PLACEHOLDER = "—";
const LOW_STOCK_PREVIEW = 5;

/** Fill ratio of on-hand against the low-stock level, clamped to 0–100. */
function fillPercent(quantity, threshold) {
  const amount = Number(quantity);
  const limit = Number(threshold);
  if (!Number.isFinite(amount) || amount <= 0) return 0;
  if (!Number.isFinite(limit) || limit <= 0) return 100;
  return Math.min(100, Math.max(0, (amount / limit) * 100));
}

/** Figures render as dashes until they arrive, so the band keeps its height. */
function figure(value) {
  return value === undefined || value === null ? PLACEHOLDER : formatQuantity(value);
}

function ArrowIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

/**
 * One band of four figures divided by rules. The low-stock cell turns red and
 * offers a review link while anything is at or below its minimum.
 */
function SummaryBand({ stats }) {
  const short = Number(stats?.low_stock_count) > 0;
  return (
    <section className="summary-band" aria-label="Stock summary">
      <dl className="summary-band__grid">
        <div className="summary-cell">
          <dt className="summary-cell__label">Total products</dt>
          <dd className="summary-cell__value">{figure(stats?.total_products)}</dd>
        </div>
        <div className="summary-cell">
          <dt className="summary-cell__label">Stock units</dt>
          <dd className="summary-cell__value">{figure(stats?.total_stock)}</dd>
        </div>
        <div className={`summary-cell${short ? " summary-cell--alarm" : ""}`}>
          <dt className="summary-cell__label">Low stock items</dt>
          <dd className="summary-cell__value">{figure(stats?.low_stock_count)}</dd>
          {short && (
            <dd className="summary-cell__action">
              <Link className="summary-cell__link" to="/products?low_stock=true">
                Review items <ArrowIcon />
              </Link>
            </dd>
          )}
        </div>
        <div className="summary-cell">
          <dt className="summary-cell__label">Movements, 7 days</dt>
          <dd className="summary-cell__value">{figure(stats?.recent_activity)}</dd>
        </div>
      </dl>
    </section>
  );
}

function LowStockLedger({ items }) {
  return (
    <ul className="stock-ledger">
      {items.map(p => (
        <li className="stock-ledger__row" key={p.id}>
          <span className="stock-ledger__id">
            <span className="stock-ledger__name">{p.name}</span>
            <span className="stock-ledger__sku">{p.sku}</span>
          </span>
          <span className="stock-ledger__level">
            {/* Decorative: the same figures follow as text. */}
            <span className="meter" aria-hidden="true">
              <span className="meter__fill" style={{ width: `${fillPercent(p.quantity, p.low_stock)}%` }} />
            </span>
            <span className="stock-ledger__qty">
              {formatQuantity(p.quantity)}
              <span className="stock-ledger__min"> / {formatQuantity(p.low_stock)}</span>
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function ActivityTimeline({ items }) {
  return (
    <ol className="timeline">
      {items.map((item, index) => {
        const delta = Number(item.delta);
        const direction = delta > 0 ? "up" : delta < 0 ? "down" : "flat";
        const when = parseApiDate(item.created_at);
        return (
          <li className="timeline__item" key={item.id ?? index}>
            <span className="timeline__name">{item.name}</span>
            <span className={`timeline__delta ledger-num--${direction}`}>
              {delta === 0 || !Number.isFinite(delta) ? PLACEHOLDER : formatDelta(delta)}
            </span>
            <span className="timeline__meta">
              {actionLabel(item.action_type)}
              {item.sku && ` · ${item.sku}`}
              {when && (
                <>
                  {" · "}
                  <time dateTime={when.toISOString()}>{formatShortDateTime(when)}</time>
                </>
              )}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function EmptyPanel({ children }) {
  return (
    <div className="empty-state">
      <div className="empty-state-text">{children}</div>
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [lowStock, setLowStock] = useState({ items: [], total: 0 });
  const [recentActivity, setRecentActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [statsRes, lowRes, histRes] = await Promise.all([
          authFetch(`/stats`),
          authFetch(`/products?low_stock=true&limit=${LOW_STOCK_PREVIEW}`),
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
        setLowStock({ items: lowData.data, total: lowData.meta?.total ?? lowData.data.length });
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

  const asOf = new Date().toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

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

      <SummaryBand stats={stats} />

      {/* Top-aligned so the shorter panel does not stretch to the timeline's height. */}
      <div className="grid-2" style={{ alignItems: "start" }}>
        <section className="panel" aria-labelledby="dashboard-low-stock">
          <div className="panel__head">
            <h2 className="panel__title" id="dashboard-low-stock">Low stock</h2>
            {lowStock.total > LOW_STOCK_PREVIEW && (
              <Link className="panel__link" to="/products?low_stock=true">View all {lowStock.total}</Link>
            )}
          </div>
          <div className="panel__body">
            {lowStock.items.length === 0 ? (
              <EmptyPanel>{loading ? "Checking stock levels..." : "Every product is above its minimum"}</EmptyPanel>
            ) : (
              <LowStockLedger items={lowStock.items} />
            )}
          </div>
        </section>

        <section className="panel" aria-labelledby="dashboard-activity">
          <div className="panel__head">
            <h2 className="panel__title" id="dashboard-activity">Recent activity</h2>
            <Link className="panel__link" to="/activity">Full log</Link>
          </div>
          <div className="panel__body">
            {recentActivity.length === 0 ? (
              <EmptyPanel>{loading ? "Loading movements..." : "No recent activity"}</EmptyPanel>
            ) : (
              <ActivityTimeline items={recentActivity} />
            )}
          </div>
        </section>
      </div>
    </section>
  );
}
