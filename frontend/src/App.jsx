import { useEffect, useState } from "react";
import { api, session } from "./api.js";

export default function App() {
  const [email, setEmail] = useState(session.token ? session.email : null);

  // Validate any stored token on load; drop it if the server rejects it.
  useEffect(() => {
    if (!session.token) return;
    api.me().then((u) => setEmail(u.email)).catch(() => { session.clear(); setEmail(null); });
  }, []);

  const signOut = () => { session.clear(); setEmail(null); };

  return email ? <Dashboard email={email} onSignOut={signOut} /> : <AuthScreen onAuthed={setEmail} />;
}

/* ---------------- auth ---------------- */

function AuthScreen({ onAuthed }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const isSignup = mode === "signup";

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const fn = isSignup ? api.signup : api.login;
      const { token, email } = await fn(form.email, form.password);
      session.save(token, email);
      onAuthed(email);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth">
      <div className="auth-panel">
        <h1>Site Previewer</h1>
        <p className="lede">Paste a link, get a picture of the page, and keep it for later.</p>
        <form onSubmit={submit}>
          <label>
            Email
            <input type="email" required autoComplete="email" value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </label>
          <label>
            Password
            <input type="password" required minLength={8}
              autoComplete={isSignup ? "new-password" : "current-password"} value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })} />
            {isSignup && <span className="hint">At least 8 characters.</span>}
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="primary" disabled={busy}>
            {busy ? "Please wait…" : isSignup ? "Create account" : "Log in"}
          </button>
        </form>
        <p className="switch">
          {isSignup ? "Already have an account?" : "New here?"}{" "}
          <button className="link" onClick={() => { setMode(isSignup ? "login" : "signup"); setError(""); }}>
            {isSignup ? "Log in" : "Create an account"}
          </button>
        </p>
      </div>
    </main>
  );
}

/* ---------------- dashboard ---------------- */

function Dashboard({ email, onSignOut }) {
  const [url, setUrl] = useState("");
  const [sites, setSites] = useState([]);
  const [latest, setLatest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const handleAuthError = (err) => { if (err.status === 401) onSignOut(); };

  useEffect(() => {
    api.sites().then(setSites).catch(handleAuthError).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const site = await api.addSite(url);
      setLatest(site);
      setSites((prev) => [site, ...prev]);
      setUrl("");
    } catch (err) {
      handleAuthError(err);
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const replace = (site) => {
    setSites((prev) => prev.map((s) => (s.id === site.id ? site : s)));
    setLatest((l) => (l && l.id === site.id ? site : l));
  };
  const retry = async (id) => { try { replace(await api.retry(id)); } catch (err) { handleAuthError(err); } };
  const remove = async (id) => {
    try {
      await api.remove(id);
      setSites((prev) => prev.filter((s) => s.id !== id));
      setLatest((l) => (l && l.id === id ? null : l));
    } catch (err) { handleAuthError(err); }
  };

  return (
    <div className="shell">
      <header className="topbar">
        <strong>Site Previewer</strong>
        <span className="who">{email}</span>
        <button className="link" onClick={onSignOut}>Log out</button>
      </header>

      <main>
        <form className="url-form" onSubmit={submit}>
          <label htmlFor="url">Website URL</label>
          <div className="row">
            <input id="url" type="text" inputMode="url" required placeholder="https://example.com/page"
              value={url} onChange={(e) => setUrl(e.target.value)} disabled={busy} />
            <button className="primary" disabled={busy}>{busy ? "Capturing…" : "Preview and save"}</button>
          </div>
          {busy && <p className="hint">Loading the page in a browser. This can take up to 30 seconds.</p>}
          {error && <p className="error" role="alert">{error}</p>}
        </form>

        {latest && (
          <section className="latest" aria-label="Latest preview">
            <h2>Just saved</h2>
            <SiteCard site={latest} large onRetry={retry} onRemove={remove} />
          </section>
        )}

        <section aria-label="Saved sites">
          <h2>Saved sites {sites.length > 0 && <span className="count">{sites.length}</span>}</h2>
          {loading ? <p className="hint">Loading…</p>
            : sites.length === 0 ? <p className="empty">Nothing saved yet. Enter a URL above to capture your first preview.</p>
            : <div className="grid">
                {sites.map((s) => <SiteCard key={s.id} site={s} onRetry={retry} onRemove={remove} />)}
              </div>}
        </section>
      </main>
    </div>
  );
}

function SiteCard({ site, large, onRetry, onRemove }) {
  const [retrying, setRetrying] = useState(false);
  const host = (() => { try { return new URL(site.url).hostname; } catch { return site.url; } })();

  const doRetry = async () => { setRetrying(true); await onRetry(site.id); setRetrying(false); };

  return (
    <article className={`card ${large ? "large" : ""}`}>
      <a className="shot" href={site.preview_url || site.url} target="_blank" rel="noreferrer"
        aria-label={`Open preview of ${host}`}>
        {site.preview_url
          ? <img src={site.preview_url} alt={`Screenshot of ${site.title || host}`} loading="lazy" />
          : <div className="noshot">No preview available</div>}
      </a>
      {site.message && <p className={`notice ${site.status}`}>{site.message}</p>}
      <div className="meta">
        <div className="titles">
          <span className="title">{site.title || host}</span>
          <a className="url" href={site.url} target="_blank" rel="noreferrer" title={site.url}>{site.url}</a>
          <time dateTime={site.created_at}>{new Date(site.created_at).toLocaleString()}</time>
        </div>
        <div className="actions">
          {site.status !== "ok" && <button className="link" onClick={doRetry} disabled={retrying}>{retrying ? "Retrying…" : "Retry"}</button>}
          <button className="link danger" onClick={() => onRemove(site.id)}>Delete</button>
        </div>
      </div>
    </article>
  );
}
