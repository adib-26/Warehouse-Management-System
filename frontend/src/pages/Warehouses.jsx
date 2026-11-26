import { useCallback, useEffect, useState } from "react";
import { authFetch } from "../api";
import { useAuth } from "../AuthContext";
import Dialog from "../components/Dialog";
import InlineAlert from "../components/InlineAlert";
import { useToast } from "../components/FeedbackProvider";
import { responseErrorMessage } from "../format";
import PageHeader from "../components/PageHeader";

const EMPTY_WAREHOUSE = { warehouse_code: "", name: "", address: "" };

export default function Warehouses() {
  const { can } = useAuth();
  const toast = useToast();
  const [warehouses, setWarehouses] = useState([]);
  // null when the dialog is closed, otherwise the draft values.
  const [form, setForm] = useState(null);
  const [formError, setFormError] = useState(null);
  const [saving, setSaving] = useState(false);

  const loadWarehouses = useCallback(async () => {
    try {
      const response = await authFetch("/warehouses?include_inactive=true&limit=500");
      const data = await response.json();
      if (response.ok) setWarehouses(data.data || []);
      else toast.error(responseErrorMessage(data, "Could not load warehouses."));
    } catch {
      toast.error("Could not load warehouses.");
    }
  }, [toast]);

  useEffect(() => { loadWarehouses(); }, [loadWarehouses]);

  const openAdd = () => { setFormError(null); setForm({ ...EMPTY_WAREHOUSE }); };
  const closeForm = () => { setForm(null); setFormError(null); };

  // Errors stay inside the dialog (the toast region is inert behind it) and
  // the dialog stays open so the operator's input is kept.
  const createWarehouse = async (event) => {
    event.preventDefault();
    if (!form?.warehouse_code.trim() || !form?.name.trim()) return;
    setSaving(true);
    setFormError(null);
    try {
      const response = await authFetch("/warehouses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setFormError(responseErrorMessage(data, "Could not create warehouse."));
        return;
      }
      closeForm();
      toast.success(`${data.name} is ready for outbound dispatches.`);
      loadWarehouses();
    } catch {
      setFormError("Could not reach the API.");
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
      const data = await response.json().catch(() => ({}));
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
  const set = (patch) => setForm(current => ({ ...current, ...patch }));

  return (
    <section>
      <PageHeader
        eyebrow="Administration"
        title="Warehouses"
        subtitle="Where stock is held"
        actions={canWrite && (
          <button className="btn btn-primary btn-sm" onClick={openAdd}>Add Warehouse</button>
        )}
      />

      <div className="table-container" tabIndex={0} role="region" aria-label="Warehouses">
        <table>
          <thead>
            <tr>
              <th>Code</th>
              <th>Warehouse</th>
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
                <td><span className="sku">{warehouse.warehouse_code}</span></td>
                <td style={{ fontWeight: 600 }}>{warehouse.name}</td>
                <td className="muted">{warehouse.address || "—"}</td>
                <td>
                  {warehouse.active
                    ? <span className="badge badge-success">Active</span>
                    : <span className="badge badge-neutral">Inactive</span>}
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

      <Dialog open={!!form} onClose={closeForm} title="New Warehouse" maxWidth={560}>
        {form && (
          <form onSubmit={createWarehouse}>
            <div className="form-grid">
              <div className="input-group">
                <label className="input-label" htmlFor="warehouse-code">Warehouse code *</label>
                <input
                  id="warehouse-code"
                  className="input mono"
                  placeholder="KL-01"
                  value={form.warehouse_code}
                  onChange={e => set({ warehouse_code: e.target.value.toUpperCase() })}
                  required
                />
                <span className="input-hint">Short code used on dispatch records.</span>
              </div>
              <div className="input-group">
                <label className="input-label" htmlFor="warehouse-name">Name *</label>
                <input
                  id="warehouse-name"
                  className="input"
                  placeholder="Kuala Lumpur Main"
                  value={form.name}
                  onChange={e => set({ name: e.target.value })}
                  required
                />
              </div>
              <div className="input-group" style={{ gridColumn: "1 / -1" }}>
                <label className="input-label" htmlFor="warehouse-address">Address</label>
                <input
                  id="warehouse-address"
                  className="input"
                  placeholder="Optional address or location note"
                  value={form.address}
                  onChange={e => set({ address: e.target.value })}
                />
              </div>
            </div>

            <InlineAlert onDismiss={() => setFormError(null)} style={{ marginTop: 20 }}>{formError}</InlineAlert>

            <div className="dialog-actions">
              <button type="button" className="btn btn-ghost btn-sm" onClick={closeForm}>Cancel</button>
              <button
                className="btn btn-primary btn-sm"
                type="submit"
                disabled={saving || !form.warehouse_code.trim() || !form.name.trim()}
              >
                {saving ? "Saving..." : "Add Warehouse"}
              </button>
            </div>
          </form>
        )}
      </Dialog>
    </section>
  );
}
