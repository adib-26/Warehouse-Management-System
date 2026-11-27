/**
 * Shared formatting helpers: numbers, dates, action labels, and API errors.
 */

const EM_DASH = "—";

/* ------------------------------------------------------------------ numbers */

/**
 * Format a stock quantity. Quantities are decimal (step 0.01) and are often the
 * result of client-side arithmetic, so round before formatting — otherwise sums
 * surface floating-point noise such as 0.30000000000000004.
 */
export function formatQuantity(value) {
  const number = Number(value);
  if (value === null || value === undefined || value === "" || !Number.isFinite(number)) return EM_DASH;
  const rounded = Math.round(number * 100) / 100;
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(rounded);
}

/** Format a signed stock movement, e.g. "+12" / "-3.5". */
export function formatDelta(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return EM_DASH;
  const rounded = Math.round(number * 100) / 100;
  return `${rounded > 0 ? "+" : ""}${formatQuantity(rounded)}`;
}

/* -------------------------------------------------------------------- dates */

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;
const TIMESTAMP =
  /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$/;

/**
 * Parse a timestamp from the API into a Date.
 *
 * The API returns naive UTC timestamps ("2026-01-02 03:04:05"). Appending "Z"
 * and handing the string to `new Date()` is not reliable: support for
 * space-separated and second-less forms is implementation-defined, so browsers
 * disagree. Parsing the parts and going through Date.UTC() is deterministic.
 *
 * Returns null when the value is absent or unparseable.
 */
export function parseApiDate(value) {
  if (value === null || value === undefined || value === "") return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;

  const text = String(value).trim();
  const match = TIMESTAMP.exec(text);
  if (!match) {
    const loose = new Date(text);
    return Number.isNaN(loose.getTime()) ? null : loose;
  }

  const [, year, month, day, hour, minute, second, fraction, offset] = match;
  // An explicit non-UTC offset is already unambiguous; let the engine apply it.
  if (offset && offset !== "Z") {
    const withOffset = new Date(text);
    return Number.isNaN(withOffset.getTime()) ? null : withOffset;
  }
  const milliseconds = fraction ? Math.round(Number(`0.${fraction}`) * 1000) : 0;
  const stamp = Date.UTC(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
    second ? Number(second) : 0,
    milliseconds,
  );
  return Number.isNaN(stamp) ? null : new Date(stamp);
}

/** Date and time in the viewer's locale. */
export function formatDateTime(value) {
  const parsed = parseApiDate(value);
  return parsed ? parsed.toLocaleString() : EM_DASH;
}

/** Date only, in the viewer's locale. */
export function formatDate(value) {
  const parsed = parseApiDate(value);
  return parsed ? parsed.toLocaleDateString() : EM_DASH;
}

/** Compact date and time for timelines, e.g. "Nov 26, 03:04 PM" in the viewer's locale. */
export function formatShortDateTime(value) {
  const parsed = parseApiDate(value);
  return parsed
    ? parsed.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : EM_DASH;
}

/**
 * Format a calendar date that carries no time ("2026-01-02", e.g. a dispatch
 * date). Rendered from its own parts so it never shifts a day in a timezone
 * behind UTC.
 */
export function formatPlainDate(value) {
  if (!value) return EM_DASH;
  const match = DATE_ONLY.exec(String(value).trim());
  if (!match) return formatDate(value);
  const [, year, month, day] = match;
  return new Date(Number(year), Number(month) - 1, Number(day)).toLocaleDateString();
}

/* ------------------------------------------------------------ action labels */

const ACTION_META = {
  STOCK_IN:     { cls: "badge-success", label: "Stock In" },
  STOCK_OUT:    { cls: "badge-danger",  label: "Stock Out" },
  STOCK_ADJUST: { cls: "badge-warning", label: "Adjusted" },
  CREATE:       { cls: "badge-success", label: "Created" },
  UPDATE:       { cls: "badge-info",    label: "Updated" },
  DELETE:       { cls: "badge-danger",  label: "Deleted" },
  ARCHIVE:      { cls: "badge-warning", label: "Archived" },
  UNDO:         { cls: "badge-warning", label: "Undone" },
  BULK_IMPORT:  { cls: "badge-warning", label: "Bulk Import" },
  UPLOAD:       { cls: "badge-info",    label: "Upload" },
  LOGIN:        { cls: "badge-info",    label: "Login" },
  LOGIN_FAILED: { cls: "badge-danger",  label: "Login failed" },
};

/** Badge class and readable label for a movement or audit action code. */
export function actionMeta(type) {
  return ACTION_META[type] || { cls: "badge-neutral", label: type || EM_DASH };
}

/** Readable label for an action code, e.g. STOCK_IN -> "Stock In". */
export function actionLabel(type) {
  return actionMeta(type).label;
}

/**
 * Known movement action types, in the order they should appear in a filter.
 * Used as a static list so selecting one filter value does not collapse the
 * remaining options to whatever happens to be loaded.
 */
export const MOVEMENT_ACTIONS = [
  "STOCK_IN",
  "STOCK_OUT",
  "STOCK_ADJUST",
  "CREATE",
  "UPDATE",
  "DELETE",
  "ARCHIVE",
];

/* --------------------------------------------------------------- API errors */

/** Pull a readable message out of a FastAPI error body. */
export function responseErrorMessage(data, fallback) {
  if (typeof data?.detail === "string") return data.detail;
  if (Array.isArray(data?.detail)) {
    return data.detail.map(item => item.msg).filter(Boolean).join("; ") || fallback;
  }
  if (data?.detail && typeof data.detail === "object") {
    return data.detail.message || data.detail.error || fallback;
  }
  return fallback;
}
