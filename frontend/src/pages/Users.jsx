import { useEffect, useState } from "react";
import { authFetch } from "../api";
import { useAuth } from "../AuthContext";
import Dialog from "../components/Dialog";
import { useToast } from "../components/FeedbackProvider";
import { formatDate } from "../format";
import PageHeader from "../components/PageHeader";

const ROLES = ["admin", "manager", "operator"];

export default function Users() {
  const { user: me, can } = useAuth();
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({ username: "", password: "", full_name: "", role: "operator" });
  const [editing, setEditing] = useState(null);
  const [newPassword, setNewPassword] = useState("");
  const toast = useToast();

  const load = () => {
    authFetch("/admin/users").then(r => r.json()).then(d => setUsers(d.data)).catch(() => {});
  };

  useEffect(() => { load(); }, []);

  const showMsg = (body, variant = "success") =>
    (variant === "error" ? toast.error(body) : toast.success(body));

  const addUser = async (e) => {
    e.preventDefault();
    try {
      const res = await authFetch("/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (res.ok) {
        setForm({ username: "", password: "", full_name: "", role: "operator" });
        load();
        showMsg(`User '${form.username}' created with role ${form.role}.`);
      } else {
        showMsg(data.detail || "Could not create user.", "error");
      }
    } catch {
      showMsg("Could not reach the API.", "error");
    }
  };

  const saveUser = async () => {
    if (!editing) return;
    const payload = { full_name: editing.full_name, role: editing.role, active: !!editing.active };
    if (newPassword) payload.password = newPassword;
    try {
      const res = await authFetch(`/admin/users/${editing.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (res.ok) {
        setEditing(null);
        setNewPassword("");
        load();
        showMsg("User updated.");
      } else {
        showMsg(data.detail || "Could not update user.", "error");
      }
    } catch {
      showMsg("Could not reach the API.", "error");
    }
  };

  const toggleActive = async (u) => {
    try {
      const res = await authFetch(`/admin/users/${u.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: !u.active }),
      });
      const data = await res.json();
      if (res.ok) {
        load();
        showMsg(`User '${u.username}' ${u.active ? "deactivated" : "activated"}.`);
      } else {
        showMsg(data.detail || "Could not update user.", "error");
      }
    } catch {
      showMsg("Could not reach the API.", "error");
    }
  };

  const canWrite = can("admin", "write");

  return (
    <section>
      <PageHeader eyebrow="Administration" title="Users" subtitle="Accounts and roles" />

      {canWrite && (
        <form onSubmit={addUser} className="card" style={{ marginBottom: 20 }}>
          <div className="card-body">
            <h3 className="section-title">Add New User</h3>
            <div className="form-grid">
              <div className="input-group">
                <label className="input-label">Username *</label>
                <input className="input" placeholder="jdoe" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} required />
              </div>
              <div className="input-group">
                <label className="input-label">Password * (min 12 characters)</label>
                <input className="input" type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} required minLength={12} maxLength={72} autoComplete="new-password" />
              </div>
              <div className="input-group">
                <label className="input-label">Full Name</label>
                <input className="input" placeholder="John Doe" value={form.full_name} onChange={e => setForm({ ...form, full_name: e.target.value })} />
              </div>
              <div className="input-group">
                <label className="input-label">Role *</label>
                <select className="select" value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}>
                  {ROLES.map(r => <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>)}
                </select>
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 16 }}>
              <button type="submit" className="btn btn-primary btn-sm">Add User</button>
            </div>
          </div>
        </form>
      )}

      <div className="table-container" tabIndex={0} role="region" aria-label="Users">
        <table>
          <thead>
            <tr>
              <th>Username</th>
              <th>Full Name</th>
              <th>Role</th>
              <th>Status</th>
              <th>Created</th>
              <th style={{ textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} style={{ opacity: u.active ? 1 : 0.5 }}>
                <td>
                  <div style={{ fontWeight: 600 }}>{u.username}</div>
                  {u.id === me?.id && <span className="muted" style={{ fontSize: "0.75rem" }}>(you)</span>}
                </td>
                <td style={{ color: "var(--text-secondary)" }}>{u.full_name || "-"}</td>
                <td>
                  <span className={`badge ${u.role === "admin" ? "badge-danger" : u.role === "manager" ? "badge-info" : "badge-neutral"}`} style={{ textTransform: "capitalize" }}>
                    {u.role}
                  </span>
                </td>
                <td>
                  {u.active ? <span className="badge badge-success">Active</span> : <span className="badge badge-warning">Inactive</span>}
                </td>
                <td className="mono" style={{ color: "var(--text-secondary)", fontSize: "0.78rem", whiteSpace: "nowrap" }}>
                  {formatDate(u.created_at)}
                </td>
                <td style={{ textAlign: "right" }}>
                  {canWrite && (
                    <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                      <button className="btn btn-ghost btn-xs" onClick={() => { setEditing({ ...u }); setNewPassword(""); }}>Edit</button>
                      {u.id !== me?.id && (
                        <button className={`btn btn-xs ${u.active ? "btn-danger" : "btn-secondary"}`} onClick={() => toggleActive(u)}>
                          {u.active ? "Deactivate" : "Activate"}
                        </button>
                      )}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={!!editing} onClose={() => setEditing(null)} title="Edit User">
        {editing && (
          <div>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="input-group">
                <label className="input-label">Username</label>
                <input className="input" value={editing.username} disabled />
              </div>
              <div className="input-group">
                <label className="input-label">Full Name</label>
                <input className="input" value={editing.full_name || ""} onChange={e => setEditing({ ...editing, full_name: e.target.value })} />
              </div>
              <div className="input-group">
                <label className="input-label">Role</label>
                <select className="select" value={editing.role} onChange={e => setEditing({ ...editing, role: e.target.value })}>
                  {ROLES.map(r => <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>)}
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">Reset Password (leave blank to keep current)</label>
                <input className="input" type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} minLength={12} maxLength={72} autoComplete="new-password" placeholder="New password (12+ characters)" />
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => setEditing(null)}>Cancel</button>
              <button className="btn btn-primary btn-sm" onClick={saveUser}>Save Changes</button>
            </div>
          </div>
        )}
      </Dialog>
    </section>
  );
}
