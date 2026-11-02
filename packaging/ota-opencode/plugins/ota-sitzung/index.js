// ota-sitzung — ein opencode-Plugin von OpenTerminalApps (Handbuch Kapitel 39).
//
// Erweiterungen von OTA (etwa das Gedächtnis) müssen wissen, in welcher
// opencode-Sitzung ein Werkzeug aufgerufen wird. Das Modell kennt seine
// Sitzungskennung nicht, und die MCP-Verbindung gehört zum opencode-Prozess,
// nicht zur Sitzung. Deshalb setzt dieses Plugin vor jedem Aufruf eines
// Werkzeugs der genannten MCP-Server (`options.server`) die Felder
//
//   ota_sitzung      die Wurzelsitzung: Kind-Sitzungen (Unteragenten) und
//                    Forks werden auf ihren Ursprung abgebildet — dieselbe
//                    Regel, die opencode intern nutzt (parentID, sonst
//                    fork.sessionID, sonst die Sitzung selbst)
//   ota_titel        der Titel der Wurzelsitzung, für die Anzeige in OTA
//   ota_verzeichnis  ihr Verzeichnis, ebenso
//
// und überschreibt dabei, was das Modell dort eingetragen hat. Für das Modell
// blendet es die Felder aus der Beschreibung der Werkzeuge aus. Es schickt
// selbst nichts irgendwohin.
//
// Geschrieben gegen die Plugin-Schnittstelle von opencode 2.2 (V2, Promise).
// scripts/test-opencode.sh prüft es gegen die festgelegte Fassung.

const FELDER = ["ota_sitzung", "ota_titel", "ota_verzeichnis"]

export default {
  id: "ota.sitzung",
  setup: async (ctx) => {
    const server = Array.isArray(ctx.options?.server) ? ctx.options.server.map(String) : []
    if (!server.length) return
    const betroffen = (name) => typeof name === "string" && server.some((s) => name.startsWith(s + "_"))
    const wurzeln = new Map()

    async function wurzel(id) {
      if (wurzeln.has(id)) return wurzeln.get(id)
      const kette = [id]
      let info = await ctx.session.get({ sessionID: id })
      for (let i = 0; i < 32; i++) {
        const weiter = info.parentID ?? info.fork?.sessionID
        if (!weiter || kette.includes(weiter)) break
        kette.push(weiter)
        info = await ctx.session.get({ sessionID: weiter })
      }
      const w = { id: info.id, titel: info.title ?? "", verzeichnis: info.location?.directory ?? "" }
      // Titel ändern sich (opencode vergibt ihn nach der ersten Antwort):
      // nur kurz merken.
      for (const k of kette) wurzeln.set(k, w)
      setTimeout(() => { for (const k of kette) wurzeln.delete(k) }, 60_000).unref?.()
      return w
    }

    await ctx.session.hook("context", (event) => {
      for (const [name, tool] of Object.entries(event.tools ?? {})) {
        if (!betroffen(name) || !tool?.input?.properties) continue
        const properties = { ...tool.input.properties }
        for (const f of FELDER) delete properties[f]
        const input = { ...tool.input, properties }
        if (Array.isArray(tool.input.required)) input.required = tool.input.required.filter((f) => !FELDER.includes(f))
        tool.input = input
      }
    })

    await ctx.tool.hook("execute.before", async (event) => {
      if (!betroffen(event.tool)) return
      const w = await wurzel(event.sessionID)
      const eingabe = event.input && typeof event.input === "object" ? event.input : {}
      event.input = { ...eingabe, ota_sitzung: w.id, ota_titel: w.titel, ota_verzeichnis: w.verzeichnis }
    })
  },
}
