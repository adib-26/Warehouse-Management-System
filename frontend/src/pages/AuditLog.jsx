import { useEffect, useState } from "react";
import { authFetch } from "../api";
import { useAuth } from "../AuthContext";

const ACTION_STYLES = {
  CREATE: { bg: "var(--green-bg)", color: "var(--green)" },
  UPDATE: { bg: "var(--blue-bg)", color: "var(--blue)" },
  DELETE: { bg: "var(--red-bg)", color: "var(--red)" },
  ARCHIVE: { bg: "var(--yellow-bg)", color: "var(--yellow)" },
  STOCK_IN: { bg: "var(--green-bg)", color: "var(--green)" },
  STOCK_OUT: { bg: "var(--red-bg)", color: "var(--red)" },
  LOGIN: { bg: "var(--blue-bg)", color: "var(--blue)" },
  BULK_IMPORT: { bg: "var(--yellow-bg)", color: "var(--yellow)" },
  UPLOAD: { bg: "var(--blue-bg)", color: "var(--blue)" },
  UNDO: { bg: "var(--yellow-bg)", color: "var(--yellow)" },
};

export default function AuditLog() {
  const { can } = useAuth();
  const [logs, setLogs] = useState([]);
  const [userFilter, setUserFilter] = useState("");
  const [moduleFilter, setModuleFilter] = useState("");
  const [actionFilter, setActionFilter] = useState("");

  // Admins use the /admin endpoint; managers with reports access use /audit-logs.
  const endpoint = can("admin", "read") ? "/admin/audit-logs" : "/audit-logs";

  const load = () => {
    const params = new URLSearchParams({ limit: "200" });
    if (userFilter) params.set("username", userFilter);
    if (moduleFilter) params.set("module", moduleFilter);
    if (actionFilter) params.set("action", actionFilter);
    authFetch(`${endpoint}?${params}`).then(r => r.json()).then(d => setLogs(d.data)).catch(() => {});
  };

  useEffect(() => { load(); }, [moduleFilter, actionFilter]);

  const usernames = [...new Set(logs.map(l => l.username).filter(Boolean))];
  const modules = [...new Set(logs.map(l => l.module).filter(Boolean))];
  const actions = [...new Set(logs.map(l => l.action).filter(Boolean))];

  return (
    <section>
      <div className="page-header">
        <div>
          <h1 className="page-title">Audit Log</h1>
          <p className="page-subtitle">Who did what, when, and on what record</p>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-body" style={{ paddingBottom: 12 }}>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <input
              className="input"
              placeholder="Filter by username..."
              value={userFilter}
              onChange={e => setUserFilter(e.target.value)}
              onKeyDown={e => e.key === "Enter" && load()}
              list="audit-usernames"
              style={{ width: "auto", minWidth: 180 }}
            />
            <datalist id="audit-usernames">
              {usernames.map(u => <option key={u} value={u} />)}
            </datalist>
            <select className="select" value={moduleFilter} onChange={e => setModuleFilter(e.target.value)} style={{ width: "auto", minWidth: 140 }}>
              <option value="">All modules</option>
              {modules.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
            <select className="select" value={actionFilter} onChange={e => setActionFilter(e.target.value)} style={{ width: "auto", minWidth: 140 }}>
              <option value="">All actions</option>
              {actions.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
            <button className="btn btn-secondary btn-sm" onClick={load}>Apply</button>
            <span className="muted" style={{ marginLeft: "auto" }}>{logs.length} record{logs.length !== 1 ? "s" : ""}</span>
          </div>
        </div>
      </div>

      <div className="table-container">
        {logs.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-text">No audit records found</div>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th style={{ width: 160 }}>Timestamp</th>
                <th>User</th>
                <th>Action</th>
                <th>Module</th>
                <th>Record</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {logs.map(l => {
                const style = ACTION_STYLES[l.action] || { bg: "var(--bg-surface-elevated)", color: "var(--text-secondary)" };
                return (
                  <tr key={l.id}>
                    <td style={{ fontSize: "0.8125rem", color: "var(--muted)", whiteSpace: "nowrap" }}>
                      {l.created_at ? new Date(l.created_at + "Z").toLocaleString() : "-"}
                    </td>
                    <td style={{ fontWeight: 600 }}>{l.username || "-"}</td>
                    <td>
                      <span className="badge" style={{ background: style.bg, color: style.color }}>{l.action}</span>
                    </td>
                    <td style={{ color: "var(--text-secondary)", textTransform: "capitalize" }}>{l.module || "-"}</td>
                    <td style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", whiteSpace: "nowrap" }}>
                      {l.entity_type ? `${l.entity_type}${l.entity_id ? ` #${l.entity_id}` : ""}` : "-"}
                    </td>
                    <td style={{ color: "var(--text-secondary)", fontSize: "0.8125rem" }}>{l.details || "-"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
