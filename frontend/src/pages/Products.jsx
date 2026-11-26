import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { authFetch } from "../api";
import { useAuth } from "../AuthContext";
import Dialog from "../components/Dialog";
import InlineAlert from "../components/InlineAlert";
import SearchField from "../components/SearchField";
import { useToast, useConfirm } from "../components/FeedbackProvider";
import { formatQuantity, responseErrorMessage } from "../format";
import PageHeader from "../components/PageHeader";

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 300;

const EMPTY_PRODUCT = {
  name: "",
  sku: "",
  category: "",
  tags: "",
  quantity: 0,
  description: "",
  low_stock: 10,
};


/**
 * One form for both creating and editing. `mode` drives the two differences:
 * new SKUs are upper-cased as they are typed, and a batch-tracked product's
 * quantity is read-only because it is derived from its inventory batches.
 */
function ProductFormDialog({ form, onClose, onChange, onSubmit, submitting, error, onDismissError }) {
  const open = !!form;
  const values = form?.values ?? EMPTY_PRODUCT;
  const isAdd = form?.mode === "add";
  const batchTracked = !isAdd && !!values.batch_tracking_enabled_at;
  const set = (patch) => onChange({ ...values, ...patch });

  return (
    <Dialog open={open} onClose={onClose} title={isAdd ? "New Product" : "Edit Product"} maxWidth={620}>
      <form onSubmit={onSubmit}>
        <div className="form-grid">
          <div className="input-group" style={{ gridColumn: "1 / -1" }}>
            <label className="input-label" htmlFor="product-name">Name *</label>
            <input
              id="product-name"
              className="input"
              placeholder="Product name"
              value={values.name}
              onChange={e => set({ name: e.target.value })}
              required
            />
          </div>
          <div className="input-group">
            <label className="input-label" htmlFor="product-sku">SKU *</label>
            <input
              id="product-sku"
              className="input mono"
              placeholder="ABC-123"
              value={values.sku}
              onChange={e => set({ sku: isAdd ? e.target.value.toUpperCase() : e.target.value })}
              required
            />
          </div>
          <div className="input-group">
            <label className="input-label" htmlFor="product-category">Category</label>
            <input
              id="product-category"
              className="input"
              placeholder="Category"
              value={values.category || ""}
              onChange={e => set({ category: e.target.value })}
            />
          </div>
          <div className="input-group">
            <label className="input-label" htmlFor="product-quantity">On hand</label>
            <input
              id="product-quantity"
              className="input mono"
              type="number"
              min={0}
              step="0.01"
              value={values.quantity}
              disabled={batchTracked}
              onChange={e => set({ quantity: Number(e.target.value) })}
            />
            {batchTracked && (
              <span className="input-hint">Batch-tracked stock is updated through inventory batches.</span>
            )}
          </div>
          <div className="input-group">
            <label className="input-label" htmlFor="product-min">Min (low-stock level)</label>
            <input
              id="product-min"
              className="input mono"
              type="number"
              min={0}
              step="0.01"
              value={values.low_stock}
              onChange={e => set({ low_stock: Number(e.target.value) })}
            />
          </div>
          <div className="input-group" style={{ gridColumn: "1 / -1" }}>
            <label className="input-label" htmlFor="product-tags">Tags</label>
            <input
              id="product-tags"
              className="input"
              placeholder="tag1, tag2"
              value={values.tags || ""}
              onChange={e => set({ tags: e.target.value })}
            />
            <span className="input-hint">Comma separated.</span>
          </div>
          <div className="input-group" style={{ gridColumn: "1 / -1" }}>
            <label className="input-label" htmlFor="product-description">Description</label>
            <textarea
              id="product-description"
              className="input textarea"
              placeholder="Product description"
              value={values.description || ""}
              onChange={e => set({ description: e.target.value })}
            />
          </div>
        </div>
        <InlineAlert onDismiss={onDismissError} style={{ marginTop: 20 }}>{error}</InlineAlert>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 22 }}>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary btn-sm" disabled={submitting}>
            {submitting ? "Saving..." : isAdd ? "Add Product" : "Save Changes"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

export default function Products() {
  const { can } = useAuth();
  const toast = useToast();
  const confirm = useConfirm();
  const [searchParams] = useSearchParams();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [facets, setFacets] = useState({ categories: [], tags: [] });
  const [q, setQ] = useState("");
  // The list refetches as the query settles, so there is no Search button.
  const [appliedQ, setAppliedQ] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [showLowStock, setShowLowStock] = useState(() => searchParams.get("low_stock") === "true");
  const [showArchived, setShowArchived] = useState(() => searchParams.get("archived") === "true");
  const [form, setForm] = useState(null);
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setAppliedQ(q);
      setOffset(0);
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [q]);

  const getParams = useCallback(() => {
    const params = new URLSearchParams();
    if (appliedQ) params.set("q", appliedQ);
    if (categoryFilter) params.set("category", categoryFilter);
    if (tagFilter) params.set("tag", tagFilter);
    if (showLowStock) params.set("low_stock", "true");
    if (showArchived) params.set("archived", "true");
    return params;
  }, [appliedQ, categoryFilter, showArchived, showLowStock, tagFilter]);

  const load = useCallback(() => {
    const params = getParams();
    params.set("limit", String(PAGE_SIZE));
    params.set("offset", String(offset));
    authFetch(`/products?${params}`).then(r => r.json()).then(d => {
      setItems(d.data);
      setTotal(d.meta.total);
    }).catch(() => {});
  }, [getParams, offset]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    authFetch("/products/facets").then(r => r.json()).then(setFacets).catch(() => {});
  }, []);

  const openAdd = () => { setFormError(null); setForm({ mode: "add", values: { ...EMPTY_PRODUCT } }); };
  const openEdit = (product) => { setFormError(null); setForm({ mode: "edit", values: { ...product } }); };
  const closeForm = () => { setForm(null); setFormError(null); };

  // Errors stay inside the dialog (the toast region is inert behind it) and
  // the dialog stays open so the operator's input is kept.
  const submitForm = async (event) => {
    event.preventDefault();
    if (!form) return;
    setSubmitting(true);
    setFormError(null);
    const values = form.values;
    try {
      if (form.mode === "add") {
        const res = await authFetch(`/products`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(values),
        });
        const data = await res.json();
        if (res.status === 201) {
          closeForm();
          load();
          toast.success(`${values.name} (${values.sku}) has been created.`);
        } else {
          setFormError(responseErrorMessage(data, "Could not add product."));
        }
      } else {
        const res = await authFetch(`/products/${values.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: values.name,
            sku: values.sku,
            description: values.description,
            category: values.category,
            tags: values.tags,
            low_stock: values.low_stock,
            archived: values.archived,
            // Omitted for batch-tracked products: the balance is derived.
            ...(values.batch_tracking_enabled_at ? {} : { quantity: values.quantity }),
          }),
        });
        if (res.ok) {
          closeForm();
          load();
          toast.success("Changes saved.");
        } else {
          const data = await res.json();
          setFormError(responseErrorMessage(data, "Could not update product."));
        }
      }
    } catch {
      setFormError("Could not reach the API.");
    } finally {
      setSubmitting(false);
    }
  };

  const deleteProduct = async (id, name) => {
    const ok = await confirm({
      title: "Delete product",
      message: `Delete "${name}"? This cannot be undone.`,
      confirmLabel: "Delete product",
      tone: "danger",
    });
    if (!ok) return;
    try {
      const res = await authFetch(`/products/${id}`, { method: "DELETE" });
      if (!res.ok) {
        const data = await res.json();
        toast.error(responseErrorMessage(data, "Could not delete product."));
        return;
      }
      load();
      toast.success(`${name} has been removed.`);
    } catch {
      toast.error("Could not delete product.");
    }
  };

  const toggleArchive = async (product) => {
    try {
      const res = await authFetch(`/products/${product.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: !product.archived }),
      });
      if (!res.ok) {
        const data = await res.json();
        toast.error(responseErrorMessage(data, "Could not change archive status."));
        return;
      }
      load();
      toast.success(`${product.name} was ${product.archived ? "restored" : "archived"}.`);
    } catch {
      toast.error("Could not change archive status.");
    }
  };

  const handleFileUpload = async (event) => {
    const file = event.currentTarget.files?.[0];
    // Let an operator fix and re-pick the same file after a validation error.
    event.currentTarget.value = "";
    if (!file) return;
    const ext = file.name.split(".").pop().toLowerCase();
    if (!["csv", "xlsx"].includes(ext)) {
      toast.error("Please upload a CSV or XLSX file.");
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await authFetch(`/products/imports`, { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) {
        toast.error(responseErrorMessage(data, "Could not import the file."));
        return;
      }
      const errors = Number(data.total_errors) || 0;
      const message = `Imported ${data.imported} products.${errors > 0 ? ` ${errors} row${errors === 1 ? "" : "s"} rejected.` : ""}`;
      if (errors > 0) toast.warning(message);
      else toast.success(message);
      load();
    } catch {
      toast.error("Could not process the file.");
    } finally {
      setUploading(false);
    }
  };

  const exportProducts = async () => {
    try {
      const res = await authFetch(`/products/export?${getParams()}`);
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        toast.error(responseErrorMessage(data, "Could not export products."));
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "products.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Could not reach the API.");
    }
  };

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const canWrite = can("products", "write");

  return (
    <section>
      <PageHeader
        eyebrow="Inventory"
        title="Products"
        subtitle="What you stock, and how much of it"
        actions={
          <>
            <button className="btn btn-secondary btn-sm" onClick={exportProducts}>Export CSV</button>
            {canWrite && (
              <>
                <label className="btn btn-secondary btn-sm" style={{ cursor: "pointer" }}>
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" />
                  </svg>
                  Import
                  <input className="file-input" type="file" accept=".csv,.xlsx" onChange={handleFileUpload} />
                </label>
                <button className="btn btn-primary btn-sm" onClick={openAdd}>Add Product</button>
              </>
            )}
          </>
        }
      />

      {uploading && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-body" style={{ display: "flex", alignItems: "center", gap: 12, justifyContent: "center" }}>
            <div className="spinner" />
            <span className="muted">Processing file...</span>
          </div>
        </div>
      )}

      <div className="toolbar" style={{ marginBottom: 16 }}>
        <SearchField
          value={q}
          onChange={setQ}
          label="Search products"
          placeholder="Search name, SKU, or description..."
        />

        <select
          className="select"
          aria-label="Filter by category"
          value={categoryFilter}
          onChange={e => { setCategoryFilter(e.target.value); setOffset(0); }}
          style={{ width: "auto", minWidth: 150 }}
        >
          <option value="">All categories</option>
          {facets.categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>

        {facets.tags.length > 0 && (
          <select
            className="select"
            aria-label="Filter by tag"
            value={tagFilter}
            onChange={e => { setTagFilter(e.target.value); setOffset(0); }}
            style={{ width: "auto", minWidth: 130 }}
          >
            <option value="">All tags</option>
            {facets.tags.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        )}

        <label className="chip">
          <input
            className="chip__input"
            type="checkbox"
            checked={showLowStock}
            onChange={e => { setShowLowStock(e.target.checked); setOffset(0); }}
          />
          Low stock
        </label>
        <label className="chip">
          <input
            className="chip__input"
            type="checkbox"
            checked={showArchived}
            onChange={e => { setShowArchived(e.target.checked); setOffset(0); }}
          />
          Archived
        </label>

        <span className="muted toolbar__count" role="status">
          {total} product{total !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="table-container" tabIndex={0} role="region" aria-label="Products">
        <table>
          <thead>
            <tr>
              <th>Product</th>
              <th>SKU</th>
              <th>Category</th>
              <th>Tags</th>
              <th style={{ textAlign: "right" }}>On hand</th>
              <th style={{ textAlign: "right" }}>Min</th>
              <th>Status</th>
              <th style={{ textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={8} className="empty-state">
                  <div className="empty-state-text">No products match these filters</div>
                </td>
              </tr>
            ) : (
              items.map(p => {
                const quantity = Number(p.quantity);
                const threshold = Number(p.low_stock);
                const isLow = quantity <= threshold;
                const tagList = p.tags ? p.tags.split(",").map(t => t.trim()).filter(Boolean) : [];
                return (
                  <tr key={p.id} style={{ opacity: p.archived ? 0.55 : 1 }}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{p.name}</div>
                      {p.description && (
                        <div className="muted" style={{ fontSize: "0.78rem", marginTop: 2, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {p.description}
                        </div>
                      )}
                    </td>
                    <td><span className="sku">{p.sku}</span></td>
                    <td style={{ color: "var(--text-secondary)" }}>{p.category || "—"}</td>
                    <td>
                      {tagList.length === 0 ? (
                        <span className="muted">—</span>
                      ) : (
                        <ul className="tag-list">
                          {tagList.map(t => <li key={t} className="tag">{t}</li>)}
                        </ul>
                      )}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <span className={`ledger-num${isLow ? " ledger-num--down" : ""}`}>{formatQuantity(quantity)}</span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <span className="mono muted" style={{ fontVariantNumeric: "tabular-nums" }}>{formatQuantity(threshold)}</span>
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                        {p.archived ? (
                          <span className="stamp stamp--archived">Archived</span>
                        ) : isLow ? (
                          <span className="stamp stamp--low">Low</span>
                        ) : (
                          <span className="stamp stamp--ok">In stock</span>
                        )}
                        {p.batch_tracking_enabled_at && <span className="stamp stamp--batch">Batch</span>}
                      </div>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                        {canWrite && (
                          <>
                            <button className="btn btn-ghost btn-xs" onClick={() => openEdit(p)}>Edit</button>
                            <button className="btn btn-ghost btn-xs" onClick={() => toggleArchive(p)}>
                              {p.archived ? "Restore" : "Archive"}
                            </button>
                          </>
                        )}
                        {can("products", "delete") && (
                          <button className="btn btn-danger btn-xs" onClick={() => deleteProduct(p.id, p.name)}>Delete</button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="pagination">
        <span className="muted">
          {total === 0
            ? "No products"
            : `Showing ${offset + 1}–${Math.min(offset + items.length, total)} of ${total}`}
        </span>
        <div className="pagination__controls">
          <button
            className="btn btn-secondary btn-sm"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </button>
          <span className="pagination__page">Page {page} of {pageCount}</span>
          <button
            className="btn btn-secondary btn-sm"
            disabled={offset + items.length >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      </div>

      <ProductFormDialog
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
