# ADR-001 · Der Arbeitsplatz ist das Fundament, Einzel-Apps sind ein Feature

**Stand:** angenommen
**Datum:** 2026-08-27

## Ausgangslage

Kasm Workspaces gibt jedem Start einen eigenen Wegwerf-Container mit genau einer Anwendung darin.
Das ist sauber und für viele Zwecke richtig — aber es zerlegt die Arbeit eines Menschen in Inseln.
Wer in VS Code ein Projekt auscheckt und es im Terminal bauen will, hat zwei Container, zwei
Dateisysteme, zwei SSH-Schlüssel und keine gemeinsame Zwischenablage. Der Umweg über einen
Netzwerkspeicher ist möglich und fühlt sich jeden Tag falsch an.

Die Frage war also nicht „wie baue ich Kasm nach", sondern: Was ist die kleinste Einheit, die ein
Mensch als *seinen Arbeitsplatz* erkennt?

## Entscheidung

**Ein Container je Nutzer**, darin alle seine Werkzeuge, jedes einzeln formatfüllend in den Browser
gestreamt. Einzelne Anwendungen als Wegwerf-Container bleiben möglich — als Zusatz, nicht als
Fundament.

## Alternativen

**Ein Container je Anwendung** (der Kasm-Weg). Besser isoliert, klarer im Ressourcenmodell, und für
das eine seltene Werkzeug genau richtig. Aber das gemeinsame `/home` ist nicht nachrüstbar: Es
zwischen Containern zu teilen bedeutet gleichzeitige Schreibzugriffe auf dieselben Konfigurationen,
und genau daran scheitert es in der Praxis — zwei VS-Code-Instanzen auf einem Profil ist kein
Grenzfall, sondern der Normalfall.

**Ein Desktop je Nutzer, Anwendungen darin per Fenstermanager.** Das ist der klassische
VDI-Ansatz. Er funktioniert, aber der Browser-Tab zeigt dann einen Desktop im Desktop, mit zwei
Taskleisten, zwei Zwischenablagen und einer Auflösung, die nie passt. OTA bietet den XFCE-Desktop
als *zusätzliche* Ansicht an, nicht als Hauptweg.

## Folgen

**Teuer:** Ein Container je Nutzer ist teurer als einer je Session, weil er auch dann steht, wenn
nur eine Anwendung offen ist. Dagegen hilft, dass Anwendungen erst bei Bedarf starten — ein
Arbeitsplatz mit einem offenen Terminal kostet fast nichts.

**Schwächere Isolation.** Alle Werkzeuge eines Nutzers teilen einen Kernel-Namespace. Zwischen
Nutzern trennt weiterhin der Container; innerhalb eines Nutzers nicht. Das ist bewusst: Es ist sein
Rechner.

**Ein eigener Displaymanager.** Ein Container mit mehreren `Xvnc`-Instanzen und einer Displayvergabe
gibt es nicht von der Stange. Das ist der Teil von OTA, den sonst niemand baut — und der Grund,
warum es OTA gibt.

**Das Golden Image wird wichtig.** Wenn alle Werkzeuge in einem Image liegen, ist dessen Pflege
kein Nebenschauplatz mehr. Daher die Build-Pipeline, die Rezepte und die App-Erkennung
([Handbuch, Kapitel 7](../wiki/07-golden-images.md)).
