// FOUC prevention for the color-scheme override. Loaded synchronously in <head>
// before the app renders, so a pinned theme is applied on the very first paint.
// Kept intentionally tiny; the rest of the theming logic loads with the app.
// CSP note: served same-origin, so it works under `script-src 'self'` without
// an inline script or a nonce.
(function () {
  try {
    var stored = localStorage.getItem("nl-color-scheme");
    if (stored === "light" || stored === "dark") {
      var meta = document.querySelector('meta[name="color-scheme"]');
      if (meta) meta.setAttribute("content", stored);
    }
  } catch {
    // localStorage can throw when site data is blocked. The page still renders
    // and follows the system preference; nothing else depends on this script.
  }
})();
