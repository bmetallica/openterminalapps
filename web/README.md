# ota-web

Oberflächen-Entwurf für OpenTerminalApps. Läuft gegen Mock-Daten aus `src/mock/data.ts`,
die den echten Host RAG spiegeln (Images, Nutzer, 4 Kerne / 15 GB).

```bash
npm install
npm run dev      # http://localhost:5273
npm run build
```

Deep-Links für Screenshots und Support:
`?view=workspaces` · `&edit=<template-id>` · `&tab=ressourcen|rechte|umgebung|zuweisung`

Gestaltung siehe `../plan.md` §11. Die Regel, an der sich alles ausrichtet:
**Farbe ist Information.** Gesättigte Farbe bedeutet immer einen Zustand, nie Dekoration.
