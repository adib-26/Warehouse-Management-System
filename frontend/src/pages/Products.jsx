// frontend/src/pages/Products.jsx
import { useEffect, useState } from "react";

const API = "http://localhost:8000";

export default function Products() {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [newProduct, setNewProduct] = useState({
    name: "",
    sku: "",
    category: "",
    quantity: 0,
    description: "",
  });

  const load = async () => {
    const products = await (await fetch(`${API}/products?q=${encodeURIComponent(q)}`)).json();
    setItems(products);
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const addProduct = async () => {
    try {
      const res = await fetch(`${API}/products`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newProduct),
      });
      const data = await res.json();

      if (data.status === "created") {
        alert("✅ Product added successfully!");
        setNewProduct({ name: "", sku: "", category: "", quantity: 0, description: "" });
        load(); // refresh list
      } else {
        alert("❌ Failed to add product");
      }
    } catch (err) {
      console.error(err);
      alert("⚠️ Error adding product");
    }
  };

  return (
    <section>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, marginBottom: 16 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "1.5rem" }}>Products</h1>
          <p className="muted" style={{ margin: "6px 0 0 0" }}>Manage SKUs, categories and stock</p>
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            aria-label="Search products"
            placeholder="Search SKU or Name"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
            style={{
              padding: "8px 12px",
              borderRadius: 10,
              border: "1px solid rgba(255,255,255,0.04)",
              background: "color-mix(in srgb, var(--text-dark) 4%, transparent)",
              color: "var(--text-dark)",
              minWidth: 220,
              outline: "none",
            }}
          />

          <button
            onClick={load}
            disabled={!q}
            style={{
              padding: "8px 12px",
              borderRadius: 10,
              border: "none",
              cursor: q ? "pointer" : "not-allowed",
              background: q ? "var(--accent)" : "rgba(255,255,255,0.04)",
              color: q ? "white" : "var(--muted)",
              fontWeight: 700,
              boxShadow: q ? "0 6px 18px rgba(37,99,235,0.12)" : "none",
              transition: "transform var(--transition-fast) ease, background var(--transition-fast) ease",
            }}
          >
            Search
          </button>
        </div>
      </header>

      {/* Add Product Form */}
      <div
        className="card"
        style={{
          marginBottom: 18,
          padding: 16,
          display: "grid",
          gap: 12,
          gridTemplateColumns: "1fr",
          borderTop: "3px solid color-mix(in srgb, var(--accent) 14%, transparent)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ margin: 0, fontSize: "1.05rem" }}>Add New Product</h2>
          <div className="muted" style={{ fontSize: 12 }}>Quick add</div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10 }}>
          <input
            placeholder="Name"
            value={newProduct.name}
            onChange={(e) => setNewProduct({ ...newProduct, name: e.target.value })}
            style={inputStyle()}
          />
          <input
            placeholder="SKU"
            value={newProduct.sku}
            onChange={(e) => setNewProduct({ ...newProduct, sku: e.target.value })}
            style={inputStyle()}
          />
          <input
            placeholder="Category"
            value={newProduct.category}
            onChange={(e) => setNewProduct({ ...newProduct, category: e.target.value })}
            style={inputStyle()}
          />
          <input
            type="number"
            placeholder="Quantity"
            value={newProduct.quantity}
            onChange={(e) => setNewProduct({ ...newProduct, quantity: Number(e.target.value) })}
            style={inputStyle()}
          />
          <input
            placeholder="Description"
            value={newProduct.description}
            onChange={(e) => setNewProduct({ ...newProduct, description: e.target.value })}
            style={{ ...inputStyle(), gridColumn: "1 / -1" }}
          />
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button
            onClick={addProduct}
            style={{
              padding: "10px 16px",
              borderRadius: 10,
              border: "none",
              background: "linear-gradient(90deg,var(--accent),var(--accent-600))",
              color: "white",
              fontWeight: 800,
              cursor: "pointer",
              boxShadow: "0 8px 24px rgba(37,99,235,0.12)",
            }}
          >
            Add Product
          </button>
        </div>
      </div>

      {/* Products table */}
      <div className="card" style={{ padding: 0, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 640 }}>
          <thead>
            <tr style={{ background: "color-mix(in srgb, var(--text-dark) 4%, transparent)" }}>
              <th style={thStyle()}>Name</th>
              <th style={thStyle()}>SKU</th>
              <th style={thStyle()}>Category</th>
              <th style={thStyle()}>Qty</th>
            </tr>
          </thead>

          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={4} style={{ padding: 14, textAlign: "center", color: "var(--muted)" }}>
                  No products found
                </td>
              </tr>
            ) : (
              items.map((p) => (
                <tr key={p.id} style={{ borderTop: "1px solid rgba(255,255,255,0.03)" }}>
                  <td style={tdStyle()}>{p.name}</td>
                  <td style={tdStyle()}>{p.sku}</td>
                  <td style={tdStyle()}>{p.category}</td>
                  <td style={tdStyle()}>{p.quantity}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* Local helper styles */
function inputStyle() {
  return {
    padding: "10px 12px",
    borderRadius: 10,
    border: "1px solid rgba(255,255,255,0.04)",
    background: "color-mix(in srgb, var(--text-dark) 4%, transparent)",
    color: "var(--text-dark)",
    outline: "none",
  };
}

function thStyle() {
  return {
    textAlign: "left",
    padding: "12px 14px",
    fontSize: 13,
    color: "var(--muted)",
    fontWeight: 700,
    letterSpacing: "-0.01em",
  };
}

function tdStyle() {
  return {
    padding: "12px 14px",
    fontSize: 14,
    color: "var(--text-dark)",
  };
}
