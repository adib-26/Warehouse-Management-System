import { useEffect, useState } from "react";
import { authFetch } from "../api";
import { useAuth } from "../AuthContext";
import { useToast } from "../components/FeedbackProvider";
import BalanceStrip from "../components/BalanceStrip";
import LedgerList from "../components/LedgerList";
import { formatQuantity, responseErrorMessage } from "../format";
import PageHeader from "../components/PageHeader";

export default function Stock() {
  const { can } = useAuth();
  const toast = useToast();
  const [products, setProducts] = useState([]);
  const [selectedSku, setSelectedSku] = useState("");
  // Kept as a string so a partially typed value such as "-" survives editing.
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("");
  const [recentMovements, setRecentMovements] = useState([]);

  const refreshData = () => {
    authFetch(`/products?limit=500`).then(r => r.json()).then(d => setProducts(d.data)).catch(() => {});
    authFetch(`/movements?limit=10`).then(r => r.json()).then(d => setRecentMovements(d.data)).catch(() => {});
  };

  useEffect(() => { refreshData(); }, []);

  const selectedProduct = products.find(p => p.sku === selectedSku);
  const deltaNumber = Number(delta);
  const deltaValid = delta !== "" && Number.isFinite(deltaNumber) && deltaNumber !== 0;
  const currentQuantity = selectedProduct ? Number(selectedProduct.quantity) : 0;
  const threshold = selectedProduct ? Number(selectedProduct.low_stock) : 0;
  const projected = currentQuantity + (deltaValid ? deltaNumber : 0);
  const goesNegative = deltaValid && projected < 0;
  const endsLow = !goesNegative && projected <= threshold;

  const adjust = async () => {
    if (!selectedSku || !deltaValid) return;
    try {
      const res = await authFetch(`/movements`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sku: selectedSku, delta: deltaNumber, reason }),
      });
      const data = await res.json();
      if (res.status === 201) {
        const summary = `${data.product_name}: ${deltaNumber > 0 ? "+" : ""}${formatQuantity(deltaNumber)} units, now ${formatQuantity(data.quantity_after)}`;
        if (data.low_stock_warning) toast.warning(`${summary} — below the low-stock threshold.`);
        else toast.success(summary);
        setDelta("");
        setReason("");
        refreshData();
      } else {
        toast.error(responseErrorMessage(data, "Adjustment failed."));
      }
    } catch {
      toast.error("Could not reach the API.");
    }
  };

  const undo = async () => {
    const last = recentMovements[0];
    if (!last) {
      toast.error("Nothing to undo.");
      return;
    }
    try {
      const res = await authFetch(`/movements/${last.id}`, { method: "DELETE" });
      if (res.ok) {
        toast.success("Last movement undone.");
        refreshData();
      } else {
        const data = await res.json();
        toast.error(responseErrorMessage(data, "Nothing to undo."));
      }
    } catch {
      toast.error("Could not reach the API.");
    }
  };

  return (
    <section>
      <PageHeader
        eyebrow="Inventory"
        title="Stock Adjustment"
        subtitle="Correct a balance by hand"
        actions={can("stock", "write") && (
          <button className="btn btn-ghost btn-sm" onClick={undo}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
            </svg>
            Undo Last
          </button>
        )}
      />

      {can("stock", "write") && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-body">
            <h2 className="section-title">Adjust Stock</h2>
            <div className="form-grid" style={{ marginBottom: 16 }}>
              <div className="input-group">
                <label className="input-label" htmlFor="stock-product">Product *</label>
                <select
                  id="stock-product"
                  className="select"
                  value={selectedSku}
                  onChange={e => setSelectedSku(e.target.value)}
                >
                  <option value="">Select a product...</option>
                  {products.filter(p => !p.is_forecast_test).map(p => (
                    <option key={p.sku} value={p.sku} disabled={p.archived || !!p.batch_tracking_enabled_at}>
                      {p.name} ({p.sku}) — {formatQuantity(p.quantity)} in stock{p.batch_tracking_enabled_at ? " — batch tracked" : ""}
                    </option>
                  ))}
                </select>
              </div>
              <div className="input-group">
                <label className="input-label" htmlFor="stock-delta">Adjustment (+/-) *</label>
                <input
                  id="stock-delta"
                  className="input"
                  type="number"
                  step="0.01"
                  placeholder="e.g. 10 or -5"
                  value={delta}
                  onChange={e => setDelta(e.target.value)}
                />
                <span className="input-hint">Positive receives stock, negative removes it.</span>
              </div>
              <div className="input-group">
                <label className="input-label" htmlFor="stock-reason">Reason</label>
                <input
                  id="stock-reason"
                  className="input"
                  placeholder="e.g. received, sold, damaged"
                  value={reason}
                  onChange={e => setReason(e.target.value)}
                />
              </div>
            </div>

            {selectedProduct && (
              <div style={{ display: "grid", gap: 12, marginBottom: 16 }}>
                <BalanceStrip
                  title={selectedProduct.name}
                  subtitle={`SKU ${selectedProduct.sku}`}
                  current={currentQuantity}
                  after={projected}
                  tone={deltaValid ? (deltaNumber > 0 ? "positive" : "negative") : "neutral"}
                  note={`Low-stock threshold ${formatQuantity(threshold)}`}
                />
                {goesNegative && (
                  <div className="alert alert-warning" role="status">
                    <span>This adjustment takes the balance below zero ({formatQuantity(projected)}).</span>
                  </div>
                )}
                {deltaValid && endsLow && (
                  <div className="alert alert-warning" role="status">
                    <span>The resulting balance is at or below the low-stock threshold.</span>
                  </div>
                )}
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button
                className={`btn btn-sm ${deltaValid && deltaNumber < 0 ? "btn-danger-solid" : "btn-primary"}`}
                onClick={adjust}
                disabled={!selectedSku || !deltaValid}
              >
                {deltaValid && deltaNumber < 0 ? "Remove Stock" : "Receive Stock"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-body">
          <h2 className="section-title">Recent Movements</h2>
          <LedgerList items={recentMovements} />
        </div>
      </div>
    </section>
  );
}
