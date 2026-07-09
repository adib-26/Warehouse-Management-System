import { useEffect, useState } from "react";

const API = "http://localhost:8000";

function Dialog({ open, onClose, title, children }) {
  if (!open) return null;
  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 560 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h2 style={{ margin: 0, fontSize: "1.1rem" }}>{title}</h2>
          <button onClick={onClose} className="btn-ghost btn btn-sm" style={{ padding: "4px 8px", fontSize: 16 }}>✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export default function Products() {
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
    fetch(`${API}/products?${getParams()}`).then((r) => r.json()).then(setItems).catch(() => {});
  };

  useEffect(() => { load(); }, []);

  const showDialog = (title, body, variant = "success") => {
    setDialog({ title, body, variant });
  };

  const addProduct = async (event) => {
    event.preventDefault();
    try {
      const res = await fetch(`${API}/products`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newProduct),
      });
      const data = await res.json();
      if (data.status === "created") {
        setNewProduct({ name: "", sku: "", category: "", tags: "", quantity: 0, description: "", low_stock: 10 });
        await load();
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
      const res = await fetch(`${API}/products/${editingProduct.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editingProduct),
      });
      if (res.ok) {
        setEditingProduct(null);
        await load();
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
    if (!confirm(`Delete "${name}"? This will archive the product.`)) return;
    try {
      await fetch(`${API}/products/${id}`, { method: "DELETE" });
      await load();
      showDialog("Product deleted", `${name} has been removed.`);
    } catch {
      showDialog("Error", "Could not delete product.", "error");
    }
  };

  const toggleArchive = async (id) => {
    try {
      await fetch(`${API}/products/${id}/archive`, { method: "PATCH" });
      await load();
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
      const res = await fetch(`${API}/products/bulk-upload`, { method: "POST", body: formData });
      const data = await res.json();
      showDialog(
        "Upload complete",
        `Imported ${data.imported} products.${data.total_errors > 0 ? ` ${data.total_errors} errors.` : ""}`
      );
      await load();
    } catch {
      showDialog("Upload failed", "Could not process the file.", "error");
    } finally {
      setUploading(false);
    }
  };

  const categories = [...new Set(items.map((p) => p.category).filter(Boolean))];
  const allTags = [...new Set(items.flatMap((p) => p.tags ? p.tags.split(",").map((t) => t.trim()) : []))].filter(Boolean);

  return (
    <section>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "1.5rem" }}>Products</h1>
          <p className="muted" style={{ margin: "4px 0 0 0" }}>Manage your inventory</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <label className="btn btn-sm" style={{ cursor: "pointer" }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
            Upload CSV/XLSX
            <input type="file" accept=".csv,.xlsx" style={{ display: "none" }} onChange={(e) => handleFileUpload(e.target.files[0])} />
          </label>
        </div>
      </div>

      {uploading && (
        <div className="card" style={{ padding: 16, marginBottom: 16, textAlign: "center" }}>
          <p className="muted">Uploading and processing file...</p>
        </div>
      )}

      <div className="card" style={{ padding: 16, marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <input
            className="input"
            placeholder="Search name, SKU, or description..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
            style={{ flex: "1 1 200px", minWidth: 160 }}
          />
          <select className="select" value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} style={{ width: "auto", minWidth: 120 }}>
            <option value="">All categories</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          {allTags.length > 0 && (
            <select className="select" value={tagFilter} onChange={(e) => setTagFilter(e.target.value)} style={{ width: "auto", minWidth: 120 }}>
              <option value="">All tags</option>
              {allTags.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          )}
          <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: "0.875rem" }}>
            <input type="checkbox" checked={showLowStock} onChange={(e) => setShowLowStock(e.target.checked)} />
            Low stock only
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: "0.875rem" }}>
            <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
            Show archived
          </label>
          <button className="btn btn-sm" onClick={load}>Search</button>
        </div>
      </div>

      <form onSubmit={addProduct} className="card" style={{ padding: 16, marginBottom: 16 }}>
        <h2 style={{ margin: "0 0 12px 0", fontSize: "1rem" }}>Add New Product</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 10 }}>
          <div>
            <label className="muted" style={{ display: "block", marginBottom: 4, fontSize: "0.8rem" }}>Name *</label>
            <input className="input" placeholder="Product name" value={newProduct.name} onChange={(e) => setNewProduct({ ...newProduct, name: e.target.value })} required />
          </div>
          <div>
            <label className="muted" style={{ display: "block", marginBottom: 4, fontSize: "0.8rem" }}>SKU *</label>
            <input className="input" placeholder="ABC-123" value={newProduct.sku} onChange={(e) => setNewProduct({ ...newProduct, sku: e.target.value.toUpperCase() })} required />
          </div>
          <div>
            <label className="muted" style={{ display: "block", marginBottom: 4, fontSize: "0.8rem" }}>Category</label>
            <input className="input" placeholder="Category" value={newProduct.category} onChange={(e) => setNewProduct({ ...newProduct, category: e.target.value })} />
          </div>
          <div>
            <label className="muted" style={{ display: "block", marginBottom: 4, fontSize: "0.8rem" }}>Tags (comma separated)</label>
            <input className="input" placeholder="tag1, tag2" value={newProduct.tags} onChange={(e) => setNewProduct({ ...newProduct, tags: e.target.value })} />
          </div>
          <div>
            <label className="muted" style={{ display: "block", marginBottom: 4, fontSize: "0.8rem" }}>Quantity</label>
            <input className="input" type="number" min={0} value={newProduct.quantity} onChange={(e) => setNewProduct({ ...newProduct, quantity: Number(e.target.value) })} />
          </div>
          <div>
            <label className="muted" style={{ display: "block", marginBottom: 4, fontSize: "0.8rem" }}>Low Stock Threshold</label>
            <input className="input" type="number" min={0} value={newProduct.low_stock} onChange={(e) => setNewProduct({ ...newProduct, low_stock: Number(e.target.value) })} />
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <label className="muted" style={{ display: "block", marginBottom: 4, fontSize: "0.8rem" }}>Description</label>
            <input className="input" placeholder="Description (optional)" value={newProduct.description} onChange={(e) => setNewProduct({ ...newProduct, description: e.target.value })} />
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
          <button type="submit" className="btn btn-sm">Add Product</button>
        </div>
      </form>

      <div className="card" style={{ padding: 0, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 800 }}>
          <thead>
            <tr style={{ background: "color-mix(in srgb, var(--text-dark) 4%, transparent)" }}>
              <th style={thStyle}>Name</th>
              <th style={thStyle}>SKU</th>
              <th style={thStyle}>Category</th>
              <th style={thStyle}>Tags</th>
              <th style={thStyle}>Qty</th>
              <th style={thStyle}>Threshold</th>
              <th style={thStyle}>Status</th>
              <th style={{ ...thStyle, textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ padding: 32, textAlign: "center", color: "var(--muted)" }}>
                  No products found
                </td>
              </tr>
            ) : (
              items.map((p) => {
                const isLow = p.quantity <= p.low_stock;
                const tagList = p.tags ? p.tags.split(",").map((t) => t.trim()).filter(Boolean) : [];
                return (
                  <tr key={p.id} style={{ borderTop: "1px solid rgba(255,255,255,0.04)", opacity: p.archived ? 0.5 : 1 }}>
                    <td style={tdStyle}>
                      <div style={{ fontWeight: 600 }}>{p.name}</div>
                      {p.description && <div className="muted" style={{ fontSize: "0.8rem", marginTop: 2 }}>{p.description}</div>}
                    </td>
                    <td style={tdStyle}><code style={{ fontSize: "0.85rem" }}>{p.sku}</code></td>
                    <td style={tdStyle}>{p.category || "-"}</td>
                    <td style={tdStyle}>
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {tagList.map((t, i) => (
                          <span key={i} className="badge badge-info">{t}</span>
                        ))}
                        {tagList.length === 0 && <span className="muted" style={{ fontSize: "0.8rem" }}>-</span>}
                      </div>
                    </td>
                    <td style={{ ...tdStyle, fontWeight: 700, color: isLow ? "#ef4444" : "inherit" }}>{p.quantity}</td>
                    <td style={tdStyle}>{p.low_stock}</td>
                    <td style={tdStyle}>
                      {p.archived ? (
                        <span className="badge badge-warning">Archived</span>
                      ) : isLow ? (
                        <span className="badge badge-danger">Low stock</span>
                      ) : (
                        <span className="badge badge-success">In stock</span>
                      )}
                    </td>
                    <td style={{ ...tdStyle, textAlign: "right" }}>
                      <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                        <button className="btn btn-sm btn-ghost" onClick={() => setEditingProduct({ ...p })} title="Edit">✎</button>
                        <button className="btn btn-sm btn-ghost" onClick={() => toggleArchive(p.id)} title={p.archived ? "Unarchive" : "Archive"}>
                          {p.archived ? "↗" : "📦"}
                        </button>
                        <button className="btn btn-sm btn-ghost" style={{ color: "#ef4444" }} onClick={() => deleteProduct(p.id, p.name)} title="Delete">✕</button>
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
            <div style={{ display: "grid", gap: 12 }}>
              <div>
                <label className="muted" style={{ display: "block", marginBottom: 4 }}>Name</label>
                <input className="input" value={editingProduct.name} onChange={(e) => setEditingProduct({ ...editingProduct, name: e.target.value })} />
              </div>
              <div>
                <label className="muted" style={{ display: "block", marginBottom: 4 }}>SKU</label>
                <input className="input" value={editingProduct.sku} onChange={(e) => setEditingProduct({ ...editingProduct, sku: e.target.value })} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label className="muted" style={{ display: "block", marginBottom: 4 }}>Category</label>
                  <input className="input" value={editingProduct.category} onChange={(e) => setEditingProduct({ ...editingProduct, category: e.target.value })} />
                </div>
                <div>
                  <label className="muted" style={{ display: "block", marginBottom: 4 }}>Quantity</label>
                  <input className="input" type="number" value={editingProduct.quantity} onChange={(e) => setEditingProduct({ ...editingProduct, quantity: Number(e.target.value) })} />
                </div>
              </div>
              <div>
                <label className="muted" style={{ display: "block", marginBottom: 4 }}>Tags (comma separated)</label>
                <input className="input" value={editingProduct.tags} onChange={(e) => setEditingProduct({ ...editingProduct, tags: e.target.value })} />
              </div>
              <div>
                <label className="muted" style={{ display: "block", marginBottom: 4 }}>Low Stock Threshold</label>
                <input className="input" type="number" value={editingProduct.low_stock} onChange={(e) => setEditingProduct({ ...editingProduct, low_stock: Number(e.target.value) })} />
              </div>
              <div>
                <label className="muted" style={{ display: "block", marginBottom: 4 }}>Description</label>
                <input className="input" value={editingProduct.description} onChange={(e) => setEditingProduct({ ...editingProduct, description: e.target.value })} />
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
              <button className="btn btn-sm btn-ghost" onClick={() => setEditingProduct(null)}>Cancel</button>
              <button className="btn btn-sm" onClick={updateProduct}>Save Changes</button>
            </div>
          </div>
        )}
      </Dialog>

      <Dialog open={!!dialog} onClose={() => setDialog(null)} title={dialog?.variant === "error" ? "Error" : "Success"}>
        <p>{dialog?.body}</p>
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 16 }}>
          <button className="btn btn-sm" onClick={() => setDialog(null)}>OK</button>
        </div>
      </Dialog>
    </section>
  );
}

const thStyle = {
  textAlign: "left",
  padding: "12px 14px",
  fontSize: 13,
  color: "var(--muted)",
  fontWeight: 700,
  letterSpacing: "-0.01em",
  whiteSpace: "nowrap",
};

const tdStyle = {
  padding: "12px 14px",
  fontSize: 14,
};
