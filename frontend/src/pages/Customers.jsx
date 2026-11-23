import { useCallback, useEffect, useState } from "react";
import { authFetch } from "../api";
import { useAuth } from "../AuthContext";

function Dialog({ open, onClose, title, children }) {
  if (!open) return null;
  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog-content" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <h2 className="dialog-title">{title}</h2>
          <button onClick={onClose} className="btn btn-ghost btn-xs" style={{ padding: "4px 8px", fontSize: 18 }}>
            &times;
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export default function Customers() {
  const { can } = useAuth();
  const [customers, setCustomers] = useState([]);
  const [q, setQ] = useState("");
  const [form, setForm] = useState({ name: "", contact_person: "", email: "", phone: "", address: "", notes: "" });
  const [editing, setEditing] = useState(null);
  const [dialog, setDialog] = useState(null);

  const load = useCallback(() => {
    const params = q ? `?q=${encodeURIComponent(q)}` : "";
    authFetch(`/customers${params}`).then(r => r.json()).then(d => setCustomers(d.data)).catch(() => {});
  }, [q]);

  useEffect(() => { load(); }, [load]);

  const showMsg = (title, body, variant = "success") => setDialog({ title, body, variant });

  const addCustomer = async (e) => {
    e.preventDefault();
    try {
      const res = await authFetch(`/customers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (res.status === 201) {
        setForm({ name: "", contact_person: "", email: "", phone: "", address: "", notes: "" });
        load();
        showMsg("Customer added", `${form.name} has been created.`);
      } else {
        showMsg("Error", data.detail || "Could not add customer.", "error");
      }
    } catch {
      showMsg("Network error", "Could not reach the API.", "error");
    }
  };

  const updateCustomer = async () => {
    if (!editing) return;
    try {
      const res = await authFetch(`/customers/${editing.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editing),
      });
      if (res.ok) {
        setEditing(null);
        load();
        showMsg("Customer updated", "Changes saved successfully.");
      } else {
        const data = await res.json();
        showMsg("Error", data.detail || "Could not update.", "error");
      }
    } catch {
      showMsg("Network error", "Could not reach the API.", "error");
    }
  };

  const deleteCustomer = async (id, name) => {
    if (!confirm(`Delete customer "${name}"?`)) return;
    try {
      await authFetch(`/customers/${id}`, { method: "DELETE" });
      load();
      showMsg("Customer deleted", `${name} has been removed.`);
    } catch {
      showMsg("Error", "Could not delete customer.", "error");
    }
  };

  return (
    <section>
      <div className="page-header">
        <div>
          <h1 className="page-title">Customers</h1>
          <p className="page-subtitle">Manage your customer contacts</p>
        </div>
      </div>

      {can("customers", "write") && (
      <form onSubmit={addCustomer} className="card" style={{ marginBottom: 20 }}>
        <div className="card-body">
          <h3 className="section-title">Add New Customer</h3>
          <div className="form-grid">
            <div className="input-group">
              <label className="input-label">Name *</label>
              <input className="input" placeholder="Customer name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required />
            </div>
            <div className="input-group">
              <label className="input-label">Contact Person</label>
              <input className="input" placeholder="John Doe" value={form.contact_person} onChange={e => setForm({ ...form, contact_person: e.target.value })} />
            </div>
            <div className="input-group">
              <label className="input-label">Email</label>
              <input className="input" type="email" placeholder="customer@example.com" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} />
            </div>
            <div className="input-group">
              <label className="input-label">Phone</label>
              <input className="input" placeholder="+1 (555) 000-0000" value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} />
            </div>
            <div className="input-group" style={{ gridColumn: "1 / -1" }}>
              <label className="input-label">Address</label>
              <input className="input" placeholder="Full address" value={form.address} onChange={e => setForm({ ...form, address: e.target.value })} />
            </div>
            <div className="input-group" style={{ gridColumn: "1 / -1" }}>
              <label className="input-label">Notes</label>
              <textarea className="input textarea" placeholder="Additional notes..." value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
            </div>
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 16 }}>
            <button type="submit" className="btn btn-primary btn-sm">Add Customer</button>
          </div>
        </div>
      </form>
      )}

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-body" style={{ paddingBottom: 12 }}>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <input
              className="input"
              placeholder="Search customers..."
              value={q}
              onChange={e => setQ(e.target.value)}
              onKeyDown={e => e.key === "Enter" && load()}
              style={{ maxWidth: 320 }}
            />
            <button className="btn btn-secondary btn-sm" onClick={load}>Search</button>
            <span className="muted" style={{ marginLeft: "auto" }}>{customers.length} customer{customers.length !== 1 ? "s" : ""}</span>
          </div>
        </div>
      </div>

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Contact</th>
              <th>Email</th>
              <th>Phone</th>
              <th>Address</th>
              <th style={{ textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {customers.length === 0 ? (
              <tr>
                <td colSpan={6} className="empty-state">
                  <div className="empty-state-text">No customers found</div>
                </td>
              </tr>
            ) : (
              customers.map(c => (
                <tr key={c.id}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{c.name}</div>
                    {c.notes && <div className="muted" style={{ fontSize: "0.8rem", marginTop: 2 }}>{c.notes.slice(0, 60)}{c.notes.length > 60 ? "..." : ""}</div>}
                  </td>
                  <td style={{ color: "var(--text-secondary)" }}>{c.contact_person || "-"}</td>
                  <td style={{ color: "var(--text-secondary)" }}>{c.email || "-"}</td>
                  <td style={{ color: "var(--text-secondary)" }}>{c.phone || "-"}</td>
                  <td style={{ color: "var(--text-secondary)", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.address || "-"}</td>
                  <td style={{ textAlign: "right" }}>
                    <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                      {can("customers", "write") && (
                        <button className="btn btn-ghost btn-xs" onClick={() => setEditing({ ...c })}>Edit</button>
                      )}
                      {can("customers", "delete") && (
                        <button className="btn btn-danger btn-xs" onClick={() => deleteCustomer(c.id, c.name)}>Delete</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Dialog open={!!editing} onClose={() => setEditing(null)} title="Edit Customer">
        {editing && (
          <div>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="input-group">
                <label className="input-label">Name</label>
                <input className="input" value={editing.name} onChange={e => setEditing({ ...editing, name: e.target.value })} />
              </div>
              <div className="input-group">
                <label className="input-label">Contact Person</label>
                <input className="input" value={editing.contact_person} onChange={e => setEditing({ ...editing, contact_person: e.target.value })} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div className="input-group">
                  <label className="input-label">Email</label>
                  <input className="input" value={editing.email} onChange={e => setEditing({ ...editing, email: e.target.value })} />
                </div>
                <div className="input-group">
                  <label className="input-label">Phone</label>
                  <input className="input" value={editing.phone} onChange={e => setEditing({ ...editing, phone: e.target.value })} />
                </div>
              </div>
              <div className="input-group">
                <label className="input-label">Address</label>
                <input className="input" value={editing.address} onChange={e => setEditing({ ...editing, address: e.target.value })} />
              </div>
              <div className="input-group">
                <label className="input-label">Notes</label>
                <textarea className="input textarea" value={editing.notes} onChange={e => setEditing({ ...editing, notes: e.target.value })} />
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => setEditing(null)}>Cancel</button>
              <button className="btn btn-primary btn-sm" onClick={updateCustomer}>Save Changes</button>
            </div>
          </div>
        )}
      </Dialog>

      <Dialog open={!!dialog} onClose={() => setDialog(null)} title={dialog?.variant === "error" ? "Error" : "Success"}>
        <p style={{ color: "var(--text-secondary)" }}>{dialog?.body}</p>
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 20 }}>
          <button className="btn btn-primary btn-sm" onClick={() => setDialog(null)}>OK</button>
        </div>
      </Dialog>
    </section>
  );
}
