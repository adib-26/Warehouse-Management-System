import React from "react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
  }

  render() {
    if (this.state.hasError) {
      return (
        <main role="alert" style={{ padding: 24 }}>
          <div className="card" style={{ maxWidth: 700, margin: "40px auto" }}>
            <div className="card-body" style={{ padding: 32 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
                <div style={{
                  width: 40,
                  height: 40,
                  borderRadius: 10,
                  background: "var(--red-bg)",
                  display: "grid",
                  placeItems: "center",
                  color: "var(--red)",
                  fontSize: 20,
                }}>
                  !
                </div>
                <div>
                  <h1 style={{ margin: 0, fontSize: "1.125rem", fontWeight: 700 }}>Something went wrong</h1>
                  <p className="muted" style={{ margin: "4px 0 0" }}>An unexpected error occurred.</p>
                </div>
              </div>
              <details style={{ marginTop: 12 }}>
                <summary style={{ cursor: "pointer", color: "var(--muted)", fontSize: "0.875rem" }}>Error details</summary>
                <pre style={{
                  whiteSpace: "pre-wrap",
                  marginTop: 8,
                  padding: 16,
                  borderRadius: "var(--radius-sm)",
                  background: "var(--bg-surface-elevated)",
                  fontSize: "0.8125rem",
                  color: "var(--text-secondary)",
                  overflow: "auto",
                }}>
                  {String(this.state.error)}
                  {this.state.errorInfo ? `\n\n${this.state.errorInfo.componentStack}` : ""}
                </pre>
              </details>
              <button className="btn btn-primary btn-sm" style={{ marginTop: 16 }} onClick={() => window.location.reload()}>
                Reload Page
              </button>
            </div>
          </div>
        </main>
      );
    }

    return this.props.children;
  }
}
