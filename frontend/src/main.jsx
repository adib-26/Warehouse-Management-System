import React from "react"
import ReactDOM from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
// Self-hosted variable fonts (bundled as same-origin assets, font-display: swap).
// The `standard` Archivo variant adds the width axis used by the condensed wordmark.
import "@fontsource-variable/archivo/standard.css"
import "@fontsource-variable/jetbrains-mono"
// Saira (width + weight axes) is the condensed display face for headings,
// the wordmark, and the dashboard's hero figures.
import "@fontsource-variable/saira/wdth.css"
import App from "./App"
import "./index.css"

ReactDOM.createRoot(document.getElementById("root")).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>
)
