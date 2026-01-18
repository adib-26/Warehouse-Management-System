import { useState } from "react"

const API = "http://localhost:8000"

export default function Stock() {
  const [sku, setSku] = useState("")
  const [qty, setQty] = useState(0)

  const adjust = async () => {
    await fetch(`${API}/stock`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sku, delta: Number(qty), reason: "manual" })
    })
    alert("Stock updated!") // replace with toast later
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Stock Adjustment</h1>
      <div className="flex gap-2 mb-6">
        <input
          className="border p-2"
          placeholder="SKU"
          value={sku}
          onChange={e => setSku(e.target.value)}
        />
        <input
          className="border p-2"
          type="number"
          placeholder="+ / -"
          value={qty}
          onChange={e => setQty(e.target.value)}
        />
        <button className="bg-black text-white px-4" onClick={adjust}>Apply</button>
      </div>
    </div>
  )
}