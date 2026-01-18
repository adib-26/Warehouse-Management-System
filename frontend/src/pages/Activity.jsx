import { useEffect, useState } from "react"

const API = "http://localhost:8000"

export default function Activity() {
  const [log, setLog] = useState([])

  const load = async () => {
    const history = await (await fetch(`${API}/history`)).json()
    setLog(history)
  }

  useEffect(() => { load() }, [])

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Activity Log</h1>
      {log.length === 0 ? (
        <p>No history yet</p>
      ) : (
        <ul className="list-disc ml-5 space-y-1">
          {log.map((l, i) => (
            <li key={i}>
              {l.at} — {l.name} ({l.description}): {l.delta > 0 ? `+${l.delta}` : l.delta}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}