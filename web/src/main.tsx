import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { ladeMarke } from './lib/branding'

// Erst die Marke, dann das erste Bild. Ein Logo, das eine Zehntelsekunde
// später umspringt, sieht aus wie ein Fehler — und die Anmeldemaske ist genau
// der Bildschirm, auf dem das jedem auffiele. Scheitert der Aufruf, wird
// trotzdem gezeichnet: dann eben mit der Vorgabe.
void ladeMarke().finally(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode><App /></StrictMode>,
  )
})

// Der Service Worker macht die Anwendung installierbar (siehe public/sw.js).
// Scheitert die Anmeldung — kein sicherer Kontext, Registrierung im Browser
// abgeschaltet —, ist das folgenlos: Dann fehlt nur die Verknüpfung auf dem
// Desktop, die Anwendung selbst läuft unverändert.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => { /* dann eben nicht */ })
  })
}
