import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../AuthContext";
import BrandMark from "../components/BrandMark";
import InlineAlert from "../components/InlineAlert";
import ThemeToggle from "../components/ThemeToggle";

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
    <div className="login">
      <header className="login__brand">
        <BrandMark size={76} />
        <p className="login__wordmark">
          <span className="wordmark__nova">Nova</span><span className="wordmark__ledger">Ledger</span>
        </p>
        <p className="login__tagline">Warehouse management</p>
        <div className="hazard-stripe login__edge" aria-hidden="true" />
      </header>

      <main className="login__main">
        <div className="login__theme"><ThemeToggle /></div>
        <div className="login__box">
          <h1 className="login__title">Sign in</h1>
          <p className="login__hint">Use your NovaLedger username and password.</p>

          <InlineAlert style={{ marginBottom: 16 }}>{error}</InlineAlert>

          <form onSubmit={handleSubmit} className="login__form">
            <div className="input-group">
              <label className="input-label" htmlFor="login-username">Username</label>
              <input
                id="login-username"
                className="input"
                value={username}
                onChange={e => setUsername(e.target.value)}
                autoFocus
                autoComplete="username"
                required
              />
            </div>
            <div className="input-group">
              <label className="input-label" htmlFor="login-password">Password</label>
              <input
                id="login-password"
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
      </main>
    </div>
  );
}
