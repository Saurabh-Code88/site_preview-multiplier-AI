const TOKEN_KEY = "sp_token";
const EMAIL_KEY = "sp_email";

export const session = {
  get token() { return localStorage.getItem(TOKEN_KEY); },
  get email() { return localStorage.getItem(EMAIL_KEY); },
  save(token, email) { localStorage.setItem(TOKEN_KEY, token); localStorage.setItem(EMAIL_KEY, email); },
  clear() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(EMAIL_KEY); },
};

async function request(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (session.token) headers.Authorization = `Bearer ${session.token}`;
  const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(formatError(data) || "Something went wrong.");
    err.status = res.status;
    throw err;
  }
  return data;
}

// FastAPI returns {detail: "msg"} or {detail: [{msg, loc}, ...]} for validation errors.
function formatError(data) {
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map((d) => (d.loc?.includes("password") ? "Password must be at least 8 characters." : d.msg)).join(" ");
  }
  return "";
}

export const api = {
  signup: (email, password) => request("/api/auth/signup", { method: "POST", body: { email, password } }),
  login: (email, password) => request("/api/auth/login", { method: "POST", body: { email, password } }),
  me: () => request("/api/me"),
  sites: () => request("/api/sites"),
  addSite: (url) => request("/api/sites", { method: "POST", body: { url } }),
  retry: (id) => request(`/api/sites/${id}/retry`, { method: "POST" }),
  remove: (id) => request(`/api/sites/${id}`, { method: "DELETE" }),
};
