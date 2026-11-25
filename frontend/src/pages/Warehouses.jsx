import { useCallback, useEffect, useState } from "react";
import { authFetch } from "../api";
import { useAuth } from "../AuthContext";
import { useToast } from "../components/FeedbackProvider";
import { responseErrorMessage } from "../format";
import PageHeader from "../components/PageHeader";

const emptyForm = { warehouse_code: "", name: "", address: "" };

export default function Warehouses() {
  const { can } = useAuth();
  const toast = useToast();
  const [warehouses, setWarehouses] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const loadWarehouses = useCallback(async () => {
    try {
      const response = await authFetch("/warehouses?include_inactive=true&limit=500");
      const data = await response.json();
      if (response.ok) setWarehouses(data.data || []);
    } catch {
      toast.error("Could not load warehouses.");
    }
  }, [toast]);

  useEffect(() => { loadWarehouses(); }, [loadWarehouses]);

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
        toast.error(responseErrorMessage(data, "Could not create warehouse."));
        return;
      }
      setForm(emptyForm);
      toast.success(`${data.name} is ready for outbound dispatches.`);
      loadWarehouses();
    } catch {
      toast.error("Could not reach the API.");
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
        toast.error(responseErrorMessage(data, "Could not update warehouse."));
        return;
      }
      toast.success(`${data.name} is now ${data.active ? "active" : "inactive"}.`);
      loadWarehouses();
    } catch {
      toast.error("Could not reach the API.");
    }
  };

  const canWrite = can("admin", "write");

  return (
    <section>
      <PageHeader eyebrow="Administration" title="Warehouses" subtitle="Where stock is held" />

      {canWrite && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-body">
            <h2 className="section-title">Add Warehouse</h2>
            <form onSubmit={createWarehouse}>
              <div className="form-grid" style={{ marginBottom: 16 }}>
                <div className="input-group">
                  <label className="input-label" htmlFor="warehouse-code">Warehouse Code *</label>
                  <input id="warehouse-code" className="input" placeholder="KL-01" value={form.warehouse_code} onChange={e => setForm({ ...form, warehouse_code: e.target.value })} required />
                </div>
                <div className="input-group">
                  <label className="input-label" htmlFor="warehouse-name">Name *</label>
                  <input id="warehouse-name" className="input" placeholder="Kuala Lumpur Main" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required />
                </div>
                <div className="input-group" style={{ gridColumn: "1 / -1" }}>
                  <label className="input-label" htmlFor="warehouse-address">Address</label>
                  <input id="warehouse-address" className="input" placeholder="Optional address or location note" value={form.address} onChange={e => setForm({ ...form, address: e.target.value })} />
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

      <div className="table-container" tabIndex={0} role="region" aria-label="Warehouses">
        <table>
          <thead>
            <tr>
              <th>Warehouse</th>
              <th>Code</th>
              <th>Address</th>
              <th>Status</th>
              {canWrite && <th style={{ textAlign: "right" }}>Actions</th>}
            </tr>
          </thead>
          <tbody>
            {warehouses.length === 0 ? (
              <tr>
                <td colSpan={canWrite ? 5 : 4} className="empty-state">
                  <div className="empty-state-text">No warehouses yet</div>
                </td>
              </tr>
            ) : warehouses.map(warehouse => (
              <tr key={warehouse.id}>
                <td style={{ fontWeight: 600 }}>{warehouse.name}</td>
                <td><span className="badge badge-neutral mono">{warehouse.warehouse_code}</span></td>
                <td className="muted">{warehouse.address || "—"}</td>
                <td>
                  <span className={`badge ${warehouse.active ? "badge-success" : "badge-neutral"}`}>
                    {warehouse.active ? "Active" : "Inactive"}
                  </span>
                </td>
                {canWrite && (
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
