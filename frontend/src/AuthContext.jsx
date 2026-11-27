import { createContext, useContext, useEffect, useState } from "react";
import { API, authFetch, getToken, setToken } from "./api";
import { responseErrorMessage } from "./format";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [permissions, setPermissions] = useState({});
  const [loading, setLoading] = useState(() => Boolean(getToken()));

  useEffect(() => {
    if (!getToken()) {
      return;
    }
    authFetch("/auth/me")
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (data) {
          setUser(data.user);
          setPermissions(data.permissions);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const login = async (username, password) => {
    const res = await fetch(`${API}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (res.status === 429) {
      throw new Error("Too many sign-in attempts. Wait a minute, then try again.");
    }
    // The proxy can answer with HTML (for example 502 while the API restarts).
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(responseErrorMessage(data, "Login failed"));
    setToken(data.token);
    setUser(data.user);
    setPermissions(data.permissions);
    return data;
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    setPermissions({});
  };

  const can = (module, action) => !!permissions?.[module]?.[action];

  return (
    <AuthContext.Provider value={{ user, permissions, loading, login, logout, can }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  return useContext(AuthContext);
}
