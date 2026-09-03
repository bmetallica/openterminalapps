/* Die Anmeldemaske folgt dem Gewand, das der Mensch in OTA gewählt hat.
   ======================================================================
   Warum das überhaupt geht: Keycloak liegt hinter demselben Ingress wie OTA,
   also auf derselben Herkunft — und damit liest diese Seite denselben
   `localStorage`, in dem `web/src/lib/theme.ts` die Wahl ablegt.

   Warum es sein muss: Ohne das bekäme jemand mit hellem Gewand eine dunkle
   Anmeldemaske und danach eine helle Anwendung. Das sieht nicht nach einer
   Anlage aus, sondern nach zweien — und genau diesen Zweifel darf eine
   Anmeldeseite nie auslösen.

   Warum ohne Framework und ohne await: Das Skript läuft im <head> und soll
   fertig sein, bevor irgendetwas gemalt wird. Alles andere blitzt kurz in
   der falschen Farbe auf.
   ====================================================================== */
(function () {
  var wahl = 'dunkel';
  try {
    var g = localStorage.getItem('ota.theme');
    if (g === 'hell' || g === 'dunkel' || g === 'system') wahl = g;
  } catch (e) {
    /* privater Modus — dann bleibt es bei der Vorgabe */
  }
  if (wahl === 'system') {
    wahl = (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches)
      ? 'hell' : 'dunkel';
  }
  // Nur bei Hell ein Attribut setzen. Dunkel ist die Grundfarbe der Datei;
  // ein Attribut dafür wäre eine zweite Wahrheit — dieselbe Regel wie in
  // web/src/lib/theme.ts.
  if (wahl === 'hell') document.documentElement.setAttribute('data-ota-gewand', 'hell');

  // Und dieselbe Überlegung für die Marke: Wer seiner Anlage eine eigene
  // Farbe gegeben hat, soll sie auch auf der Anmeldemaske sehen. OTA legt sie
  // beim Laden im localStorage ab (`web/src/lib/branding.ts`); von dort ist
  // sie hier synchron lesbar, ohne Anfrage und ohne Aufblitzen. Wer diese
  // Anlage noch nie geöffnet hat, sieht beim ersten Mal die Vorgabe — das ist
  // der Preis dafür, nicht auf ein `fetch` zu warten, und er ist es wert.
  try {
    var marke = JSON.parse(localStorage.getItem('ota.marke') || '{}');
    if (/^#[0-9A-Fa-f]{6}$/.test(marke.accent || '')) {
      // Auf heller Fläche braucht dieselbe Farbe mehr Tiefe — derselbe
      // Sprung wie in `branding.ts` und im Stylesheet der Anwendung.
      var f = wahl === 'hell' ? 0.7 : 1;
      var n = parseInt(marke.accent.slice(1), 16);
      var teil = function (v) { return Math.round(Math.min(255, v * f)); };
      var hex = function (v) { return ('0' + v.toString(16)).slice(-2); };
      document.documentElement.style.setProperty('--ota-accent',
        '#' + hex(teil((n >> 16) & 255)) + hex(teil((n >> 8) & 255)) + hex(teil(n & 255)));
    }
  } catch (e) {
    /* keine Marke hinterlegt — dann bleibt es beim Kühlblau */
  }
})();
