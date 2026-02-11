// src/ErrorBoundary.jsx
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
    // Optional: send error and errorInfo to a logging service
    // Example: sendToLoggingService({ error, errorInfo });
  }

  render() {
    if (this.state.hasError) {
      return (
        <main role="alert" style={{ padding: 24 }}>
          <div style={{
            maxWidth: 800,
            margin: "0 auto",
            background: "#fff",
            borderRadius: 8,
            boxShadow: "0 2px 10px rgba(0,0,0,0.08)",
            padding: 20
          }}>
            <h1 style={{ margin: 0, fontSize: 20 }}>Something went wrong</h1>
            <p style={{ marginTop: 8, color: "#444" }}>
              An unexpected error occurred. Try refreshing the page.
            </p>
            <details style={{ marginTop: 12, color: "#666" }}>
              <summary style={{ cursor: "pointer" }}>Error details</summary>
              <pre style={{ whiteSpace: "pre-wrap", marginTop: 8 }}>
                {String(this.state.error)}
                {this.state.errorInfo ? `\n\n${this.state.errorInfo.componentStack}` : ""}
              </pre>
            </details>
          </div>
        </main>
      );
    }

    return this.props.children;
  }
}
