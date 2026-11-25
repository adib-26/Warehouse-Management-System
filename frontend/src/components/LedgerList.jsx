import { actionMeta, formatDate, formatDelta } from "../format";

/**
 * Compact movement ledger shared by the Stock and Dashboard pages.
 * Items carry { id?, name, sku?, delta, action_type, created_at }.
 */
export default function LedgerList({ items, emptyText = "No recent movements" }) {
  if (!items || items.length === 0) {
    return (
      <div className="empty-state" style={{ padding: 24 }}>
        <div className="empty-state-text">{emptyText}</div>
      </div>
    );
  }

  return (
    <ul className="ledger-list">
      {items.map((item, index) => {
        const meta = actionMeta(item.action_type);
        const delta = Number(item.delta);
        const direction = delta > 0 ? "up" : delta < 0 ? "down" : "flat";
        return (
          <li className="ledger-row" key={item.id ?? index}>
            <span className="ledger-row__id">
              <span className="ledger-row__name">{item.name}</span>
              {item.sku && <span className="muted ledger-row__sku">{item.sku}</span>}
            </span>
            <span className="ledger-row__meta">
              <span className={`ledger-num ledger-num--${direction}`}>
                {delta === 0 ? "—" : formatDelta(delta)}
              </span>
              <span className={`badge ${meta.cls}`}>{meta.label}</span>
              <span className="muted ledger-row__time">{formatDate(item.created_at)}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
