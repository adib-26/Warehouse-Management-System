import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import Dialog from "./Dialog";

const ToastContext = createContext(null);
const ConfirmContext = createContext(null);

// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used within a FeedbackProvider");
  return context;
}

/**
 * Promise-based replacement for window.confirm().
 *
 *   const confirm = useConfirm();
 *   if (!await confirm({ message: "Delete this?", tone: "danger" })) return;
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useConfirm() {
  const context = useContext(ConfirmContext);
  if (!context) throw new Error("useConfirm must be used within a FeedbackProvider");
  return context;
}

let sequence = 0;

const ICONS = {
  success: <path d="M20 6 9 17l-5-5" />,
  error: <path d="M18 6 6 18M6 6l12 12" />,
  warning: <path d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />,
  info: <path d="M12 16v-4m0-4h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0z" />,
};

function ToastItem({ toast, onDismiss }) {
  const { id, type, message, duration } = toast;
  const timer = useRef(null);

  const stop = useCallback(() => window.clearTimeout(timer.current), []);
  const start = useCallback(() => {
    stop();
    if (duration > 0) timer.current = window.setTimeout(() => onDismiss(id), duration);
  }, [duration, id, onDismiss, stop]);

  useEffect(() => {
    start();
    return stop;
  }, [start, stop]);

  // Errors and warnings interrupt (assertive); routine feedback is polite.
  const role = type === "error" || type === "warning" ? "alert" : "status";

  return (
    <div
      className={`toast toast--${type}${toast.leaving ? " toast--leaving" : ""}`}
      role={role}
      onMouseEnter={stop}
      onMouseLeave={start}
      onFocus={stop}
      onBlur={start}
    >
      <span className="toast__icon" aria-hidden="true">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          {ICONS[type] || ICONS.info}
        </svg>
      </span>
      <p className="toast__msg">{message}</p>
      <button type="button" className="icon-btn toast__close" aria-label="Dismiss notification" onClick={() => onDismiss(id)}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M18 6 6 18M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

export function FeedbackProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const [confirmOptions, setConfirmOptions] = useState(null);
  const resolverRef = useRef(null);

  /* ------------------------------------------------------------- toasts */

  const dismiss = useCallback((id) => {
    setToasts((list) => list.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
    window.setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), 190);
  }, []);

  const push = useCallback((message, type = "info", options = {}) => {
    const id = ++sequence;
    // Errors persist until dismissed; routine feedback auto-hides.
    const duration = options.duration ?? (type === "error" ? 0 : 5000);
    setToasts((list) => [...list, { id, message, type, duration }]);
    return id;
  }, []);

  const toastApi = useMemo(
    () => ({
      show: push,
      success: (message, options) => push(message, "success", options),
      error: (message, options) => push(message, "error", options),
      warning: (message, options) => push(message, "warning", options),
      info: (message, options) => push(message, "info", options),
      dismiss,
    }),
    [push, dismiss],
  );

  /* ------------------------------------------------------------ confirm */

  const confirm = useCallback((options = {}) => new Promise((resolve) => {
    resolverRef.current = resolve;
    setConfirmOptions(options);
  }), []);

  // Settling twice is harmless: the resolver is cleared on the first call, so
  // the follow-up `close` event from hiding the dialog is a no-op.
  const settle = useCallback((result) => {
    const resolve = resolverRef.current;
    resolverRef.current = null;
    setConfirmOptions(null);
    resolve?.(result);
  }, []);

  const destructive = confirmOptions?.tone === "danger";

  return (
    <ToastContext.Provider value={toastApi}>
      <ConfirmContext.Provider value={confirm}>
        {children}

        <div className="toast-region" role="region" aria-label="Notifications">
          {toasts.map((toast) => (
            <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />
          ))}
        </div>

        <Dialog
          open={!!confirmOptions}
          onClose={() => settle(false)}
          title={confirmOptions?.title || "Are you sure?"}
          maxWidth={460}
          tone={destructive ? "danger" : undefined}
        >
          <p style={{ margin: 0, color: "var(--text-primary)" }}>{confirmOptions?.message}</p>
          <div className="dialog-actions">
            {/* A destructive confirmation focuses the safe action. */}
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              autoFocus={destructive}
              onClick={() => settle(false)}
            >
              {confirmOptions?.cancelLabel || "Cancel"}
            </button>
            <button
              type="button"
              className={`btn btn-sm ${destructive ? "btn-danger-solid" : "btn-primary"}`}
              autoFocus={!destructive}
              onClick={() => settle(true)}
            >
              {confirmOptions?.confirmLabel || "Confirm"}
            </button>
          </div>
        </Dialog>
      </ConfirmContext.Provider>
    </ToastContext.Provider>
  );
}
