import { useCallback, useEffect, useState } from "react";
import { authFetch } from "../api";
import { useAuth } from "../AuthContext";
import PartyFormDialog, { EMPTY_PARTY } from "../components/PartyFormDialog";
import SearchField from "../components/SearchField";
import { useToast, useConfirm } from "../components/FeedbackProvider";
import { responseErrorMessage } from "../format";
import PageHeader from "../components/PageHeader";

const SEARCH_DEBOUNCE_MS = 300;

export default function Suppliers() {
  const { can } = useAuth();
  const toast = useToast();
  const confirm = useConfirm();
  const [suppliers, setSuppliers] = useState([]);
  const [q, setQ] = useState("");
  // The list refetches as the query settles, so there is no Search button.
  const [appliedQ, setAppliedQ] = useState("");
  // null when the dialog is closed, otherwise { mode, values }.
  const [form, setForm] = useState(null);
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setAppliedQ(q), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [q]);

  const load = useCallback(() => {
    const params = appliedQ ? `?q=${encodeURIComponent(appliedQ)}` : "";
    authFetch(`/suppliers${params}`).then(r => r.json()).then(d => setSuppliers(d.data)).catch(() => {});
  }, [appliedQ]);

  useEffect(() => { load(); }, [load]);

  const openAdd = () => { setFormError(null); setForm({ mode: "add", values: { ...EMPTY_PARTY } }); };
  const openEdit = (supplier) => { setFormError(null); setForm({ mode: "edit", values: { ...supplier } }); };
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
    try {
      const res = await authFetch(isAdd ? "/suppliers" : `/suppliers/${values.id}`, {
        method: isAdd ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      if (isAdd ? res.status === 201 : res.ok) {
        closeForm();
        load();
        toast.success(isAdd ? `${values.name} has been created.` : "Changes saved.");
      } else {
        const data = await res.json().catch(() => ({}));
        setFormError(responseErrorMessage(data, isAdd ? "Could not add supplier." : "Could not update supplier."));
      }
    } catch {
      setFormError("Could not reach the API.");
    } finally {
      setSubmitting(false);
    }
  };

  const deleteSupplier = async (id, name) => {
    const ok = await confirm({
      title: "Delete supplier",
      message: `Delete "${name}"? This cannot be undone.`,
      confirmLabel: "Delete supplier",
      tone: "danger",
    });
    if (!ok) return;
    try {
      const res = await authFetch(`/suppliers/${id}`, { method: "DELETE" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        toast.error(responseErrorMessage(data, "Could not delete supplier."));
        return;
      }
      load();
      toast.success(`${name} has been removed.`);
    } catch {
      toast.error("Could not delete supplier.");
    }
  };

  const canWrite = can("suppliers", "write");

  return (
    <section>
      <PageHeader
        eyebrow="Supply Chain"
        title="Suppliers"
        subtitle="Who you buy from"
        actions={canWrite && (
          <button className="btn btn-primary btn-sm" onClick={openAdd}>Add Supplier</button>
        )}
      />

      <div className="toolbar" style={{ marginBottom: 16 }}>
        <SearchField
          value={q}
          onChange={setQ}
          label="Search suppliers"
          placeholder="Search name, contact, or email..."
        />
        <span className="muted toolbar__count" role="status">
          {suppliers.length} supplier{suppliers.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="table-container" tabIndex={0} role="region" aria-label="Suppliers">
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
            {suppliers.length === 0 ? (
              <tr>
                <td colSpan={6} className="empty-state">
                  <div className="empty-state-text">No suppliers found</div>
                </td>
              </tr>
            ) : (
              suppliers.map(s => (
                <tr key={s.id}>
                  <td>
                    <div className="cell-strong">{s.name}</div>
                    {s.notes && <div className="cell-sub">{s.notes}</div>}
                  </td>
                  <td className="cell-quiet cell-nowrap">{s.contact_person || "—"}</td>
                  <td className="cell-quiet cell-nowrap">{s.email || "—"}</td>
                  <td className="cell-quiet cell-nowrap mono" style={{ fontSize: "0.8rem" }}>{s.phone || "—"}</td>
                  <td className="cell-quiet cell-clip">{s.address || "—"}</td>
                  <td style={{ textAlign: "right" }}>
                    <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                      {canWrite && (
                        <button className="btn btn-ghost btn-xs" onClick={() => openEdit(s)}>Edit</button>
                      )}
                      {can("suppliers", "delete") && (
                        <button className="btn btn-danger btn-xs" onClick={() => deleteSupplier(s.id, s.name)}>Delete</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <PartyFormDialog
        form={form}
        noun="Supplier"
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
