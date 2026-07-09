import { useEffect, useState } from "react";

const API = "http://localhost:8000";

export default function Stock() {
  const [products, setProducts] = useState([]);
  const [selectedSku, setSelectedSku] = useState("");
  const [delta, setDelta] = useState(0);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState(null);
  const [recentMovements, setRecentMovements] = useState([]);

  const refreshData = () => {
    fetch(`${API}/products`).then((r) => r.json()).then(setProducts).catch(() => {});
    fetch(`${API}/history?limit=10`).then((r) => r.json()).then(setRecentMovements).catch(() => {});
  };

  useEffect(() => { refreshData(); }, []);

  const adjust = async () => {
    if (!selectedSku || delta === 0) return;
    try {
      const res = await fetch(`${API}/stock`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sku: selectedSku, delta: Number(delta), reason }),
      });
      const data = await res.json();
      if (res.ok) {
        setMessage({
          type: data.low_stock_warning ? "warning" : "success",
          text: `${data.product}: ${delta > 0 ? "+" : ""}${delta} units (now ${data.quantity})${data.low_stock_warning ? " — LOW STOCK!" : ""}`,
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
    try {
      const res = await fetch(`${API}/stock/undo`, { method: "POST" });
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

  const selectedProduct = products.find((p) => p.sku === selectedSku);
  const isLow = selectedProduct && selectedProduct.quantity <= selectedProduct.low_stock;

  return (
    <section>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "1.5rem" }}>Stock Adjustment</h1>
          <p className="muted" style={{ margin: "4px 0 0 0" }}>Add or remove stock from products</p>
        </div>
        <button className="btn btn-sm btn-ghost" onClick={undo} title="Undo last movement">
          ↩ Undo
        </button>
      </div>

      {message && (
        <div className="card" style={{
          padding: 12,
          marginBottom: 16,
          borderLeft: `4px solid ${message.type === "error" ? "#ef4444" : message.type === "warning" ? "#fbbf24" : "#34d399"}`,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>{message.text}</span>
            <button className="btn btn-sm btn-ghost" style={{ padding: "2px 8px" }} onClick={() => setMessage(null)}>✕</button>
          </div>
        </div>
      )}

      <div className="card" style={{ padding: 20, marginBottom: 16 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
          <div>
            <label className="muted" style={{ display: "block", marginBottom: 4 }}>Product</label>
            <select
              className="select"
              value={selectedSku}
              onChange={(e) => setSelectedSku(e.target.value)}
              style={{ width: "100%" }}
            >
              <option value="">Select a product...</option>
              {products.map((p) => (
                <option key={p.sku} value={p.sku} disabled={p.archived}>
                  {p.name} ({p.sku}) — {p.quantity} in stock
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="muted" style={{ display: "block", marginBottom: 4 }}>Adjustment</label>
            <input
              className="input"
              type="number"
              placeholder="+ or - quantity"
              value={delta}
              onChange={(e) => setDelta(Number(e.target.value))}
              style={{ width: "100%" }}
            />
          </div>
          <div>
            <label className="muted" style={{ display: "block", marginBottom: 4 }}>Reason</label>
            <input
              className="input"
              placeholder="e.g. received, sold, damaged"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              style={{ width: "100%" }}
            />
          </div>
        </div>

        {selectedProduct && (
          <div style={{
            marginTop: 12,
            padding: "8px 12px",
            borderRadius: 8,
            background: isLow ? "rgba(239, 68, 68, 0.1)" : "rgba(52, 211, 153, 0.1)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}>
            <div>
              <strong>{selectedProduct.name}</strong>
              <span className="muted" style={{ marginLeft: 8 }}>SKU: {selectedProduct.sku}</span>
            </div>
            <div>
              Current stock: <strong style={{ color: isLow ? "#ef4444" : "#34d399" }}>{selectedProduct.quantity}</strong>
              {isLow && <span className="badge badge-danger" style={{ marginLeft: 8 }}>Low stock</span>}
            </div>
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
          <button
            className="btn btn-sm"
            onClick={adjust}
            disabled={!selectedSku || delta === 0}
            style={{ background: delta < 0 ? "#dc2626" : undefined }}
          >
            {delta >= 0 ? "Receive Stock" : "Remove Stock"}
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: 16 }}>
        <h2 style={{ margin: "0 0 12px 0", fontSize: "1rem" }}>Recent Movements</h2>
        {recentMovements.length === 0 ? (
          <p className="muted">No recent movements</p>
        ) : (
          <div style={{ display: "grid", gap: 8 }}>
            {recentMovements.map((m, i) => (
              <div key={i} style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "8px 12px",
                borderRadius: 8,
                background: "color-mix(in srgb, var(--text-dark) 3%, transparent)",
                fontSize: "0.9rem",
              }}>
                <div>
                  <strong>{m.name}</strong>
                  <span className="muted" style={{ marginLeft: 8 }}>{m.sku}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{
                    fontWeight: 700,
                    color: m.delta > 0 ? "#34d399" : m.delta < 0 ? "#ef4444" : "inherit",
                  }}>
                    {m.delta > 0 ? "+" : ""}{m.delta}
                  </span>
                  <span className="muted" style={{ fontSize: "0.8rem" }}>{m.action_type}</span>
                  <span className="muted" style={{ fontSize: "0.8rem" }}>{m.created_at}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
