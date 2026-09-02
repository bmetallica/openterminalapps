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
})();
