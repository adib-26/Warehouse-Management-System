import { createContext, useContext, useEffect, useState } from "react";
import { API, authFetch, getToken, setToken } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [permissions, setPermissions] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getToken()) {
      setLoading(false);
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
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Login failed");
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

export function useAuth() {
  return useContext(AuthContext);
}
