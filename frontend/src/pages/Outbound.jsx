import { useEffect, useState, useRef } from "react";
import { authFetch, downloadAttachment as apiDownloadAttachment } from "../api";
import { useAuth } from "../AuthContext";
import Dialog from "../components/Dialog";
import BalanceStrip from "../components/BalanceStrip";
import { useConfirm } from "../components/FeedbackProvider";
import { formatPlainDate, formatQuantity, responseErrorMessage } from "../format";
import PageHeader from "../components/PageHeader";

function localDate() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

export default function Outbound() {
  const { can } = useAuth();
  const confirm = useConfirm();
  const [products, setProducts] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [shipments, setShipments] = useState([]);
  const [form, setForm] = useState({
    product_id: "",
    customer_id: "",
    warehouse_id: "",
    quantity: 1,
    so_ref: "",
    dispatch_date: localDate(),
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
    authFetch(`/customers?limit=500`).then(r => r.json()).then(d => setCustomers(d.data)).catch(() => {});
    authFetch(`/warehouses?limit=500`).then(r => r.json()).then(d => setWarehouses(d.data)).catch(() => {});
    authFetch(`/outbound-shipments?limit=100`).then(r => r.json()).then(d => setShipments(d.data)).catch(() => {});
  };

  useEffect(() => { loadData(); }, []);

  const selectedProduct = products.find(p => p.id === Number(form.product_id));
  const insufficientStock = selectedProduct && form.quantity > selectedProduct.quantity;

  const logOutbound = async (e) => {
    e.preventDefault();
    if (!form.product_id || !form.customer_id || !form.warehouse_id || form.quantity <= 0 || insufficientStock) return;
    try {
      const res = await authFetch(`/outbound-shipments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          product_id: Number(form.product_id),
          customer_id: Number(form.customer_id),
          warehouse_id: Number(form.warehouse_id),
          quantity: Number(form.quantity),
        }),
      });
      const data = await res.json();
      if (res.status === 201) {
        setMessage({ type: "success", text: `${data.quantity}x ${data.product_name} dispatched to ${data.customer_name}. Remaining stock: ${data.quantity_after}` });
        setForm({ product_id: "", customer_id: "", warehouse_id: "", quantity: 1, so_ref: "", dispatch_date: localDate(), notes: "" });
        loadData();
      } else {
        setMessage({ type: "error", text: data.detail || "Failed to log outbound." });
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
      const res = await authFetch(`/outbound-shipments/imports`, { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) {
        setMessage({ type: "error", text: responseErrorMessage(data, "Could not import the outbound file.") });
        return;
      }
      const rowErrors = Array.isArray(data.errors) ? data.errors : [];
      const totalErrors = Number(data.total_errors) || rowErrors.length;
      setMessage({
        type: totalErrors > 0 ? "warning" : "success",
        text: `Imported ${data.imported} outbound records.${totalErrors > 0 ? ` ${totalErrors} row${totalErrors === 1 ? " was" : "s were"} rejected: ${rowErrors.join("; ") || "see the source file and correct the required values."}` : ""}`,
      });
      loadData();
    } catch {
      setMessage({ type: "error", text: "Could not process the file." });
    } finally {
      setUploading(false);
      setUploadFile(null);
    }
  };

  const selectBulkFile = (event) => {
    const file = event.currentTarget.files?.[0];
    // Let an operator correct and choose the same file again after a validation error.
    event.currentTarget.value = "";
    handleBulkUpload(file);
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
      const res = await authFetch(`/outbound-shipments/${detailShipment.id}/attachments`, {
        method: "POST",
        body: formData,
      });
      if (res.ok) {
        setUploadFile(null);
        loadAttachments(detailShipment.id);
      }
    } catch (error) {
      console.error("Failed to upload outbound attachment", error);
    }
  };

  const loadAttachments = (shipmentId) => {
    authFetch(`/outbound-shipments/${shipmentId}/attachments`)
      .then(r => r.json())
      .then(d => setAttachments(d.data))
      .catch(error => console.error("Failed to load outbound attachments", error));
  };

  const openDetail = (shipment) => {
    setDetailShipment(shipment);
    loadAttachments(shipment.id);
  };

  const downloadAttachment = (id, filename) => {
    apiDownloadAttachment(id, filename).catch(() => {});
  };

  const deleteAttachment = async (id) => {
    const ok = await confirm({
      title: "Remove attachment",
      message: "Remove this attachment? This cannot be undone.",
      confirmLabel: "Remove",
      tone: "danger",
    });
    if (!ok) return;
    await authFetch(`/attachments/${id}`, { method: "DELETE" });
    if (detailShipment) loadAttachments(detailShipment.id);
  };

  return (
    <section>
      <PageHeader eyebrow="Supply Chain" title="Outbound Stock" subtitle="What's going out to customers" />

      {message && (
        <div className={`alert alert-${message.type}`} role={message.type === "error" ? "alert" : "status"} style={{ marginBottom: 20 }}>
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

      {can("outbound", "write") && (
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-body">
          <h3 className="section-title">Log Outbound Dispatch</h3>
          <form onSubmit={logOutbound}>
            <div className="form-grid" style={{ marginBottom: 16 }}>
              <div className="input-group">
                <label className="input-label">Product *</label>
                <select className="select" value={form.product_id} onChange={e => setForm({ ...form, product_id: e.target.value })} required>
                  <option value="">Select product...</option>
                  {products.filter(p => !p.archived && !p.is_forecast_test).map(p => (
                    <option key={p.id} value={p.id}>{p.name} ({p.sku}) - {formatQuantity(p.quantity)} in stock</option>
                  ))}
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">Customer *</label>
                <select className="select" value={form.customer_id} onChange={e => setForm({ ...form, customer_id: e.target.value })} required>
                  <option value="">Select customer...</option>
                  {customers.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">Warehouse *</label>
                <select className="select" value={form.warehouse_id} onChange={e => setForm({ ...form, warehouse_id: e.target.value })} required>
                  <option value="">Select warehouse...</option>
                  {warehouses.map(w => (
                    <option key={w.id} value={w.id}>{w.name} ({w.warehouse_code})</option>
                  ))}
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">Quantity *</label>
                <input className="input" type="number" min="0.01" step="0.01" value={form.quantity} onChange={e => setForm({ ...form, quantity: Number(e.target.value) })} required />
              </div>
              <div className="input-group">
                <label className="input-label">SO / Ref #</label>
                <input className="input" placeholder="SO-00123" value={form.so_ref} onChange={e => setForm({ ...form, so_ref: e.target.value })} />
              </div>
              <div className="input-group">
                <label className="input-label">Dispatch Date</label>
                <input className="input" type="date" value={form.dispatch_date} onChange={e => setForm({ ...form, dispatch_date: e.target.value })} />
              </div>
              <div className="input-group">
                <label className="input-label">Notes</label>
                <input className="input" placeholder="Additional notes..." value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
              </div>
            </div>

            {selectedProduct && (
              <div style={{ display: "grid", gap: 12, marginBottom: 16 }}>
                <BalanceStrip
                  title={selectedProduct.name}
                  subtitle={`SKU ${selectedProduct.sku}`}
                  current={Number(selectedProduct.quantity)}
                  after={Number(selectedProduct.quantity) - (Number(form.quantity) || 0)}
                  tone={Number(form.quantity) > 0 ? "negative" : "neutral"}
                />
                {insufficientStock && (
                  <div className="alert alert-error" role="alert">
                    <span>
                      Insufficient stock: only <strong>{formatQuantity(selectedProduct.quantity)}</strong> unit
                      {Number(selectedProduct.quantity) !== 1 ? "s" : ""} of <strong>{selectedProduct.name}</strong> available.
                      Negative stock dispatch is not allowed.
                    </span>
                  </div>
                )}
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button type="submit" className="btn btn-primary btn-sm" disabled={!form.product_id || !form.customer_id || !form.warehouse_id || form.quantity <= 0 || insufficientStock}>
                Log Outbound
              </button>
            </div>
          </form>
        </div>
      </div>
      )}

      {can("outbound", "write") && (
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-body" style={{ paddingBottom: 12 }}>
          <div
            ref={dropRef}
            className={`dropzone ${dragging ? "dropzone-active" : ""}`}
            onDragOver={e => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={event => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            role="button"
            tabIndex={0}
            aria-label="Upload outbound CSV or XLSX file"
          >
            <div style={{ marginBottom: 8 }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth="1.5" style={{ margin: "0 auto" }}>
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
              </svg>
            </div>
            <div className="dropzone-text">
              <strong>Drag & drop a CSV/XLSX file here</strong>
              <br />
              or click to browse. Required: product_name or sku, customer_name, warehouse_code, and quantity. The warehouse code must match an active warehouse.
            </div>
            <input ref={fileInputRef} type="file" accept=".csv,.xlsx" style={{ display: "none" }} onChange={selectBulkFile} />
          </div>
        </div>
      </div>
      )}

      <div className="table-container" tabIndex={0} role="region" aria-label="Outbound shipments">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Product</th>
              <th>Customer</th>
              <th>Warehouse</th>
              <th>Qty</th>
              <th>SO Ref</th>
              <th>Attachments</th>
              <th style={{ textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {shipments.length === 0 ? (
              <tr>
                <td colSpan={8} className="empty-state">
                  <div className="empty-state-text">No outbound records yet</div>
                </td>
              </tr>
            ) : (
              shipments.map(s => (
                <tr key={s.id}>
                  <td className="mono" style={{ color: "var(--text-secondary)", fontSize: "0.78rem", whiteSpace: "nowrap" }}>
                    {formatPlainDate(s.dispatch_date)}
                  </td>
                  <td>
                    <div style={{ fontWeight: 600 }}>{s.product_name}</div>
                    <div className="muted" style={{ fontSize: "0.75rem" }}>{s.product_sku}</div>
                  </td>
                  <td style={{ color: "var(--text-secondary)" }}>{s.customer_name}</td>
                  <td style={{ color: "var(--text-secondary)" }}>
                    {s.warehouse_name ? (
                      <>
                        <div>{s.warehouse_name}</div>
                        <div className="muted" style={{ fontSize: "0.75rem" }}>{s.warehouse_code}</div>
                      </>
                    ) : <span className="muted">Legacy / unassigned</span>}
                  </td>
                  <td>
                    <span className="ledger-num ledger-num--down">-{formatQuantity(s.quantity)}</span>
                  </td>
                  <td>
                    {s.so_ref ? (
                      <span className="badge badge-info">{s.so_ref}</span>
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

      <Dialog open={!!detailShipment} onClose={() => { setDetailShipment(null); setAttachments([]); }} title="Outbound Shipment Details" maxWidth={640}>
        {detailShipment && (
          <div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 20 }}>
              <div>
                <div className="muted" style={{ fontSize: "0.75rem", marginBottom: 2 }}>Product</div>
                <div style={{ fontWeight: 600 }}>{detailShipment.product_name}</div>
                <div className="muted" style={{ fontSize: "0.8rem" }}>{detailShipment.product_sku}</div>
              </div>
              <div>
                <div className="muted" style={{ fontSize: "0.75rem", marginBottom: 2 }}>Customer</div>
                <div style={{ fontWeight: 600 }}>{detailShipment.customer_name}</div>
              </div>
              <div>
                <div className="muted" style={{ fontSize: "0.75rem", marginBottom: 2 }}>Warehouse</div>
                <div style={{ fontWeight: 600 }}>{detailShipment.warehouse_name || "Legacy / unassigned"}</div>
                {detailShipment.warehouse_code && <div className="muted" style={{ fontSize: "0.8rem" }}>{detailShipment.warehouse_code}</div>}
              </div>
              <div>
                <div className="muted" style={{ fontSize: "0.75rem", marginBottom: 2 }}>Quantity</div>
                <div className="ledger-num ledger-num--down">-{formatQuantity(detailShipment.quantity)}</div>
              </div>
              <div>
                <div className="muted" style={{ fontSize: "0.75rem", marginBottom: 2 }}>Dispatched</div>
                <div>{formatPlainDate(detailShipment.dispatch_date)}</div>
              </div>
              {detailShipment.so_ref && (
                <div>
                  <div className="muted" style={{ fontSize: "0.75rem", marginBottom: 2 }}>SO Ref</div>
                  <div><span className="badge badge-info">{detailShipment.so_ref}</span></div>
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
              <h4 className="section-title">Attachments (e.g. signed DOs)</h4>
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
                        {can("outbound", "write") && (
                          <button className="btn btn-danger btn-xs" onClick={() => deleteAttachment(a.id)}>Remove</button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted" style={{ marginBottom: 12 }}>No attachments</p>
              )}

              {can("outbound", "write") && (
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
