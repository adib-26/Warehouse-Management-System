import { useEffect, useState, useRef } from "react";
import { authFetch, downloadAttachment as apiDownloadAttachment } from "../api";
import { useAuth } from "../AuthContext";

function Dialog({ open, onClose, title, children }) {
  if (!open) return null;
  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 640 }}>
        <div className="dialog-header">
          <h2 className="dialog-title">{title}</h2>
          <button onClick={onClose} className="btn btn-ghost btn-xs" style={{ padding: "4px 8px", fontSize: 18 }}>&times;</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export default function Inbound() {
  const { can } = useAuth();
  const [products, setProducts] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [shipments, setShipments] = useState([]);
  const [form, setForm] = useState({
    product_id: "",
    supplier_id: "",
    quantity: 1,
    invoice_ref: "",
    received_date: new Date().toISOString().split("T")[0],
    notes: "",
  });
  const [message, setMessage] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [detailShipment, setDetailShipment] = useState(null);
  const [attachments, setAttachments] = useState([]);
  const [uploadFile, setUploadFile] = useState(null);
  const fileInputRef = useRef(null);
  const dropRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  const loadData = () => {
    authFetch(`/products?limit=500`).then(r => r.json()).then(d => setProducts(d.data)).catch(() => {});
    authFetch(`/suppliers?limit=500`).then(r => r.json()).then(d => setSuppliers(d.data)).catch(() => {});
    authFetch(`/inbound-shipments?limit=100`).then(r => r.json()).then(d => setShipments(d.data)).catch(() => {});
  };

  useEffect(() => { loadData(); }, []);

  const logInbound = async (e) => {
    e.preventDefault();
    if (!form.product_id || !form.supplier_id || form.quantity <= 0) return;
    try {
      const res = await authFetch(`/inbound-shipments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, product_id: Number(form.product_id), supplier_id: Number(form.supplier_id), quantity: Number(form.quantity) }),
      });
      const data = await res.json();
      if (res.status === 201) {
        setMessage({ type: "success", text: `${data.quantity}x ${data.product_name} received from ${data.supplier_name}. New stock: ${data.quantity_after}` });
        setForm({ product_id: "", supplier_id: "", quantity: 1, invoice_ref: "", received_date: new Date().toISOString().split("T")[0], notes: "" });
        loadData();
      } else {
        setMessage({ type: "error", text: data.detail || "Failed to log inbound." });
      }
    } catch {
      setMessage({ type: "error", text: "Could not reach the API." });
    }
  };

  const handleBulkUpload = async (file) => {
    if (!file) return;
    const ext = file.name.split(".").pop().toLowerCase();
    if (!["csv", "xlsx"].includes(ext)) {
      setMessage({ type: "error", text: "Please upload a CSV or XLSX file." });
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await authFetch(`/inbound-shipments/imports`, { method: "POST", body: formData });
      const data = await res.json();
      setMessage({
        type: "success",
        text: `Imported ${data.imported} inbound records.${data.total_errors > 0 ? ` ${data.total_errors} errors.` : ""}`,
      });
      loadData();
    } catch {
      setMessage({ type: "error", text: "Could not process the file." });
    } finally {
      setUploading(false);
      setUploadFile(null);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length > 0) {
      handleBulkUpload(e.dataTransfer.files[0]);
    }
  };

  const uploadAttachment = async () => {
    if (!uploadFile || !detailShipment) return;
    const formData = new FormData();
    formData.append("file", uploadFile);
    try {
      const res = await authFetch(`/inbound-shipments/${detailShipment.id}/attachments`, {
        method: "POST",
        body: formData,
      });
      if (res.ok) {
        setUploadFile(null);
        loadAttachments(detailShipment.id);
      }
    } catch (error) {
      console.error("Failed to upload inbound attachment", error);
    }
  };

  const loadAttachments = (shipmentId) => {
    authFetch(`/inbound-shipments/${shipmentId}/attachments`)
      .then(r => r.json())
      .then(d => setAttachments(d.data))
      .catch(error => console.error("Failed to load inbound attachments", error));
  };

  const openDetail = (shipment) => {
    setDetailShipment(shipment);
    loadAttachments(shipment.id);
  };

  const downloadAttachment = (id, filename) => {
    apiDownloadAttachment(id, filename).catch(() => {});
  };

  const deleteAttachment = async (id) => {
    if (!confirm("Delete this attachment?")) return;
    await authFetch(`/attachments/${id}`, { method: "DELETE" });
    if (detailShipment) loadAttachments(detailShipment.id);
  };

  const selectedProduct = products.find(p => p.id === Number(form.product_id));

  return (
    <section>
      <div className="page-header">
        <div>
          <h1 className="page-title">Inbound Stock</h1>
          <p className="page-subtitle">Log incoming stock and manage deliveries</p>
        </div>
        {can("inbound", "write") && (
          <div style={{ display: "flex", gap: 8 }}>
            <label className="btn btn-secondary btn-sm" style={{ cursor: "pointer" }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
              Bulk Upload
              <input type="file" accept=".csv,.xlsx" style={{ display: "none" }} onChange={e => handleBulkUpload(e.target.files[0])} />
            </label>
          </div>
        )}
      </div>

      {message && (
        <div className={`alert alert-${message.type}`} style={{ marginBottom: 20 }}>
          <span>{message.text}</span>
          <button className="btn btn-ghost btn-xs" style={{ padding: "2px 8px" }} onClick={() => setMessage(null)}>&times;</button>
        </div>
      )}

      {uploading && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-body" style={{ display: "flex", alignItems: "center", gap: 12, justifyContent: "center" }}>
            <div className="spinner" />
            <span className="muted">Processing file...</span>
          </div>
        </div>
      )}

      {can("inbound", "write") && (
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-body">
          <h3 className="section-title">Log Incoming Stock</h3>
          <form onSubmit={logInbound}>
            <div className="form-grid" style={{ marginBottom: 16 }}>
              <div className="input-group">
                <label className="input-label">Product *</label>
                <select className="select" value={form.product_id} onChange={e => setForm({ ...form, product_id: e.target.value })} required>
                  <option value="">Select product...</option>
                  {products.filter(p => !p.archived).map(p => (
                    <option key={p.id} value={p.id}>{p.name} ({p.sku}) - {p.quantity} in stock</option>
                  ))}
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">Supplier *</label>
                <select className="select" value={form.supplier_id} onChange={e => setForm({ ...form, supplier_id: e.target.value })} required>
                  <option value="">Select supplier...</option>
                  {suppliers.map(s => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">Quantity *</label>
                <input className="input" type="number" min="1" value={form.quantity} onChange={e => setForm({ ...form, quantity: Number(e.target.value) })} required />
              </div>
              <div className="input-group">
                <label className="input-label">Invoice / Ref #</label>
                <input className="input" placeholder="INV-00123" value={form.invoice_ref} onChange={e => setForm({ ...form, invoice_ref: e.target.value })} />
              </div>
              <div className="input-group">
                <label className="input-label">Received Date</label>
                <input className="input" type="date" value={form.received_date} onChange={e => setForm({ ...form, received_date: e.target.value })} />
              </div>
              <div className="input-group">
                <label className="input-label">Notes</label>
                <input className="input" placeholder="Additional notes..." value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
              </div>
            </div>

            {selectedProduct && (
              <div className="alert alert-success" style={{ marginBottom: 16 }}>
                <span>
                  Current stock of <strong>{selectedProduct.name}</strong>: {selectedProduct.quantity} units.
                  After receiving: <strong>{selectedProduct.quantity + form.quantity}</strong> units.
                </span>
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button type="submit" className="btn btn-primary btn-sm" disabled={!form.product_id || !form.supplier_id || form.quantity <= 0}>
                Log Inbound
              </button>
            </div>
          </form>
        </div>
      </div>
      )}

      {can("inbound", "write") && (
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-body" style={{ paddingBottom: 12 }}>
          <div
            ref={dropRef}
            className={`dropzone ${dragging ? "dropzone-active" : ""}`}
            onDragOver={e => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <div style={{ marginBottom: 8 }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth="1.5" style={{ margin: "0 auto" }}>
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
              </svg>
            </div>
            <div className="dropzone-text">
              <strong>Drag & drop a CSV/XLSX file here</strong>
              <br />
              or click to browse. Must include: product_name or sku, supplier_name, quantity.
            </div>
            <input ref={fileInputRef} type="file" accept=".csv,.xlsx" style={{ display: "none" }} onChange={e => handleBulkUpload(e.target.files[0])} />
          </div>
        </div>
      </div>
      )}

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Product</th>
              <th>Supplier</th>
              <th>Qty</th>
              <th>Invoice Ref</th>
              <th>Attachments</th>
              <th style={{ textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {shipments.length === 0 ? (
              <tr>
                <td colSpan={7} className="empty-state">
                  <div className="empty-state-text">No inbound records yet</div>
                </td>
              </tr>
            ) : (
              shipments.map(s => (
                <tr key={s.id}>
                  <td style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", whiteSpace: "nowrap" }}>
                    {s.received_date || "-"}
                  </td>
                  <td>
                    <div style={{ fontWeight: 600 }}>{s.product_name}</div>
                    <div className="muted" style={{ fontSize: "0.75rem" }}>{s.product_sku}</div>
                  </td>
                  <td style={{ color: "var(--text-secondary)" }}>{s.supplier_name}</td>
                  <td>
                    <span style={{ fontWeight: 700, color: "var(--green)" }}>+{s.quantity}</span>
                  </td>
                  <td>
                    {s.invoice_ref ? (
                      <span className="badge badge-info">{s.invoice_ref}</span>
                    ) : (
                      <span className="muted">-</span>
                    )}
                  </td>
                  <td>
                    {s.attachments && s.attachments.length > 0 ? (
                      <span className="badge badge-neutral">{s.attachments.length} file{s.attachments.length !== 1 ? "s" : ""}</span>
                    ) : (
                      <span className="muted">None</span>
                    )}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <button className="btn btn-ghost btn-xs" onClick={() => openDetail(s)}>Details</button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Dialog open={!!detailShipment} onClose={() => { setDetailShipment(null); setAttachments([]); }} title="Inbound Shipment Details">
        {detailShipment && (
          <div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 20 }}>
              <div>
                <div className="muted" style={{ fontSize: "0.75rem", marginBottom: 2 }}>Product</div>
                <div style={{ fontWeight: 600 }}>{detailShipment.product_name}</div>
                <div className="muted" style={{ fontSize: "0.8rem" }}>{detailShipment.product_sku}</div>
              </div>
              <div>
                <div className="muted" style={{ fontSize: "0.75rem", marginBottom: 2 }}>Supplier</div>
                <div style={{ fontWeight: 600 }}>{detailShipment.supplier_name}</div>
              </div>
              <div>
                <div className="muted" style={{ fontSize: "0.75rem", marginBottom: 2 }}>Quantity</div>
                <div style={{ fontWeight: 700, color: "var(--green)" }}>+{detailShipment.quantity}</div>
              </div>
              <div>
                <div className="muted" style={{ fontSize: "0.75rem", marginBottom: 2 }}>Received</div>
                <div>{detailShipment.received_date || "-"}</div>
              </div>
              {detailShipment.invoice_ref && (
                <div>
                  <div className="muted" style={{ fontSize: "0.75rem", marginBottom: 2 }}>Invoice Ref</div>
                  <div><span className="badge badge-info">{detailShipment.invoice_ref}</span></div>
                </div>
              )}
              {detailShipment.notes && (
                <div style={{ gridColumn: "1 / -1" }}>
                  <div className="muted" style={{ fontSize: "0.75rem", marginBottom: 2 }}>Notes</div>
                  <div>{detailShipment.notes}</div>
                </div>
              )}
            </div>

            <div style={{ borderTop: "1px solid var(--border)", paddingTop: 16, marginBottom: 16 }}>
              <h4 className="section-title">Attachments</h4>
              {attachments.length > 0 ? (
                <div style={{ display: "grid", gap: 8, marginBottom: 12 }}>
                  {attachments.map(a => (
                    <div key={a.id} style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "10px 14px",
                      background: "var(--bg-surface-elevated)",
                      borderRadius: "var(--radius-sm)",
                    }}>
                      <div>
                        <div style={{ fontWeight: 500, fontSize: "0.875rem" }}>{a.filename}</div>
                        <div className="muted" style={{ fontSize: "0.75rem" }}>{(a.file_size / 1024).toFixed(1)} KB</div>
                      </div>
                      <div style={{ display: "flex", gap: 6 }}>
                        <button className="btn btn-ghost btn-xs" onClick={() => downloadAttachment(a.id, a.filename)}>Download</button>
                        {can("inbound", "write") && (
                          <button className="btn btn-danger btn-xs" onClick={() => deleteAttachment(a.id)}>Remove</button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted" style={{ marginBottom: 12 }}>No attachments</p>
              )}

              {can("inbound", "write") && (
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input
                    type="file"
                    className="input"
                    style={{ flex: 1 }}
                    onChange={e => setUploadFile(e.target.files[0])}
                  />
                  <button className="btn btn-primary btn-sm" onClick={uploadAttachment} disabled={!uploadFile}>Upload</button>
                </div>
              )}
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button className="btn btn-ghost btn-sm" onClick={() => { setDetailShipment(null); setAttachments([]); }}>Close</button>
            </div>
          </div>
        )}
      </Dialog>
    </section>
  );
}
