import { useEffect, useState } from "react";
import { authFetch } from "../api";
import { useAuth } from "../AuthContext";

const ACTIONS = ["read", "write", "delete"];

export default function Permissions() {
  const { can } = useAuth();
  const [roles, setRoles] = useState([]);
  const [modules, setModules] = useState([]);
  const [matrix, setMatrix] = useState({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const [dirty, setDirty] = useState(false);

  const load = () => {
    authFetch("/admin/permissions")
      .then(r => r.json())
      .then(data => {
        setRoles(data.roles);
        setModules(data.modules);
        const m = {};
        for (const e of data.entries) {
          m[`${e.role}:${e.module}`] = {
            read: !!e.can_read,
            write: !!e.can_write,
            delete: !!e.can_delete,
          };
        }
        setMatrix(m);
        setDirty(false);
      })
      .catch(() => {});
  };

  useEffect(() => { load(); }, []);

  const toggle = (role, module, action) => {
    const key = `${role}:${module}`;
    setMatrix(prev => ({
      ...prev,
      [key]: { ...prev[key], [action]: !prev[key]?.[action] },
    }));
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const entries = [];
      for (const role of roles) {
        for (const module of modules) {
          const p = matrix[`${role}:${module}`] || { read: false, write: false, delete: false };
          entries.push({ role, module, can_read: p.read, can_write: p.write, can_delete: p.delete });
        }
      }
      const res = await authFetch("/admin/permissions", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entries }),
      });
      const data = await res.json();
      if (res.ok) {
        setMessage({ type: "success", text: "Permission matrix saved. Changes take effect immediately." });
        load();
      } else {
        setMessage({ type: "error", text: data.detail || "Could not save permissions." });
      }
    } catch {
      setMessage({ type: "error", text: "Could not reach the API." });
    } finally {
      setSaving(false);
    }
  };

  const canWrite = can("admin", "write");

  return (
    <section>
      <div className="page-header">
        <div>
          <h1 className="page-title">Permissions</h1>
          <p className="page-subtitle">Read / write / delete access per role and module</p>
        </div>
        {canWrite && (
          <button className="btn btn-primary btn-sm" onClick={save} disabled={saving || !dirty}>
            {saving ? "Saving..." : "Save Changes"}
          </button>
        )}
      </div>

      {message && (
        <div className={`alert alert-${message.type}`} style={{ marginBottom: 20 }}>
          <span>{message.text}</span>
          <button className="btn btn-ghost btn-xs" style={{ padding: "2px 8px" }} onClick={() => setMessage(null)}>&times;</button>
        </div>
      )}

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Module</th>
              {roles.map(r => (
                <th key={r} style={{ textAlign: "center", textTransform: "capitalize" }}>{r}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {modules.map(module => (
              <tr key={module}>
                <td style={{ fontWeight: 600, textTransform: "capitalize" }}>{module}</td>
                {roles.map(role => {
                  const p = matrix[`${role}:${module}`] || {};
                  const locked = role === "admin" && module === "admin";
                  return (
                    <td key={role} style={{ textAlign: "center" }}>
                      <div style={{ display: "inline-flex", gap: 12 }}>
                        {ACTIONS.map(action => (
                          <label key={action} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3, fontSize: "0.65rem", color: "var(--muted)", cursor: locked || !canWrite ? "not-allowed" : "pointer" }}>
                            <input
                              type="checkbox"
                              checked={!!p[action]}
                              disabled={locked || !canWrite}
                              onChange={() => toggle(role, module, action)}
                              style={{ accentColor: "var(--accent)" }}
                            />
                            {action.charAt(0).toUpperCase()}
                          </label>
                        ))}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="muted" style={{ marginTop: 12, fontSize: "0.8125rem" }}>
        R = read, W = write, D = delete. Admin access to the admin module is locked to prevent lockout.
      </p>
    </section>
  );
}
