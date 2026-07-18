import { useEffect, useState } from "react";
import { authFetch } from "../api";
import { useAuth } from "../AuthContext";

export default function Stock() {
  const { can } = useAuth();
  const [products, setProducts] = useState([]);
  const [selectedSku, setSelectedSku] = useState("");
  const [delta, setDelta] = useState(0);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState(null);
  const [recentMovements, setRecentMovements] = useState([]);

  const refreshData = () => {
    authFetch(`/products?limit=500`).then(r => r.json()).then(d => setProducts(d.data)).catch(() => {});
    authFetch(`/movements?limit=10`).then(r => r.json()).then(d => setRecentMovements(d.data)).catch(() => {});
  };

  useEffect(() => { refreshData(); }, []);

  const adjust = async () => {
    if (!selectedSku || delta === 0) return;
    try {
      const res = await authFetch(`/movements`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sku: selectedSku, delta: Number(delta), reason }),
      });
      const data = await res.json();
      if (res.status === 201) {
        setMessage({
          type: data.low_stock_warning ? "warning" : "success",
          text: `${data.product_name}: ${delta > 0 ? "+" : ""}${delta} units (now ${data.quantity_after})${data.low_stock_warning ? " — LOW STOCK!" : ""}`,
        });
        setDelta(0);
        setReason("");
        refreshData();
      } else {
        setMessage({ type: "error", text: data.detail || "Adjustment failed" });
      }
    } catch {
      setMessage({ type: "error", text: "Could not reach the API" });
    }
  };

  const undo = async () => {
    const last = recentMovements[0];
    if (!last) {
      setMessage({ type: "error", text: "Nothing to undo" });
      return;
    }
    try {
      const res = await authFetch(`/movements/${last.id}`, { method: "DELETE" });
      if (res.ok) {
        setMessage({ type: "success", text: "Last movement undone" });
        refreshData();
      } else {
        const data = await res.json();
        setMessage({ type: "error", text: data.detail || "Nothing to undo" });
      }
    } catch {
      setMessage({ type: "error", text: "Could not reach the API" });
    }
  };

  const selectedProduct = products.find(p => p.sku === selectedSku);
  const isLow = selectedProduct && selectedProduct.quantity <= selectedProduct.low_stock;

  return (
    <section>
      <div className="page-header">
        <div>
          <h1 className="page-title">Stock Adjustment</h1>
          <p className="page-subtitle">Add or remove stock from products</p>
        </div>
        {can("stock", "write") && (
          <button className="btn btn-ghost btn-sm" onClick={undo}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"/></svg>
            Undo Last
          </button>
        )}
      </div>

      {message && (
        <div className={`alert alert-${message.type === "error" ? "error" : message.type === "warning" ? "warning" : "success"}`} style={{ marginBottom: 20 }}>
          <span>{message.text}</span>
          <button className="btn btn-ghost btn-xs" style={{ padding: "2px 8px" }} onClick={() => setMessage(null)}>&times;</button>
        </div>
      )}

      {can("stock", "write") && (
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-body">
          <h3 className="section-title">Adjust Stock</h3>
          <div className="form-grid" style={{ marginBottom: 16 }}>
            <div className="input-group">
              <label className="input-label">Product *</label>
              <select
                className="select"
                value={selectedSku}
                onChange={e => setSelectedSku(e.target.value)}
              >
                <option value="">Select a product...</option>
                {products.map(p => (
                  <option key={p.sku} value={p.sku} disabled={p.archived}>
                    {p.name} ({p.sku}) — {p.quantity} in stock
                  </option>
                ))}
              </select>
            </div>
            <div className="input-group">
              <label className="input-label">Adjustment (+/-) *</label>
              <input
                className="input"
                type="number"
                placeholder="e.g. +10 or -5"
                value={delta}
                onChange={e => setDelta(Number(e.target.value))}
              />
            </div>
            <div className="input-group">
              <label className="input-label">Reason</label>
              <input
                className="input"
                placeholder="e.g. received, sold, damaged"
                value={reason}
                onChange={e => setReason(e.target.value)}
              />
            </div>
          </div>

          {selectedProduct && (
            <div style={{
              padding: "14px 18px",
              borderRadius: "var(--radius-sm)",
              background: isLow ? "var(--red-bg)" : "var(--green-bg)",
              border: `1px solid ${isLow ? "rgba(239, 68, 68, 0.15)" : "rgba(16, 185, 129, 0.15)"}`,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 16,
            }}>
              <div>
                <div style={{ fontWeight: 600 }}>{selectedProduct.name}</div>
                <div className="muted" style={{ fontSize: "0.8rem" }}>SKU: {selectedProduct.sku}</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ color: "var(--muted)", fontSize: "0.8125rem" }}>Current:</span>
                <span style={{ fontWeight: 700, fontSize: "1.125rem", color: isLow ? "var(--red)" : "var(--green)" }}>
                  {selectedProduct.quantity}
                </span>
                {isLow && <span className="badge badge-danger">Low stock</span>}
              </div>
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button
              className="btn btn-primary btn-sm"
              onClick={adjust}
              disabled={!selectedSku || delta === 0}
              style={delta < 0 ? { background: "var(--red)", boxShadow: "0 2px 8px rgba(239, 68, 68, 0.3)" } : {}}
            >
              {delta >= 0 ? "Receive Stock" : "Remove Stock"}
            </button>
          </div>
        </div>
      </div>
      )}

      <div className="card">
        <div className="card-body">
          <h3 className="section-title">Recent Movements</h3>
          {recentMovements.length === 0 ? (
            <div className="empty-state" style={{ padding: 24 }}>
              <div className="empty-state-text">No recent movements</div>
            </div>
          ) : (
            <div style={{ display: "grid", gap: 8 }}>
              {recentMovements.map((m, i) => (
                <div key={i} style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "12px 16px",
                  borderRadius: "var(--radius-sm)",
                  background: "var(--bg-surface-elevated)",
                  fontSize: "0.875rem",
                }}>
                  <div>
                    <span style={{ fontWeight: 600 }}>{m.name}</span>
                    <span className="muted" style={{ marginLeft: 8, fontSize: "0.8rem" }}>{m.sku}</span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                    <span style={{
                      fontWeight: 700,
                      fontSize: "0.9375rem",
                      color: m.delta > 0 ? "var(--green)" : m.delta < 0 ? "var(--red)" : "var(--text-secondary)",
                    }}>
                      {m.delta > 0 ? "+" : ""}{m.delta}
                    </span>
                    <span className="badge badge-neutral" style={{ fontSize: "0.7rem" }}>{m.action_type}</span>
                    <span className="muted" style={{ fontSize: "0.75rem", whiteSpace: "nowrap" }}>
                      {m.created_at ? new Date(m.created_at + "Z").toLocaleDateString() : ""}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
