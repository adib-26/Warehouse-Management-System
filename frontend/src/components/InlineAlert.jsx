/**
 * Inline alert for messages that must stay next to the UI that raised them,
 * chiefly errors inside a modal <dialog>. A toast cannot be used there: the
 * modal makes everything outside it inert, so the toast could not be reached
 * or dismissed until the dialog closed.
 *
 * Errors use role="alert" (assertive); everything else uses role="status".
 */
export default function InlineAlert({ type = "error", children, onDismiss, style }) {
  if (!children) return null;
  return (
    <div className={`alert alert-${type}`} role={type === "error" ? "alert" : "status"} style={style}>
      <span>{children}</span>
      {onDismiss && (
        <button type="button" className="icon-btn alert__close" aria-label="Dismiss message" onClick={onDismiss}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  );
}
