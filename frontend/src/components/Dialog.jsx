import { useEffect, useId, useRef } from "react";

/**
 * Shared modal built on the native <dialog> element. The browser provides the
 * backdrop, top-layer rendering, focus containment, Escape handling, and focus
 * return, so there is no hand-rolled focus trap or role="dialog".
 *
 * Props: open, onClose, title, children, maxWidth (px).
 */
export default function Dialog({ open, onClose, title, children, maxWidth = 560 }) {
  const ref = useRef(null);
  const titleId = useId();

  // Enable declarative light-dismiss; fall back to a pointer check on browsers
  // without the `closedby` attribute.
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return undefined;
    dialog.setAttribute("closedby", "any");
    if ("closedBy" in HTMLDialogElement.prototype) return undefined;

    const handlePointer = (event) => {
      if (event.target !== dialog) return;
      const rect = dialog.getBoundingClientRect();
      const inside =
        rect.top <= event.clientY &&
        event.clientY <= rect.top + rect.height &&
        rect.left <= event.clientX &&
        event.clientX <= rect.left + rect.width;
      if (!inside) dialog.close();
    };
    dialog.addEventListener("click", handlePointer);
    return () => dialog.removeEventListener("click", handlePointer);
  }, []);

  // Keep the element's open state in sync with the `open` prop.
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    else if (!open && dialog.open) dialog.close();
  }, [open]);

  // Native close requests (Escape, backdrop, close button) flow back to React.
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return undefined;
    const handleClose = () => onClose?.();
    dialog.addEventListener("close", handleClose);
    return () => dialog.removeEventListener("close", handleClose);
  }, [onClose]);

  return (
    <dialog
      ref={ref}
      className="app-dialog"
      aria-labelledby={title ? titleId : undefined}
      style={{ width: `min(92vw, ${maxWidth}px)` }}
    >
      <div className="app-dialog__inner">
        {title && (
          <div className="app-dialog__head">
            <h2 className="app-dialog__title" id={titleId}>{title}</h2>
            <button type="button" className="icon-btn" aria-label="Close dialog" onClick={() => onClose?.()}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}
        {children}
      </div>
    </dialog>
  );
}
