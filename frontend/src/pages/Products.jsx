import { useEffect, useState } from "react";
import { authFetch } from "../api";
import { useAuth } from "../AuthContext";

function Dialog({ open, onClose, title, children }) {
  if (!open) return null;
  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 560 }}>
        <div className="dialog-header">
          <h2 className="dialog-title">{title}</h2>
          <button onClick={onClose} className="btn btn-ghost btn-xs" style={{ padding: "4px 8px", fontSize: 18 }}>&times;</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export default function Products() {
  const { can } = useAuth();
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [showLowStock, setShowLowStock] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [newProduct, setNewProduct] = useState({ name: "", sku: "", category: "", tags: "", quantity: 0, description: "", low_stock: 10 });
  const [editingProduct, setEditingProduct] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);

  const getParams = () => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (categoryFilter) params.set("category", categoryFilter);
    if (tagFilter) params.set("tag", tagFilter);
    if (showLowStock) params.set("low_stock", "true");
    if (showArchived) params.set("archived", "true");
    return params;
  };

  const load = () => {
    authFetch(`/products?${getParams()}`).then(r => r.json()).then(setItems).catch(() => {});
  };

  useEffect(() => { load(); }, []);

  const showDialog = (title, body, variant = "success") => setDialog({ title, body, variant });

  const addProduct = async (e) => {
    e.preventDefault();
    try {
      const res = await authFetch(`/products`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newProduct),
      });
      const data = await res.json();
      if (data.status === "created") {
        setNewProduct({ name: "", sku: "", category: "", tags: "", quantity: 0, description: "", low_stock: 10 });
        setShowAddForm(false);
        load();
        showDialog("Product added", `${newProduct.name} (${newProduct.sku}) has been created.`);
      } else {
        showDialog("Error", data.detail || "Could not add product.", "error");
      }
    } catch {
      showDialog("Network error", "Could not reach the API.", "error");
    }
  };

  const updateProduct = async () => {
    if (!editingProduct) return;
    try {
      const res = await authFetch(`/products/${editingProduct.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editingProduct),
      });
      if (res.ok) {
        setEditingProduct(null);
        load();
        showDialog("Product updated", "Changes saved successfully.");
      } else {
        const data = await res.json();
        showDialog("Error", data.detail || "Could not update.", "error");
      }
    } catch {
      showDialog("Network error", "Could not reach the API.", "error");
    }
  };

  const deleteProduct = async (id, name) => {
    if (!confirm(`Delete "${name}"?`)) return;
    try {
      await authFetch(`/products/${id}`, { method: "DELETE" });
      load();
      showDialog("Product deleted", `${name} has been removed.`);
    } catch {
      showDialog("Error", "Could not delete product.", "error");
    }
  };

  const toggleArchive = async (id) => {
    try {
      await authFetch(`/products/${id}/archive`, { method: "PATCH" });
      load();
    } catch {
      showDialog("Error", "Could not toggle archive status.", "error");
    }
  };

  const handleFileUpload = async (file) => {
    if (!file) return;
    const ext = file.name.split(".").pop().toLowerCase();
    if (!["csv", "xlsx"].includes(ext)) {
      showDialog("Invalid file", "Please upload a CSV or XLSX file.", "error");
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await authFetch(`/products/bulk-upload`, { method: "POST", body: formData });
      const data = await res.json();
      showDialog(
        "Upload complete",
        `Imported ${data.imported} products.${data.total_errors > 0 ? ` ${data.total_errors} errors.` : ""}`
      );
      load();
    } catch {
      showDialog("Upload failed", "Could not process the file.", "error");
    } finally {
      setUploading(false);
    }
  };

  const categories = [...new Set(items.map(p => p.category).filter(Boolean))];
  const allTags = [...new Set(items.flatMap(p => p.tags ? p.tags.split(",").map(t => t.trim()) : []))].filter(Boolean);

  return (
    <section>
      <div className="page-header">
        <div>
          <h1 className="page-title">Products</h1>
          <p className="page-subtitle">Manage your inventory catalog</p>
        </div>
        {can("products", "write") && (
          <div style={{ display: "flex", gap: 8 }}>
            <label className="btn btn-secondary btn-sm" style={{ cursor: "pointer" }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
              Upload CSV/XLSX
              <input type="file" accept=".csv,.xlsx" style={{ display: "none" }} onChange={e => handleFileUpload(e.target.files[0])} />
            </label>
            <button className="btn btn-primary btn-sm" onClick={() => setShowAddForm(!showAddForm)}>
              {showAddForm ? "Cancel" : "+ Add Product"}
            </button>
          </div>
        )}
      </div>

      {uploading && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-body" style={{ display: "flex", alignItems: "center", gap: 12, justifyContent: "center" }}>
            <div className="spinner" />
            <span className="muted">Processing file...</span>
          </div>
        </div>
      )}

      {showAddForm && (
        <form onSubmit={addProduct} className="card" style={{ marginBottom: 20 }}>
          <div className="card-body">
            <h3 className="section-title">New Product</h3>
            <div className="form-grid">
              <div className="input-group">
                <label className="input-label">Name *</label>
                <input className="input" placeholder="Product name" value={newProduct.name} onChange={e => setNewProduct({ ...newProduct, name: e.target.value })} required />
              </div>
              <div className="input-group">
                <label className="input-label">SKU *</label>
                <input className="input" placeholder="ABC-123" value={newProduct.sku} onChange={e => setNewProduct({ ...newProduct, sku: e.target.value.toUpperCase() })} required />
              </div>
              <div className="input-group">
                <label className="input-label">Category</label>
                <input className="input" placeholder="Category" value={newProduct.category} onChange={e => setNewProduct({ ...newProduct, category: e.target.value })} />
              </div>
              <div className="input-group">
                <label className="input-label">Tags (comma separated)</label>
                <input className="input" placeholder="tag1, tag2" value={newProduct.tags} onChange={e => setNewProduct({ ...newProduct, tags: e.target.value })} />
              </div>
              <div className="input-group">
                <label className="input-label">Quantity</label>
                <input className="input" type="number" min={0} value={newProduct.quantity} onChange={e => setNewProduct({ ...newProduct, quantity: Number(e.target.value) })} />
              </div>
              <div className="input-group">
                <label className="input-label">Low Stock Threshold</label>
                <input className="input" type="number" min={0} value={newProduct.low_stock} onChange={e => setNewProduct({ ...newProduct, low_stock: Number(e.target.value) })} />
              </div>
              <div className="input-group" style={{ gridColumn: "1 / -1" }}>
                <label className="input-label">Description</label>
                <input className="input" placeholder="Product description" value={newProduct.description} onChange={e => setNewProduct({ ...newProduct, description: e.target.value })} />
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 16 }}>
              <button type="submit" className="btn btn-primary btn-sm">Add Product</button>
            </div>
          </div>
        </form>
      )}

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-body" style={{ paddingBottom: 12 }}>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <input
              className="input"
              placeholder="Search name, SKU, or description..."
              value={q}
              onChange={e => setQ(e.target.value)}
              onKeyDown={e => e.key === "Enter" && load()}
              style={{ flex: "1 1 200px", maxWidth: 360 }}
            />
            <select className="select" value={categoryFilter} onChange={e => setCategoryFilter(e.target.value)} style={{ width: "auto", minWidth: 140 }}>
              <option value="">All categories</option>
              {categories.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            {allTags.length > 0 && (
              <select className="select" value={tagFilter} onChange={e => setTagFilter(e.target.value)} style={{ width: "auto", minWidth: 140 }}>
                <option value="">All tags</option>
                {allTags.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            )}
            <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
              <input type="checkbox" checked={showLowStock} onChange={e => setShowLowStock(e.target.checked)} style={{ accentColor: "var(--accent)" }} />
              Low stock
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
              <input type="checkbox" checked={showArchived} onChange={e => setShowArchived(e.target.checked)} style={{ accentColor: "var(--accent)" }} />
              Archived
            </label>
            <button className="btn btn-secondary btn-sm" onClick={load}>Search</button>
            <span className="muted" style={{ marginLeft: "auto" }}>{items.length} product{items.length !== 1 ? "s" : ""}</span>
          </div>
        </div>
      </div>

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Product</th>
              <th>SKU</th>
              <th>Category</th>
              <th>Tags</th>
              <th>Qty</th>
              <th>Threshold</th>
              <th>Status</th>
              <th style={{ textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={8} className="empty-state">
                  <div className="empty-state-text">No products found</div>
                </td>
              </tr>
            ) : (
              items.map(p => {
                const isLow = p.quantity <= p.low_stock;
                const tagList = p.tags ? p.tags.split(",").map(t => t.trim()).filter(Boolean) : [];
                return (
                  <tr key={p.id} style={{ opacity: p.archived ? 0.5 : 1 }}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{p.name}</div>
                      {p.description && <div className="muted" style={{ fontSize: "0.8rem", marginTop: 2, maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.description}</div>}
                    </td>
                    <td><code style={{ fontSize: "0.8125rem", background: "var(--bg-surface-elevated)", padding: "2px 6px", borderRadius: 4 }}>{p.sku}</code></td>
                    <td style={{ color: "var(--text-secondary)" }}>{p.category || "-"}</td>
                    <td>
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {tagList.map((t, i) => (
                          <span key={i} className="badge badge-info">{t}</span>
                        ))}
                        {tagList.length === 0 && <span className="muted" style={{ fontSize: "0.8rem" }}>-</span>}
                      </div>
                    </td>
                    <td style={{ fontWeight: 700, color: isLow ? "var(--red)" : "var(--text-primary)" }}>{p.quantity}</td>
                    <td style={{ color: "var(--text-secondary)" }}>{p.low_stock}</td>
                    <td>
                      {p.archived ? (
                        <span className="badge badge-warning">Archived</span>
                      ) : isLow ? (
                        <span className="badge badge-danger">Low stock</span>
                      ) : (
                        <span className="badge badge-success">In stock</span>
                      )}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                        {can("products", "write") && (
                          <>
                            <button className="btn btn-ghost btn-xs" onClick={() => setEditingProduct({ ...p })}>Edit</button>
                            <button className="btn btn-ghost btn-xs" onClick={() => toggleArchive(p.id)}>{p.archived ? "Unarchive" : "Archive"}</button>
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

      <Dialog open={!!editingProduct} onClose={() => setEditingProduct(null)} title="Edit Product">
        {editingProduct && (
          <div>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="input-group">
                <label className="input-label">Name</label>
                <input className="input" value={editingProduct.name} onChange={e => setEditingProduct({ ...editingProduct, name: e.target.value })} />
              </div>
              <div className="input-group">
                <label className="input-label">SKU</label>
                <input className="input" value={editingProduct.sku} onChange={e => setEditingProduct({ ...editingProduct, sku: e.target.value })} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div className="input-group">
                  <label className="input-label">Category</label>
                  <input className="input" value={editingProduct.category} onChange={e => setEditingProduct({ ...editingProduct, category: e.target.value })} />
                </div>
                <div className="input-group">
                  <label className="input-label">Quantity</label>
                  <input className="input" type="number" value={editingProduct.quantity} onChange={e => setEditingProduct({ ...editingProduct, quantity: Number(e.target.value) })} />
                </div>
              </div>
              <div className="input-group">
                <label className="input-label">Tags</label>
                <input className="input" value={editingProduct.tags} onChange={e => setEditingProduct({ ...editingProduct, tags: e.target.value })} />
              </div>
              <div className="input-group">
                <label className="input-label">Low Stock Threshold</label>
                <input className="input" type="number" value={editingProduct.low_stock} onChange={e => setEditingProduct({ ...editingProduct, low_stock: Number(e.target.value) })} />
              </div>
              <div className="input-group">
                <label className="input-label">Description</label>
                <textarea className="input textarea" value={editingProduct.description} onChange={e => setEditingProduct({ ...editingProduct, description: e.target.value })} />
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => setEditingProduct(null)}>Cancel</button>
              <button className="btn btn-primary btn-sm" onClick={updateProduct}>Save Changes</button>
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
