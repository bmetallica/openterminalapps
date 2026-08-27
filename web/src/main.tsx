import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode><App /></StrictMode>,
)

// Der Service Worker macht die Anwendung installierbar (siehe public/sw.js).
// Scheitert die Anmeldung — kein sicherer Kontext, Registrierung im Browser
// abgeschaltet —, ist das folgenlos: Dann fehlt nur die Verknüpfung auf dem
// Desktop, die Anwendung selbst läuft unverändert.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => { /* dann eben nicht */ })
  })
}
