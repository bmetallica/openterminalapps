# ota-web

Die Oberfläche von OpenTerminalApps: React 18, TypeScript, Vite — **handgeschriebenes CSS, keine
UI-Bibliothek.**

Im Betrieb wird sie gebaut und von nginx ausgeliefert (`docker compose build web`). Für die
Entwicklung reicht Node auf dem Rechner:

```bash
npm install
npm run dev      # http://localhost:5273
npm run build
```

`npm run dev` spricht mit der **echten** API — Mock-Daten gibt es nicht mehr. Es braucht also eine
laufende Anlage; die Adresse steht in `vite.config.ts`.

Deep-Links für Screenshots und Support:
`?view=workspaces` · `&edit=<template-id>` · `&tab=ressourcen|rechte|umgebung|zuweisung`

**Zwei Regeln, an denen sich alles ausrichtet** (ausführlich in `../plan.md` §13):

* **Farbe ist Information, nie Dekoration.** Gesättigte Farbe bedeutet immer einen Zustand. Die
  Primäraktion ist deshalb bewusst unbunt.
* **Deutsch ist der Schlüssel, Englisch das Wörterbuch.** Texte stehen als `t('deutscher Text')` im
  Quelltext, die Übersetzung in `src/lib/i18n.en.ts`. Ein neuer Text gehört **immer** in beide —
  sonst erscheint er in der englischen Oberfläche auf Deutsch.

Die Schriften (Archivo, IBM Plex Mono) liegen unter `public/fonts/` und werden mitgeliefert. **Es
wird nichts von fremden Hosts nachgeladen** — das ist Absicht und darf nicht zurückgedreht werden.
