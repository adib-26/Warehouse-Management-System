import { useEffect, useState } from "react";
import { authFetch } from "../api";
import { useAuth } from "../AuthContext";
import Dialog from "../components/Dialog";
import InlineAlert from "../components/InlineAlert";
import { useToast } from "../components/FeedbackProvider";
import { formatDate, responseErrorMessage } from "../format";
import PageHeader from "../components/PageHeader";

const ROLES = ["admin", "manager", "operator"];
const MIN_PASSWORD = 12;

const EMPTY_USER = { username: "", password: "", full_name: "", role: "operator" };

const titleCase = (value) => value.charAt(0).toUpperCase() + value.slice(1);

/**
 * One dialog for both creating and editing an account. Creating asks for a
 * username and password; editing locks the username and offers an optional
 * password reset instead.
 */
function UserFormDialog({ form, onClose, onChange, onSubmit, submitting, error, onDismissError }) {
  const open = !!form;
  const values = form?.values ?? EMPTY_USER;
  const isAdd = form?.mode === "add";
  const set = (patch) => onChange({ ...values, ...patch });

  return (
    <Dialog open={open} onClose={onClose} title={isAdd ? "New User" : "Edit User"} maxWidth={560}>
      <form onSubmit={onSubmit}>
        <div className="form-grid">
          <div className="input-group" style={{ gridColumn: "1 / -1" }}>
            <label className="input-label" htmlFor="user-username">Username {isAdd && "*"}</label>
            <input
              id="user-username"
              className="input mono"
              placeholder="jdoe"
              value={values.username || ""}
              onChange={e => set({ username: e.target.value })}
              disabled={!isAdd}
              required={isAdd}
            />
            {!isAdd && <span className="input-hint">A username cannot be changed after the account is created.</span>}
          </div>
          <div className="input-group">
            <label className="input-label" htmlFor="user-fullname">Full name</label>
            <input
              id="user-fullname"
              className="input"
              placeholder="Jane Doe"
              value={values.full_name || ""}
              onChange={e => set({ full_name: e.target.value })}
            />
          </div>
          <div className="input-group">
            <label className="input-label" htmlFor="user-role">Role *</label>
            <select
              id="user-role"
              className="select"
              value={values.role}
              onChange={e => set({ role: e.target.value })}
            >
              {ROLES.map(r => <option key={r} value={r}>{titleCase(r)}</option>)}
            </select>
          </div>
          <div className="input-group" style={{ gridColumn: "1 / -1" }}>
            <label className="input-label" htmlFor="user-password">
              {isAdd ? "Password *" : "Reset password"}
            </label>
            <input
              id="user-password"
              className="input"
              type="password"
              value={values.password || ""}
              onChange={e => set({ password: e.target.value })}
              minLength={MIN_PASSWORD}
              maxLength={72}
              autoComplete="new-password"
              required={isAdd}
              placeholder={isAdd ? "" : "Leave blank to keep the current password"}
            />
            <span className="input-hint">At least {MIN_PASSWORD} characters.</span>
          </div>
        </div>

        <InlineAlert onDismiss={onDismissError} style={{ marginTop: 20 }}>{error}</InlineAlert>

        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary btn-sm" disabled={submitting}>
            {submitting ? "Saving..." : isAdd ? "Add User" : "Save changes"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

export default function Users() {
  const { user: me, can } = useAuth();
  const toast = useToast();
  const [users, setUsers] = useState([]);
  // null when the dialog is closed, otherwise { mode, values }.
  const [form, setForm] = useState(null);
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const load = () => {
    authFetch("/admin/users").then(r => r.json()).then(d => setUsers(d.data)).catch(() => {});
  };

  useEffect(() => { load(); }, []);

  const openAdd = () => { setFormError(null); setForm({ mode: "add", values: { ...EMPTY_USER } }); };
  const openEdit = (u) => {
    setFormError(null);
    // password is the optional reset field, so it always starts empty.
    setForm({ mode: "edit", values: { ...u, password: "" } });
  };
  const closeForm = () => { setForm(null); setFormError(null); };

  // Errors stay inside the dialog (the toast region is inert behind it) and
  // the dialog stays open so the operator's input is kept.
  const submitForm = async (event) => {
    event.preventDefault();
    if (!form) return;
    setSubmitting(true);
    setFormError(null);
    const values = form.values;
    const isAdd = form.mode === "add";
    const payload = isAdd
      ? { username: values.username, password: values.password, full_name: values.full_name, role: values.role }
      : {
          full_name: values.full_name,
          role: values.role,
          active: !!values.active,
          // Only sent when the operator actually typed a new password.
          ...(values.password ? { password: values.password } : {}),
        };
    try {
      const res = await authFetch(isAdd ? "/admin/users" : `/admin/users/${values.id}`, {
        method: isAdd ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        closeForm();
        load();
        toast.success(isAdd ? `${values.username} was created as ${values.role}.` : "Changes saved.");
      } else {
        const data = await res.json().catch(() => ({}));
        setFormError(responseErrorMessage(data, isAdd ? "Could not create user." : "Could not update user."));
      }
    } catch {
      setFormError("Could not reach the API.");
    } finally {
      setSubmitting(false);
    }
  };

  const toggleActive = async (u) => {
    try {
      const res = await authFetch(`/admin/users/${u.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: !u.active }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        toast.error(responseErrorMessage(data, "Could not update user."));
        return;
      }
      load();
      toast.success(`${u.username} was ${u.active ? "deactivated" : "activated"}.`);
    } catch {
      toast.error("Could not reach the API.");
    }
  };

  const canWrite = can("admin", "write");

  return (
    <section>
      <PageHeader
        eyebrow="Administration"
        title="Users"
        subtitle="Accounts and roles"
        actions={canWrite && (
          <button className="btn btn-primary btn-sm" onClick={openAdd}>Add User</button>
        )}
      />

      <div className="table-container" tabIndex={0} role="region" aria-label="Users">
        <table>
          <thead>
            <tr>
              <th>Username</th>
              <th>Full name</th>
              <th>Role</th>
              <th>Status</th>
              <th>Created</th>
              {canWrite && <th style={{ textAlign: "right" }}>Actions</th>}
            </tr>
          </thead>
          <tbody>
            {users.length === 0 ? (
              <tr>
                <td colSpan={canWrite ? 6 : 5} className="empty-state">
                  <div className="empty-state-text">No accounts yet</div>
                </td>
              </tr>
            ) : users.map(u => (
              <tr key={u.id}>
                <td>
                  <span className="sku" style={{ fontWeight: 600 }}>{u.username}</span>
                  {u.id === me?.id && <span className="muted" style={{ fontSize: "0.75rem" }}> (you)</span>}
                </td>
                <td style={{ color: "var(--text-secondary)" }}>{u.full_name || "—"}</td>
                <td>
                  <span className={`badge ${u.role === "admin" ? "badge-danger" : u.role === "manager" ? "badge-info" : "badge-neutral"}`}>
                    {u.role}
                  </span>
                </td>
                <td>
                  {u.active
                    ? <span className="badge badge-success">Active</span>
                    : <span className="badge badge-neutral">Inactive</span>}
                </td>
                <td className="mono" style={{ color: "var(--text-secondary)", fontSize: "0.78rem", whiteSpace: "nowrap" }}>
                  {formatDate(u.created_at)}
                </td>
                {canWrite && (
                  <td style={{ textAlign: "right" }}>
                    <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                      <button className="btn btn-ghost btn-xs" onClick={() => openEdit(u)}>Edit</button>
                      {u.id !== me?.id && (
                        <button
                          className={`btn btn-xs ${u.active ? "btn-danger" : "btn-secondary"}`}
                          onClick={() => toggleActive(u)}
                        >
                          {u.active ? "Deactivate" : "Activate"}
                        </button>
                      )}
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <UserFormDialog
        form={form}
        submitting={submitting}
        error={formError}
        onDismissError={() => setFormError(null)}
        onClose={closeForm}
        onChange={values => setForm(current => (current ? { ...current, values } : current))}
        onSubmit={submitForm}
      />
    </section>
  );
}
