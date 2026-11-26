import { useCallback, useEffect, useState } from "react";
import { authFetch } from "../api";
import { useAuth } from "../AuthContext";
import PartyFormDialog, { EMPTY_PARTY } from "../components/PartyFormDialog";
import SearchField from "../components/SearchField";
import { useToast, useConfirm } from "../components/FeedbackProvider";
import { responseErrorMessage } from "../format";
import PageHeader from "../components/PageHeader";

const SEARCH_DEBOUNCE_MS = 300;

export default function Customers() {
  const { can } = useAuth();
  const toast = useToast();
  const confirm = useConfirm();
  const [customers, setCustomers] = useState([]);
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
    authFetch(`/customers${params}`).then(r => r.json()).then(d => setCustomers(d.data)).catch(() => {});
  }, [appliedQ]);

  useEffect(() => { load(); }, [load]);

  const openAdd = () => { setFormError(null); setForm({ mode: "add", values: { ...EMPTY_PARTY } }); };
  const openEdit = (customer) => { setFormError(null); setForm({ mode: "edit", values: { ...customer } }); };
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
      const res = await authFetch(isAdd ? "/customers" : `/customers/${values.id}`, {
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
        setFormError(responseErrorMessage(data, isAdd ? "Could not add customer." : "Could not update customer."));
      }
    } catch {
      setFormError("Could not reach the API.");
    } finally {
      setSubmitting(false);
    }
  };

  const deleteCustomer = async (id, name) => {
    const ok = await confirm({
      title: "Delete customer",
      message: `Delete "${name}"? This cannot be undone.`,
      confirmLabel: "Delete customer",
      tone: "danger",
    });
    if (!ok) return;
    try {
      const res = await authFetch(`/customers/${id}`, { method: "DELETE" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        toast.error(responseErrorMessage(data, "Could not delete customer."));
        return;
      }
      load();
      toast.success(`${name} has been removed.`);
    } catch {
      toast.error("Could not delete customer.");
    }
  };

  const canWrite = can("customers", "write");

  return (
    <section>
      <PageHeader
        eyebrow="Supply Chain"
        title="Customers"
        subtitle="Who you ship to"
        actions={canWrite && (
          <button className="btn btn-primary btn-sm" onClick={openAdd}>Add Customer</button>
        )}
      />

      <div className="toolbar" style={{ marginBottom: 16 }}>
        <SearchField
          value={q}
          onChange={setQ}
          label="Search customers"
          placeholder="Search name, contact, or email..."
        />
        <span className="muted toolbar__count" role="status">
          {customers.length} customer{customers.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="table-container" tabIndex={0} role="region" aria-label="Customers">
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
                    <div className="cell-strong">{c.name}</div>
                    {c.notes && <div className="cell-sub">{c.notes}</div>}
                  </td>
                  <td className="cell-quiet cell-nowrap">{c.contact_person || "—"}</td>
                  <td className="cell-quiet cell-nowrap">{c.email || "—"}</td>
                  <td className="cell-quiet cell-nowrap mono" style={{ fontSize: "0.8rem" }}>{c.phone || "—"}</td>
                  <td className="cell-quiet cell-clip">{c.address || "—"}</td>
                  <td style={{ textAlign: "right" }}>
                    <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                      {canWrite && (
                        <button className="btn btn-ghost btn-xs" onClick={() => openEdit(c)}>Edit</button>
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

      <PartyFormDialog
        form={form}
        noun="Customer"
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
