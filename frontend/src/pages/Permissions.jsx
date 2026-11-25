import { useEffect, useState } from "react";
import { authFetch } from "../api";
import { useAuth } from "../AuthContext";
import { useToast } from "../components/FeedbackProvider";
import { responseErrorMessage } from "../format";
import PageHeader from "../components/PageHeader";

const ACTIONS = ["read", "write", "delete"];

export default function Permissions() {
  const { can } = useAuth();
  const toast = useToast();
  const [roles, setRoles] = useState([]);
  const [modules, setModules] = useState([]);
  const [matrix, setMatrix] = useState({});
  const [saving, setSaving] = useState(false);
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
        toast.success("Permission matrix saved. Changes take effect immediately.");
        load();
      } else {
        toast.error(responseErrorMessage(data, "Could not save permissions."));
      }
    } catch {
      toast.error("Could not reach the API.");
    } finally {
      setSaving(false);
    }
  };

  const canWrite = can("admin", "write");

  return (
    <section>
      <PageHeader
        eyebrow="Administration"
        title="Permissions"
        subtitle="What each role can do"
        actions={canWrite && (
          <>
            {dirty && <span className="dirty-flag">Unsaved changes</span>}
            <button className="btn btn-primary btn-sm" onClick={save} disabled={saving || !dirty}>
              {saving ? "Saving..." : "Save Changes"}
            </button>
          </>
        )}
      />

      <div className="table-container" tabIndex={0} role="region" aria-label="Permission matrix">
        <table className="perm-grid">
          <thead>
            <tr>
              <th rowSpan={2} scope="col">Module</th>
              {roles.map(role => (
                <th key={role} colSpan={ACTIONS.length} scope="colgroup" className="perm-role">{role}</th>
              ))}
            </tr>
            <tr>
              {roles.flatMap(role => ACTIONS.map((action, index) => (
                <th
                  key={`${role}-${action}`}
                  scope="col"
                  className={`perm-sub${index === 0 ? " perm-sub--first" : ""}`}
                >
                  {action}
                </th>
              )))}
            </tr>
          </thead>
          <tbody>
            {modules.map(module => (
              <tr key={module}>
                <th scope="row">{module}</th>
                {roles.flatMap(role => {
                  const p = matrix[`${role}:${module}`] || {};
                  // Admin access to the admin module stays on to prevent lockout.
                  const locked = role === "admin" && module === "admin";
                  return ACTIONS.map((action, index) => (
                    <td
                      key={`${role}-${action}`}
                      className={`perm-cell${index === 0 ? " perm-cell--first" : ""}`}
                    >
                      <input
                        type="checkbox"
                        className="tickbox"
                        checked={!!p[action]}
                        disabled={locked || !canWrite}
                        aria-label={`${role} can ${action} ${module}`}
                        title={locked ? "Locked to prevent administrator lockout" : undefined}
                        onChange={() => toggle(role, module, action)}
                      />
                    </td>
                  ));
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="muted" style={{ marginTop: 12, fontSize: "0.8125rem" }}>
        Administrator access to the Administration module is locked to prevent lockout.
      </p>
    </section>
  );
}
