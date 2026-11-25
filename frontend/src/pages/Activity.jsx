import { useCallback, useEffect, useState } from "react";
import { authFetch } from "../api";
import { actionMeta, formatDateTime, formatDelta, MOVEMENT_ACTIONS } from "../format";
import PageHeader from "../components/PageHeader";

export default function Activity() {
  const [log, setLog] = useState([]);
  const [actionFilter, setActionFilter] = useState("");
  // Action types observed in the data, accumulated across loads. The filter
  // options come from a static list, so selecting one value no longer collapses
  // the rest; this only adds types the backend reports that we don't know about.
  const [extraActions, setExtraActions] = useState([]);

  const fetchData = useCallback(() => {
    const params = new URLSearchParams({ limit: "200" });
    if (actionFilter) params.set("action_type", actionFilter);
    authFetch(`/movements?${params}`)
      .then(r => r.json())
      .then(d => {
        const rows = d.data || [];
        setLog(rows);
        setExtraActions(previous => {
          const known = new Set([...MOVEMENT_ACTIONS, ...previous]);
          const added = [];
          for (const row of rows) {
            if (row.action_type && !known.has(row.action_type)) {
              known.add(row.action_type);
              added.push(row.action_type);
            }
          }
          return added.length > 0 ? [...previous, ...added] : previous;
        });
      })
      .catch(() => {});
  }, [actionFilter]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const filterOptions = [...MOVEMENT_ACTIONS, ...extraActions];

  return (
    <section>
      <PageHeader eyebrow="Reports" title="Activity Log" subtitle="Every stock movement, newest first" />

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-body">
          <div className="toolbar">
            <label className="toolbar__label" htmlFor="activity-action">Action</label>
            <select
              id="activity-action"
              className="select"
              value={actionFilter}
              onChange={e => setActionFilter(e.target.value)}
              style={{ width: "auto", minWidth: 180 }}
            >
              <option value="">All actions</option>
              {filterOptions.map(action => (
                <option key={action} value={action}>{actionMeta(action).label}</option>
              ))}
            </select>
            <span className="muted toolbar__count" role="status">
              {log.length} record{log.length !== 1 ? "s" : ""}
            </span>
          </div>
        </div>
      </div>

      <div className="table-container" tabIndex={0} role="region" aria-label="Activity log">
        {log.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-text">
              {actionFilter ? "No activity matches this filter" : "No activity recorded yet"}
            </div>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th style={{ width: 170 }}>Timestamp</th>
                <th>Product</th>
                <th>Action</th>
                <th style={{ textAlign: "right" }}>Delta</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {log.map(l => {
                const meta = actionMeta(l.action_type);
                const delta = Number(l.delta);
                return (
                  <tr key={l.id}>
                    <td className="mono" style={{ fontSize: "0.78rem", color: "var(--muted)", whiteSpace: "nowrap" }}>
                      {formatDateTime(l.created_at)}
                    </td>
                    <td>
                      <div style={{ fontWeight: 600 }}>{l.name}</div>
                      <div className="muted mono" style={{ fontSize: "0.74rem" }}>{l.sku}</div>
                    </td>
                    <td><span className={`badge ${meta.cls}`}>{meta.label}</span></td>
                    <td style={{ textAlign: "right" }}>
                      {delta !== 0 ? (
                        <span className={`ledger-num ledger-num--${delta > 0 ? "up" : "down"}`}>
                          {formatDelta(delta)}
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td style={{ color: "var(--text-secondary)", fontSize: "0.8125rem" }}>
                      {l.reason || "—"}
                    </td>
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
