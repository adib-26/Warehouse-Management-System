import { useEffect, useState } from "react";
import { authFetch } from "../api";
import { useAuth } from "../AuthContext";


const emptyForm = { warehouse_code: "", name: "", address: "" };


export default function Warehouses() {
  const { can } = useAuth();
  const [warehouses, setWarehouses] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [message, setMessage] = useState(null);
  const [saving, setSaving] = useState(false);

  const loadWarehouses = async () => {
    try {
      const response = await authFetch("/warehouses?include_inactive=true&limit=500");
      const data = await response.json();
      if (response.ok) setWarehouses(data.data || []);
    } catch {
      setMessage({ type: "error", text: "Could not load warehouses." });
    }
  };

  useEffect(() => { loadWarehouses(); }, []);

  const createWarehouse = async (event) => {
    event.preventDefault();
    if (!form.warehouse_code.trim() || !form.name.trim()) return;
    setSaving(true);
    try {
      const response = await authFetch("/warehouses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await response.json();
      if (!response.ok) {
        setMessage({ type: "error", text: data.detail || "Could not create warehouse." });
        return;
      }
      setForm(emptyForm);
      setMessage({ type: "success", text: `${data.name} is ready for outbound dispatches.` });
      loadWarehouses();
    } catch {
      setMessage({ type: "error", text: "Could not reach the API." });
    } finally {
      setSaving(false);
    }
  };

  const setActive = async (warehouse, active) => {
    try {
      const response = await authFetch(`/warehouses/${warehouse.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active }),
      });
      const data = await response.json();
      if (!response.ok) {
        setMessage({ type: "error", text: data.detail || "Could not update warehouse." });
        return;
      }
      setMessage({ type: "success", text: `${data.name} is now ${data.active ? "active" : "inactive"}.` });
      loadWarehouses();
    } catch {
      setMessage({ type: "error", text: "Could not reach the API." });
    }
  };

  return (
    <section>
      <div className="page-header">
        <div>
          <h1 className="page-title">Warehouses</h1>
          <p className="page-subtitle">Manage the locations used to attribute completed outbound demand.</p>
        </div>
      </div>

      {message && (
        <div className={`alert alert-${message.type}`} style={{ marginBottom: 20 }}>
          <span>{message.text}</span>
          <button className="btn btn-ghost btn-xs" style={{ padding: "2px 8px" }} onClick={() => setMessage(null)}>&times;</button>
        </div>
      )}

      {can("admin", "write") && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-body">
            <h3 className="section-title">Add Warehouse</h3>
            <form onSubmit={createWarehouse}>
              <div className="form-grid" style={{ marginBottom: 16 }}>
                <div className="input-group">
                  <label className="input-label">Warehouse Code *</label>
                  <input className="input" placeholder="KL-01" value={form.warehouse_code} onChange={e => setForm({ ...form, warehouse_code: e.target.value })} required />
                </div>
                <div className="input-group">
                  <label className="input-label">Name *</label>
                  <input className="input" placeholder="Kuala Lumpur Main" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required />
                </div>
                <div className="input-group" style={{ gridColumn: "1 / -1" }}>
                  <label className="input-label">Address</label>
                  <input className="input" placeholder="Optional address or location note" value={form.address} onChange={e => setForm({ ...form, address: e.target.value })} />
                </div>
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <button className="btn btn-primary btn-sm" type="submit" disabled={saving || !form.warehouse_code.trim() || !form.name.trim()}>
                  {saving ? "Saving..." : "Add Warehouse"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Warehouse</th>
              <th>Code</th>
              <th>Address</th>
              <th>Status</th>
              {can("admin", "write") && <th style={{ textAlign: "right" }}>Actions</th>}
            </tr>
          </thead>
          <tbody>
            {warehouses.length === 0 ? (
              <tr>
                <td colSpan={can("admin", "write") ? 5 : 4} className="empty-state">
                  <div className="empty-state-text">No warehouses yet</div>
                </td>
              </tr>
            ) : warehouses.map(warehouse => (
              <tr key={warehouse.id}>
                <td style={{ fontWeight: 600 }}>{warehouse.name}</td>
                <td><span className="badge badge-neutral">{warehouse.warehouse_code}</span></td>
                <td className="muted">{warehouse.address || "-"}</td>
                <td>
                  <span className={`badge ${warehouse.active ? "badge-success" : "badge-neutral"}`}>
                    {warehouse.active ? "Active" : "Inactive"}
                  </span>
                </td>
                {can("admin", "write") && (
                  <td style={{ textAlign: "right" }}>
                    <button className="btn btn-ghost btn-xs" onClick={() => setActive(warehouse, !warehouse.active)}>
                      {warehouse.active ? "Deactivate" : "Activate"}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
