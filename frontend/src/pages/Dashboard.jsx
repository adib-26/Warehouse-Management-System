import { useEffect, useState } from "react"

const API = "http://localhost:8000"

export default function Dashboard() {
  const [stats, setStats] = useState({ products: 0, stock: 0, activity: 0 })

  const load = async () => {
    // You can adjust these endpoints based on your backend
    const products = await (await fetch(`${API}/products`)).json()
    const history = await (await fetch(`${API}/history`)).json()

    setStats({
      products: products.length,
      stock: products.reduce((sum, p) => sum + p.quantity, 0),
      activity: history.length,
    })
  }

  useEffect(() => { load() }, [])

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Dashboard Overview</h1>

      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-white shadow rounded p-4">
          <h2 className="text-sm font-semibold text-gray-500">Total Products</h2>
          <p className="text-2xl font-bold">{stats.products}</p>
        </div>
        <div className="bg-white shadow rounded p-4">
          <h2 className="text-sm font-semibold text-gray-500">Total Stock</h2>
          <p className="text-2xl font-bold">{stats.stock}</p>
        </div>
        <div className="bg-white shadow rounded p-4">
          <h2 className="text-sm font-semibold text-gray-500">Activity Logs</h2>
          <p className="text-2xl font-bold">{stats.activity}</p>
        </div>
      </div>

      {/* Placeholder for chart */}
      <div className="bg-white shadow rounded p-6">
        <h2 className="text-lg font-semibold mb-4">Stock Trend</h2>
        <p className="text-gray-500">📊 Chart goes here (we can add Recharts or Chart.js later)</p>
      </div>
    </div>
  )
}