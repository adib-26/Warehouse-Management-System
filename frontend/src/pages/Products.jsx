import { useEffect, useState } from "react"

const API = "http://localhost:8000"

export default function Products() {
  const [items, setItems] = useState([])
  const [q, setQ] = useState("")
  const [newProduct, setNewProduct] = useState({
    name: "",
    sku: "",
    category: "",
    quantity: 0,
    description: ""
  })

  const load = async () => {
    const products = await (await fetch(`${API}/products?q=${q}`)).json()
    setItems(products)
  }

  useEffect(() => { load() }, [])

  const addProduct = async () => {
    try {
      const res = await fetch(`${API}/products`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newProduct),
      })
      const data = await res.json()

      if (data.status === "created") {
        alert("✅ Product added successfully!")
        setNewProduct({ name: "", sku: "", category: "", quantity: 0, description: "" })
        load() // refresh list
      } else {
        alert("❌ Failed to add product")
      }
    } catch (err) {
      console.error(err)
      alert("⚠️ Error adding product")
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Products</h1>

      {/* Search */}
      <input
        className="border p-2 w-full mb-2"
        placeholder="Search SKU or Name"
        value={q}
        onChange={e => setQ(e.target.value)}
        onKeyDown={e => e.key === "Enter" && load()}
      />
      <button
        className={`px-4 mb-4 text-white ${q ? "bg-black" : "bg-gray-400 cursor-not-allowed"}`}
        onClick={load}
        disabled={!q}
      >
        Search
      </button>

      {/* Add Product Form */}
      <div className="bg-white p-4 rounded shadow mb-6">
        <h2 className="text-lg font-semibold mb-2">Add New Product</h2>
        <div className="grid grid-cols-2 gap-2 mb-2">
          <input
            className="border p-2"
            placeholder="Name"
            value={newProduct.name}
            onChange={e => setNewProduct({ ...newProduct, name: e.target.value })}
          />
          <input
            className="border p-2"
            placeholder="SKU"
            value={newProduct.sku}
            onChange={e => setNewProduct({ ...newProduct, sku: e.target.value })}
          />
          <input
            className="border p-2"
            placeholder="Category"
            value={newProduct.category}
            onChange={e => setNewProduct({ ...newProduct, category: e.target.value })}
          />
          <input
            className="border p-2"
            type="number"
            placeholder="Quantity"
            value={newProduct.quantity}
            onChange={e => setNewProduct({ ...newProduct, quantity: Number(e.target.value) })}
          />
          <input
            className="border p-2 col-span-2"
            placeholder="Description"
            value={newProduct.description}
            onChange={e => setNewProduct({ ...newProduct, description: e.target.value })}
          />
        </div>
        <button
          className="bg-black text-white px-4 py-2"
          onClick={addProduct}
        >
          Add Product
        </button>
      </div>

      {/* Products table */}
      <table className="w-full border mb-6">
        <thead>
          <tr className="bg-gray-100">
            <th className="text-left p-2">Name</th>
            <th className="text-left p-2">SKU</th>
            <th className="text-left p-2">Category</th>
            <th className="text-left p-2">Qty</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <tr>
              <td colSpan={4} className="p-2">No products found</td>
            </tr>
          ) : (
            items.map(p => (
              <tr key={p.id}>
                <td className="p-2">{p.name}</td>
                <td className="p-2">{p.sku}</td>
                <td className="p-2">{p.category}</td>
                <td className="p-2">{p.quantity}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}