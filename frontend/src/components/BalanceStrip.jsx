import { formatQuantity } from "../format";

/**
 * Before/after balance preview shared by the Stock, Inbound, and Outbound
 * forms: shows the current on-hand figure next to the projected result.
 *
 * tone: "positive" | "negative" | "neutral" (drives the tint and result color)
 */
export default function BalanceStrip({ title, subtitle, current, after, tone = "neutral", note }) {
  return (
    <div className="balance-strip" data-tone={tone}>
      <div className="balance-strip__id">
        {title && <div className="balance-strip__name">{title}</div>}
        {subtitle && <div className="muted" style={{ fontSize: "0.78rem" }}>{subtitle}</div>}
        {note && <div className="muted" style={{ fontSize: "0.78rem", marginTop: 2 }}>{note}</div>}
      </div>
      <div className="balance-flow">
        <div className="balance-cell">
          <span className="balance-cell__label">On hand</span>
          <span className="balance-cell__value">{formatQuantity(current)}</span>
        </div>
        <svg className="balance-arrow" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M5 12h14M13 6l6 6-6 6" />
        </svg>
        <div className="balance-cell">
          <span className="balance-cell__label">After</span>
          <span className="balance-cell__value balance-cell__value--result">{formatQuantity(after)}</span>
        </div>
      </div>
    </div>
  );
}
