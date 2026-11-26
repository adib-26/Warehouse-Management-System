import Dialog from "./Dialog";
import InlineAlert from "./InlineAlert";

/**
 * Create/edit dialog for a trading party — a customer or a supplier. Both
 * carry the same fields, so one component serves both pages instead of each
 * repeating the form markup.
 *
 * `form` is null when closed, otherwise { mode: "add" | "edit", values }.
 * Errors render inline: the modal makes the toast region inert, and keeping
 * the dialog open preserves what the operator typed.
 */
/**
 * Field shape shared by the customer and supplier forms. Exported so each
 * page can seed a blank draft without restating the fields.
 */
// eslint-disable-next-line react-refresh/only-export-components
export const EMPTY_PARTY = {
  name: "",
  contact_person: "",
  email: "",
  phone: "",
  address: "",
  notes: "",
};

export default function PartyFormDialog({
  form,
  noun,
  onClose,
  onChange,
  onSubmit,
  submitting,
  error,
  onDismissError,
}) {
  const open = !!form;
  const values = form?.values ?? EMPTY_PARTY;
  const isAdd = form?.mode === "add";
  const set = (patch) => onChange({ ...values, ...patch });
  const id = `party-${noun.toLowerCase()}`;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={isAdd ? `New ${noun}` : `Edit ${noun}`}
      maxWidth={620}
    >
      <form onSubmit={onSubmit}>
        <div className="form-grid">
          <div className="input-group" style={{ gridColumn: "1 / -1" }}>
            <label className="input-label" htmlFor={`${id}-name`}>Name *</label>
            <input
              id={`${id}-name`}
              className="input"
              placeholder={`${noun} name`}
              value={values.name}
              onChange={e => set({ name: e.target.value })}
              required
            />
          </div>
          <div className="input-group">
            <label className="input-label" htmlFor={`${id}-contact`}>Contact person</label>
            <input
              id={`${id}-contact`}
              className="input"
              placeholder="Jane Doe"
              value={values.contact_person || ""}
              onChange={e => set({ contact_person: e.target.value })}
            />
          </div>
          <div className="input-group">
            <label className="input-label" htmlFor={`${id}-email`}>Email</label>
            <input
              id={`${id}-email`}
              className="input"
              type="email"
              placeholder="name@example.com"
              value={values.email || ""}
              onChange={e => set({ email: e.target.value })}
            />
          </div>
          <div className="input-group">
            <label className="input-label" htmlFor={`${id}-phone`}>Phone</label>
            <input
              id={`${id}-phone`}
              className="input"
              placeholder="+60 3 0000 0000"
              value={values.phone || ""}
              onChange={e => set({ phone: e.target.value })}
            />
          </div>
          <div className="input-group" style={{ gridColumn: "1 / -1" }}>
            <label className="input-label" htmlFor={`${id}-address`}>Address</label>
            <input
              id={`${id}-address`}
              className="input"
              placeholder="Street, city, postcode"
              value={values.address || ""}
              onChange={e => set({ address: e.target.value })}
            />
          </div>
          <div className="input-group" style={{ gridColumn: "1 / -1" }}>
            <label className="input-label" htmlFor={`${id}-notes`}>Notes</label>
            <textarea
              id={`${id}-notes`}
              className="input textarea"
              placeholder="Delivery windows, dock constraints, account terms..."
              value={values.notes || ""}
              onChange={e => set({ notes: e.target.value })}
            />
          </div>
        </div>

        <InlineAlert onDismiss={onDismissError} style={{ marginTop: 20 }}>{error}</InlineAlert>

        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary btn-sm" disabled={submitting}>
            {submitting ? "Saving..." : isAdd ? `Add ${noun}` : "Save changes"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
