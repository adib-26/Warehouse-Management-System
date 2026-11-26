import { useEffect, useState } from "react";

const STORAGE_KEY = "nl-color-scheme";

function metaEl() {
  return document.querySelector('meta[name="color-scheme"]');
}

function readOverride() {
  const content = metaEl()?.getAttribute("content");
  return content === "light" || content === "dark" ? content : null;
}

function readSystem() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyMeta(value) {
  metaEl()?.setAttribute("content", value ?? "light dark");
}

/**
 * Two-state scheme toggle (per the dark-mode-toggle guidance): the override is
 * stored only when it diverges from the system preference, so a user can always
 * revert to "follow system" and a pinned scheme survives later system changes.
 *
 * Shown with a text label ("Dark" / "Light" names the scheme it switches to)
 * rather than an icon alone, so it is easy to find. It appears in the app
 * header and on the sign-in page.
 */
export default function ThemeToggle() {
  const [override, setOverride] = useState(readOverride);
  const [system, setSystem] = useState(readSystem);

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onSystemChange = () => setSystem(query.matches ? "dark" : "light");
    const onStorage = (event) => {
      if (event.key !== STORAGE_KEY) return;
      const next = event.newValue === "light" || event.newValue === "dark" ? event.newValue : null;
      applyMeta(next);
      setOverride(next);
    };
    query.addEventListener("change", onSystemChange);
    window.addEventListener("storage", onStorage);
    return () => {
      query.removeEventListener("change", onSystemChange);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const rendered = override ?? system;
  const next = rendered === "dark" ? "light" : "dark";

  const toggle = () => {
    try {
      if (next === system) {
        // Undo the override and follow the system preference again.
        localStorage.removeItem(STORAGE_KEY);
        applyMeta(null);
        setOverride(null);
      } else {
        localStorage.setItem(STORAGE_KEY, next);
        applyMeta(next);
        setOverride(next);
      }
    } catch {
      // Persistence may be blocked; still apply for this session.
      applyMeta(next === system ? null : next);
      setOverride(next === system ? null : next);
    }
  };

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggle}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
    >
      {rendered === "dark" ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      )}
      <span className="theme-toggle__text" aria-hidden="true">{next}</span>
    </button>
  );
}
