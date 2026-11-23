import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../AuthContext";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{
      minHeight: "100vh",
      display: "grid",
      placeItems: "center",
      padding: 24,
    }}>
      <div className="card" style={{ width: "100%", maxWidth: 400 }}>
        <div className="card-body" style={{ padding: 32 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 24 }}>
            <div style={{
              width: 42,
              height: 42,
              borderRadius: 10,
              background: "linear-gradient(135deg, #3b82f6, #2563eb)",
              display: "grid",
              placeItems: "center",
              fontWeight: 800,
              color: "white",
              fontSize: "0.85rem",
              boxShadow: "0 2px 8px rgba(37, 99, 235, 0.3)",
            }}>
              NL
            </div>
            <div>
              <div style={{ fontSize: "1.0625rem", fontWeight: 700 }}>NovaLedger</div>
              <div style={{ fontSize: "0.8rem", color: "var(--muted)" }}>Sign in to continue</div>
            </div>
          </div>

          {error && (
            <div className="alert alert-error" style={{ marginBottom: 16 }}>
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="input-group">
              <label className="input-label">Username</label>
              <input
                className="input"
                value={username}
                onChange={e => setUsername(e.target.value)}
                autoFocus
                autoComplete="username"
                required
              />
            </div>
            <div className="input-group">
              <label className="input-label">Password</label>
              <input
                className="input"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
            <button type="submit" className="btn btn-primary" disabled={submitting || !username || !password} style={{ marginTop: 6 }}>
              {submitting ? "Signing in..." : "Sign In"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
