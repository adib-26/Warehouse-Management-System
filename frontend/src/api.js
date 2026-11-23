const apiBase = (import.meta.env.VITE_API_URL || "").replace(/\/+$/, "");
export const API_ROOT = apiBase;
export const API = `${apiBase}/v1`;

export function getToken() {
  return localStorage.getItem("token");
}

export function setToken(token) {
  if (token) localStorage.setItem("token", token);
  else localStorage.removeItem("token");
}

export async function authFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API}${path}`, { ...options, headers });

  if (res.status === 401) {
    setToken(null);
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }
  return res;
}

export async function downloadAttachment(id, filename) {
  const res = await authFetch(`/attachments/${id}`);
  if (!res.ok) return;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "attachment";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
