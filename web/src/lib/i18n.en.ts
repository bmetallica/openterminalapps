/**
 * Englische Übersetzungen. Schlüssel ist der deutsche Satz — siehe `i18n.ts`.
 *
 * Was hier fehlt, erscheint auf Deutsch. Das ist der gewollte Rückfall und
 * kein Fehler: Eine fehlende Zeile macht die Oberfläche zweisprachig, aber
 * nie unlesbar.
 *
 * Enthalten sind auch die Meldungen, die der Server schickt. Sie laufen durch
 * dieselbe Tabelle (siehe `call()` in `api.ts`), damit ein Fehler nicht
 * plötzlich auf Deutsch dasteht, während der Rest der Seite Englisch spricht.
 */

export const EN: Record<string, string> = {
  // ---------------------------------------------------------------- Rahmen
  'OpenTerminalApps startet…': 'Starting OpenTerminalApps…',
  'Willkommen, {name}': 'Welcome, {name}',
  'Hauptnavigation': 'Main navigation',
  'Abmelden ({name})': 'Sign out ({name})',
  'Abmelden': 'Sign out',
  '{free} GB von {total} GB frei': '{free} GB of {total} GB free',
  'frei': 'free',
  'Sprache': 'Language',
  'Verwaltung': 'Administration',
  'Ansicht': 'View',
  'Wird geladen…': 'Loading…',
  'Wird gespeichert…': 'Saving…',
  'Erneut versuchen': 'Try again',
  'Abbrechen': 'Cancel',
  'Verwerfen': 'Discard',
  'Speichern': 'Save',
  'Löschen': 'Delete',
  'Schliessen': 'Close',
  'Verstanden': 'Got it',
  'Name': 'Name',
  'Wert': 'Value',
  'Status': 'Status',
  'Art': 'Type',
  'Zeitpunkt': 'Time',
  'Nutzer': 'User',
  'Gruppe': 'Group',
  'Gruppen': 'Groups',
  'Workspace': 'Workspace',
  'Ressourcen': 'Resources',
  'Rechte': 'Permissions',
  'Grösse': 'Size',
  'Ausgelöst': 'Triggered by',
  'Bitte wählen': 'Please choose',
  'Suchen…': 'Search…',
  'Auswahl durchsuchen': 'Search the options',
  'Nichts gefunden für „{q}"': 'Nothing found for “{q}”',
  'Zeile {n} entfernen': 'Remove row {n}',
  'geerbt von {source}': 'inherited from {source}',
  'zurücksetzen': 'reset',
  'Vorlage': 'workspace',

  // ------------------------------------------------------------- Anmeldung
  'Melde dich an, um deinen Arbeitsplatz zu öffnen.': 'Sign in to open your workspace.',
  'Benutzername': 'Username',
  'Passwort': 'Password',
  'Code aus deiner App': 'Code from your app',
  'Wird geprüft…': 'Checking…',
  'Anmelden': 'Sign in',
  'Anmeldung fehlgeschlagen': 'Sign-in failed',
  'Passwort ändern': 'Change password',
  'Dein Konto wurde mit einem Einmal-Passwort angelegt. Bitte vergib ein eigenes.':
    'Your account was created with a one-time password. Please choose your own.',
  'Aktuelles Passwort': 'Current password',
  'Neues Passwort': 'New password',
  'Mindestens 12 Zeichen.': 'At least 12 characters.',
  'Passwort setzen': 'Set password',
  'Passwort geändert': 'Password changed',
  'Wechsel fehlgeschlagen': 'Change failed',

  // ------------------------------------------------------------- Dashboard
  'Noch wach': 'Still up',
  'Guten Morgen': 'Good morning',
  'Guten Tag': 'Hello',
  'Guten Abend': 'Good evening',
  'Angemeldet als {name}': 'Signed in as {name}',
  'Deine Sessions': 'Your sessions',
  'Deine Apps': 'Your apps',
  'Keine Session läuft': 'No session running',
  'Wähle unten eine App. Der erste Start dauert etwas länger, danach bleibt deine Umgebung erhalten.':
    'Pick an app below. The first start takes a little longer; after that your environment is kept.',
  'Dir ist noch nichts zugewiesen': 'Nothing assigned to you yet',
  'Wende dich an deine Administration — dort kann dir ein Arbeitsplatz freigeschaltet werden.':
    'Ask your administrators — they can give you access to a workspace.',
  'bereit': 'ready',
  'eingefroren': 'frozen',
  '{app} anzeigen': 'Show {app}',
  '{app} starten': 'Start {app}',
  'startet': 'starting',
  'startet…': 'starting…',
  'läuft': 'running',
  'Laufzeit': 'Uptime',
  'Zuletzt aktiv': 'Last active',
  'Zugeteilt': 'Allocated',
  'Apps offen': 'Apps open',
  '{open} von {total}': '{open} of {total}',
  'Desktop öffnen': 'Open desktop',
  'Weiter arbeiten': 'Resume work',
  'Fortsetzen': 'Resume',
  'Pause': 'Pause',
  'Pausiert': 'Paused',
  'Fortgesetzt': 'Resumed',
  'Beendet — dein Profil bleibt erhalten': 'Stopped — your profile is kept',
  '{name} beenden': 'Stop {name}',
  '{name} läuft': '{name} is running',
  '{name} läuft bereits — oben verbinden': '{name} is already running — connect above',
  '{n} Apps in einem Container': '{n} apps in one container',
  'Kern': 'core',
  'Kerne': 'cores',
  'Starten': 'Start',

  // ---------------------------------------------------------------- Viewer
  '{name} — Sitzung': '{name} — session',
  'Kontrollleiste schliessen': 'Close control bar',
  'Kontrollleiste öffnen': 'Open control bar',
  'Leiste schliessen': 'Close bar',
  'Anwendung': 'Application',
  'Desktop': 'Desktop',
  'Alle Anwendungen teilen sich dasselbe Zuhause und dieselbe Zwischenablage.':
    'All applications share the same home directory and the same clipboard.',
  'Zwischenablage': 'Clipboard',
  'Strg+C und Strg+V werden zwischen Browser und Session abgeglichen. Dieses Feld ist der Weg, wenn der Browser die Zwischenablage nicht freigibt.':
    'Ctrl+C and Ctrl+V are synced between the browser and the session. This field is the way through when the browser withholds clipboard access.',
  'Der Abgleich startet, sobald der Stream steht.': 'Syncing starts as soon as the stream is up.',
  'Text zum Übertragen…': 'Text to transfer…',
  'Zwischenablage-Inhalt': 'Clipboard contents',
  'In die Session': 'To the session',
  'Aus der Session': 'From the session',
  'Aus der Session übernommen': 'Taken from the session',
  'In der Session wurde noch nichts kopiert': 'Nothing has been copied in the session yet',
  'Das Feld ist leer': 'The field is empty',
  'In die Session übertragen': 'Transferred to the session',
  'Übertragung nicht möglich — läuft der Stream?': 'Transfer failed — is the stream running?',
  'Vollbild': 'Full screen',
  'Fokus setzen': 'Focus session',
  'Fokus zurück in der Sitzung': 'Focus is back in the session',
  'Sitzung': 'Session',
  'Neu verbinden': 'Reconnect',
  'Neu verbunden': 'Reconnected',
  'Zurück zum Dashboard': 'Back to dashboard',

  // ------------------------------------------------------------ Workspaces
  'Workspace anlegen': 'Create workspace',
  'Workspace angelegt': 'Workspace created',
  'Neuer Workspace': 'New workspace',
  'Änderungen speichern': 'Save changes',
  'Noch kein Workspace angelegt': 'No workspace created yet',
  'Lege einen Arbeitsplatz an und weise ihn einer Gruppe zu — dann erscheint er im Dashboard der Nutzer.':
    'Create a workspace and assign it to a group — then it shows up on your users’ dashboards.',
  'Arbeitsspeicher frei': 'Memory free',
  'von {n} GB': 'of {n} GB',
  'Zugesagt je Session': 'Committed per session',
  'wenn alle {n} Workspaces gleichzeitig laufen': 'if all {n} workspaces run at once',
  '{n} Container': '{n} containers',
  'Die Verwaltung konnte nicht geladen werden': 'Administration could not be loaded',
  'Anzeigename': 'Display name',
  'So erscheint der Workspace auf der Kachel im Dashboard.':
    'This is how the workspace appears on the dashboard tile.',
  'Beschreibung': 'Description',
  'Ein Satz, der Nutzern sagt, wofür sie diesen Workspace öffnen.':
    'One sentence telling users what to open this workspace for.',
  'Image': 'Image',
  'Wählbar sind die Images, die auf diesem Host bereitliegen.':
    'You can pick any image already present on this host.',
  'Betriebsart': 'Mode',
  'Ein Linux je Nutzer mit mehreren Apps darin. Der Standard.':
    'One Linux per user with several apps inside. The default.',
  'Eine Anwendung als Wegwerf-Container. Für selten genutzte Werkzeuge.':
    'A single application as a throwaway container. For rarely used tools.',
  'Arbeitsplatz': 'Workspace',
  'Einzelne App': 'Single app',
  'Kategorien': 'Categories',
  'Bestimmt, unter welchem Filter der Workspace erscheint.':
    'Decides which filter the workspace appears under.',
  'Sichtbarkeit': 'Visibility',
  'Workspace ist aktiv': 'Workspace is active',
  'Zugewiesene Nutzer können ihn starten.': 'Assigned users can start it.',
  'Niemand kann ihn starten, die Zuweisung bleibt bestehen.':
    'Nobody can start it; the assignment stays in place.',
  'Diese Anwendungen sind im Golden Image installiert. Jede bekommt beim Start ein eigenes Display im selben Container und teilt sich mit den anderen das Zuhause.':
    'These applications are installed in the golden image. Each one gets its own display in the same container and shares the home directory with the others.',
  'Extensions wandern nicht zwischen den Editoren. Jeder bezieht sie aus seiner eigenen Quelle.':
    'Extensions do not travel between editors. Each one gets them from its own source.',
  'Für dieses Image ist noch kein App-Katalog hinterlegt. Er entsteht mit dem Golden Image.':
    'No app catalogue is stored for this image yet. It is created along with the golden image.',
  'Extensions aus:': 'Extensions from:',
  '{app} bereitstellen': 'Provide {app}',
  'Die Werte gelten für den Container als Ganzes, nicht je App. Er muss auf die Spitze ausgelegt sein — auf alles, was ein Nutzer gleichzeitig offen hat.':
    'These values apply to the container as a whole, not per app. Size it for the peak — everything a user has open at the same time.',
  'Prozessorkerne': 'CPU cores',
  'Prozessorkerne für diesen Nutzer': 'CPU cores for this user',
  'Prozessorkerne für {name}': 'CPU cores for {name}',
  'Dieser Host hat {n} Kerne.': 'This host has {n} cores.',
  'Über {n} Kernen teilen sich die Sessions die CPU.':
    'Above {n} cores the sessions share the CPU.',
  'Arbeitsspeicher': 'Memory',
  'Arbeitsspeicher für diesen Nutzer': 'Memory for this user',
  'Arbeitsspeicher für {name}': 'Memory for {name}',
  'Der Host hat {total} GB, davon sind gerade {free} GB frei.':
    'The host has {total} GB, of which {free} GB are free right now.',
  'Host-Auslastung nicht verfügbar.': 'Host usage unavailable.',
  'Mehr als {free} GB sind gerade nicht frei. Der Start würde abgelehnt.':
    'More than {free} GB are not free right now. The start would be refused.',
  'Mehr als {free} GB sind gerade nicht frei.': 'More than {free} GB are not free right now.',
  'Auflösung': 'Resolution',
  'Nutzer können sie in der Session jederzeit ändern.':
    'Users can change it inside the session at any time.',
  'Sitzung endet nach Inaktivität': 'Session ends after inactivity',
  'Gemessen ab dem letzten Lebenszeichen des Browsers.':
    'Measured from the browser’s last sign of life.',
  'Zeit bis zur Inaktivität': 'Time until inactivity',
  'Was dann passiert': 'What happens then',
  'Der Container wird entfernt. Das persistente Profil bleibt erhalten.':
    'The container is removed. The persistent profile is kept.',
  'Der Container behält seinen Arbeitsspeicher und ist sofort wieder da.':
    'The container keeps its memory and is back instantly.',
  'Der Container wird gestoppt und beim nächsten Mal neu gestartet.':
    'The container is stopped and started fresh next time.',
  'Aktion bei Inaktivität': 'Action on inactivity',
  'Pausieren': 'Pause',
  'Stoppen': 'Stop',
  'Persistentes Profil': 'Persistent profile',
  'Ein gemeinsames Home für alle Workspaces dieses Nutzers.':
    'One shared home for all of this user’s workspaces.',
  'Ein eigenes Home nur für diesen Workspace-Typ.':
    'A separate home just for this workspace type.',
  'Nichts wird gespeichert. Jeder Start beginnt beim Golden Image.':
    'Nothing is kept. Every start begins from the golden image.',
  'Persistenz': 'Persistence',
  'Pro Nutzer': 'Per user',
  'Pro Workspace': 'Per workspace',
  'Flüchtig': 'Ephemeral',
  'Gilt für alle Nutzer dieses Workspace. Gruppen können strenger sein, nie großzügiger.':
    'Applies to every user of this workspace. Groups can be stricter, never more permissive.',
  'Die Brücke hält die Zwischenablage über alle Apps im Container gleich. Wird das Kopieren hier abgeschaltet, läuft auch die Brücke nicht.':
    'The bridge keeps the clipboard identical across all apps in the container. Turn copying off here and the bridge stops too.',
  'Umgebungsvariablen': 'Environment variables',
  'Keine Geheimnisse hier — Umgebungsvariablen sind über docker inspect lesbar und landen in Logs.':
    'No secrets here — environment variables are readable through docker inspect and end up in logs.',
  'Variable hinzufügen': 'Add variable',
  'Nur Mitglieder dieser Gruppen sehen den Workspace in ihrem Dashboard.':
    'Only members of these groups see the workspace on their dashboard.',
  'Verfügbar': 'Available',
  'Alle Gruppen zugewiesen': 'All groups assigned',
  'Niemand sieht diesen Workspace': 'Nobody sees this workspace',
  'Ressourcen je Nutzer': 'Resources per user',
  'Zuteilung fehlgeschlagen': 'Allocation failed',
  'Anlegen fehlgeschlagen': 'Creating failed',

  // Rechte-Schalter
  'Kopieren erlauben': 'Allow copying',
  'Session → Browser. Entspricht SendCutText': 'Session → browser. Maps to SendCutText',
  'Einfügen erlauben': 'Allow pasting',
  'Browser → Session. Entspricht AcceptCutText': 'Browser → session. Maps to AcceptCutText',
  'Bilder übertragen': 'Transfer images',
  'image/png zusätzlich zu Text': 'image/png in addition to text',
  'Markieren und Mittelklick': 'Select and middle-click',
  'X-PRIMARY zusätzlich zu Strg+C. Ab Werk aus': 'X-PRIMARY in addition to Ctrl+C. Off by default',
  'Dateien hochladen': 'Upload files',
  'Ablegen im Uploads-Ordner der Session': 'Dropped into the session’s Uploads folder',
  'Dateien herunterladen': 'Download files',
  'Aus der Session auf den eigenen Rechner': 'From the session to your own machine',
  'Ton': 'Audio',
  'Audioausgabe der Session im Browser': 'The session’s audio output in the browser',
  'Mikrofon': 'Microphone',
  'Zugriff auf das Mikrofon des Nutzers': 'Access to the user’s microphone',
  'Kamera': 'Camera',
  'Zugriff auf die Kamera des Nutzers': 'Access to the user’s camera',
  'Drucken': 'Printing',
  'Druckaufträge als PDF an den Browser': 'Print jobs sent to the browser as PDF',
  'Dateien': 'Files',
  'Geräte': 'Devices',
  'Sonstiges': 'Other',

  // Reiter im Workspace-Editor
  'Allgemein': 'General',
  'Apps': 'Apps',
  'Umgebung': 'Environment',
  'Zuteilung': 'Allocation',

  // Kategorien
  'Entwicklung': 'Development',
  'Produktivität': 'Productivity',
  'Büro': 'Office',
  'Multimedia': 'Multimedia',
  'Kommunikation': 'Communication',
  'KI-Werkzeug': 'AI tool',

  // ------------------------------------------------------- Nutzer, Gruppen
  'Nutzer und Gruppen': 'Users and groups',
  'Nutzer anlegen': 'Create user',
  'Gruppe anlegen': 'Create group',
  'Lokales Konto': 'Local account',
  'Wird für die Anmeldung verwendet und lässt sich später nicht ändern.':
    'Used to sign in and cannot be changed later.',
  'E-Mail': 'Email',
  'Startpasswort': 'Initial password',
  'Mindestens 12 Zeichen. Der Nutzer muss es bei der ersten Anmeldung wechseln.':
    'At least 12 characters. The user must change it at first sign-in.',
  'leer lassen, um es nicht zu ändern': 'leave empty to keep it unchanged',
  'Bestimmt, welche Workspaces der Nutzer sieht und was er darf.':
    'Decides which workspaces the user sees and what they may do.',
  'Konto': 'Account',
  'Konto ist aktiv': 'Account is active',
  'Der Nutzer kann sich anmelden.': 'The user can sign in.',
  'Anmeldung gesperrt, Daten bleiben erhalten.': 'Sign-in blocked, data is kept.',
  'Systemgruppe — Name und Priorität sind festgelegt':
    'System group — name and priority are fixed',
  'Systemgruppe': 'System group',
  'Gruppenname': 'Group name',
  'Priorität': 'Priority',
  'Kleinere Zahl gewinnt, wenn zwei Gruppen widersprechende Ressourcen vorgeben.':
    'The lower number wins when two groups specify conflicting resources.',
  'Ohne Rechte sieht ein Mitglied nur sein eigenes Dashboard. „Vollzugriff auf alles" schliesst alle übrigen ein.':
    'Without permissions a member only sees their own dashboard. “Full access to everything” includes all the others.',
  'Zuletzt angemeldet': 'Last sign-in',
  'noch nie': 'never',
  'Mitglieder': 'Members',
  'nur eigenes Dashboard': 'own dashboard only',

  // Rechte-Klartext aus der API
  'Vollzugriff auf alles': 'Full access to everything',
  'Workspaces anlegen und ändern': 'Create and change workspaces',
  'Golden Images bauen und aktivieren': 'Build and activate golden images',
  'Nutzer anlegen und ändern': 'Create and change users',
  'Gruppen anlegen und ändern': 'Create and change groups',
  'Alle Sessions sehen und beenden': 'See and stop all sessions',
  'Globale Einstellungen ändern': 'Change global settings',
  'Audit-Log einsehen': 'View the audit log',
  'Registries einbinden': 'Attach registries',

  // ---------------------------------------------------------------- Betrieb
  'Betrieb': 'Operations',
  'Sessions': 'Sessions',
  'Protokoll': 'Audit log',
  'Sicherung': 'Backup',
  'Zurzeit läuft nichts': 'Nothing is running right now',
  'Hier stehen alle Sessions aller Nutzer, sobald jemand einen Workspace öffnet.':
    'Every user’s sessions appear here as soon as someone opens a workspace.',
  '{n} Session(en) belegen zusammen': '{n} session(s) together take up',
  'zugeteilten Speicher.': 'of allocated memory.',
  '{n} Apps': '{n} apps',
  'Beenden': 'Stop',
  'Beenden entfernt nur den Container. Das persistente Profil des Nutzers bleibt erhalten.':
    'Stopping only removes the container. The user’s persistent profile is kept.',
  'Vorgänge, keine Inhalte. Was in einer Session getan wird, steht hier nicht.':
    'Events, not contents. What someone does inside a session is not recorded here.',
  'Wer': 'Who',
  'Was': 'What',
  'Betrifft': 'Subject',
  'Von wo': 'From where',

  // Vorgangsnamen im Protokoll
  'Anmeldung': 'Sign-in',
  'Anmeldung fehlgeschlagen ': 'Sign-in failed',
  'Zweiter Faktor falsch': 'Second factor incorrect',
  'Session gestartet': 'Session started',
  'Session gestoppt': 'Session stopped',
  'Session pausiert': 'Session paused',
  'Session fortgesetzt': 'Session resumed',
  'Session beendet': 'Session ended',
  'Anwendung geöffnet': 'Application opened',
  'Anwendung geschlossen': 'Application closed',
  'Workspace geändert': 'Workspace changed',
  'Workspace gelöscht': 'Workspace deleted',
  'App-Katalog gesetzt': 'App catalogue set',
  'Zuteilung gesetzt': 'Allocation set',
  'Zuteilung entfernt': 'Allocation removed',
  'Nutzer angelegt': 'User created',
  'Nutzer geändert': 'User changed',
  'Nutzer gelöscht': 'User deleted',
  'Gruppe angelegt': 'Group created',
  'Gruppe geändert': 'Group changed',
  'Gruppe gelöscht': 'Group deleted',

  // --------------------------------------------------------------- Sicherung
  'Ablage': 'Storage',
  'Netzlaufwerk': 'network share',
  'lokale Platte': 'local disk',
  'NICHT beschreibbar': 'NOT writable',
  'Platz frei': 'Space free',
  'Belegt durch Sicherungen': 'Used by backups',
  '{n} gültige Sicherungen': '{n} valid backups',
  'Die Sicherungen liegen auf der lokalen Platte. Für ein Netzlaufwerk genügt es, ein NFS unter':
    'Backups live on the local disk. For a network share it is enough to mount an NFS export at',
  'einzuhängen — an OTA ändert sich dabei nichts, es sieht weiterhin nur diesen einen Pfad.':
    '— nothing changes in OTA, it still only ever sees this one path.',
  'Zeitplan': 'Schedule',
  'Automatisch sichern': 'Back up automatically',
  'Täglich um {time} Uhr': 'Daily at {time}',
  'an {days}': 'on {days}',
  'Es wird nur gesichert, wenn du es von Hand anstösst.':
    'Backups only run when you start them by hand.',
  'Uhrzeit': 'Time of day',
  'Ortszeit des Servers. Am besten dann, wenn niemand arbeitet.':
    'Server local time. Best chosen when nobody is working.',
  'An welchen Tagen': 'On which days',
  'Nichts ausgewählt bedeutet: jeden Tag.': 'Nothing selected means: every day.',
  'Was gesichert wird': 'What gets backed up',
  'Profile der Nutzer': 'User profiles',
  'Das Home mit Projekten, Einstellungen und Schlüsseln. Der eigentliche Wert.':
    'The home directory with projects, settings and keys. The part that actually matters.',
  'Änderungen in den Containern': 'Changes inside containers',
  'Nur was ausserhalb des Home verändert wurde. Meist aus dem Golden Image reproduzierbar.':
    'Only what changed outside the home directory. Usually reproducible from the golden image.',
  'Datenbank': 'Database',
  'Nutzer, Gruppen, Workspaces, Zuweisungen und das Audit-Log. Klein und schnell.':
    'Users, groups, workspaces, assignments and the audit log. Small and fast.',
  'Wie viele tägliche Stände bleiben': 'How many daily copies to keep',
  'Ältere werden nach dem Lauf entfernt.': 'Older ones are removed after each run.',
  'Tägliche Stände': 'Daily copies',
  'Stände': 'copies',
  'Zusätzliche wöchentliche Stände': 'Additional weekly copies',
  'Aus den älteren wird je Kalenderwoche der neueste behalten.':
    'Of the older ones, the newest per calendar week is kept.',
  'Wöchentliche Stände': 'Weekly copies',
  'Wochen': 'weeks',
  'Zuletzt gelaufen {when}': 'Last run {when}',
  'Vorhandene Sicherungen': 'Existing backups',
  'Läuft…': 'Running…',
  'Nur Datenbank': 'Database only',
  'Jetzt alle sichern': 'Back up everything now',
  'Noch nichts gesichert': 'Nothing backed up yet',
  'Stosse eine Sicherung von Hand an oder schalte den Zeitplan ein.':
    'Start a backup by hand or switch the schedule on.',
  '{n} Dateien': '{n} files',
  'Wiederherstellen': 'Restore',
  'Legt die Dateien in den laufenden Arbeitsplatz zurück':
    'Puts the files back into the running workspace',
  'In Session zurückspielen': 'Restore into session',
  'Sicherung löschen': 'Delete backup',
  'Datenbank wiederherstellen': 'Restore the database',
  'Das geht bewusst nicht per Knopfdruck. Die Datenbank trägt die Anmeldung, mit der du gerade hier stehst — sie unter der laufenden Anwendung auszutauschen bricht jede offene Verbindung mittendrin.':
    'Deliberately not a single button. The database holds the very sign-in you are using right now — swapping it out underneath the running application breaks every open connection mid-flight.',
  'Auf dem Server ausführen. Das Skript legt vorher eine Sicherheitskopie an, hält API und Agent an, spielt zurück und startet beides wieder:':
    'Run this on the server. The script takes a safety copy first, stops the API and the agent, restores, and starts both again:',
  'Profile auf der Platte sind davon nicht betroffen. Nach der Wiederherstellung müssen sich alle neu anmelden.':
    'Profiles on disk are unaffected. After the restore everyone has to sign in again.',
  'Profil wiederherstellen': 'Restore profile',
  'Das aktuelle Profil von': 'The current profile of',
  'wird durch den Stand vom': 'will be replaced by the copy from',
  'ersetzt. Alles, was seitdem entstanden ist, verschwindet aus dem Arbeitsplatz.':
    '. Everything created since then disappears from the workspace.',
  'Der bisherige Stand wird nicht gelöscht, sondern daneben aufgehoben — falls die Wiederherstellung doch nicht das Richtige war, lässt er sich zurückholen.':
    'The previous state is not deleted but kept alongside — if the restore turns out to be the wrong call, it can be brought back.',
  'Laufende Sessions des Nutzers müssen vorher beendet sein.':
    'The user’s running sessions have to be stopped first.',
  'Profil': 'Profile',
  'Container': 'Container',
  'von Hand': 'by hand',
  'nach Plan': 'on schedule',
  'vor Wiederherstellung': 'before restore',
  'fertig': 'done',
  'gestoppt': 'stopped',
  'pausiert': 'paused',
  'fehlgeschlagen': 'failed',
  'Mo': 'Mon',
  'Di': 'Tue',
  'Mi': 'Wed',
  'Do': 'Thu',
  'Fr': 'Fri',
  'Sa': 'Sat',
  'So': 'Sun',
  'Sicherung fehlgeschlagen': 'Backup failed',

  // ------------------------------------------------------------------ Hilfe
  'Hilfe': 'Help',
  'Handbuch': 'Handbook',
  'Kapitel': 'Chapters',
  'Kapitel durchsuchen': 'Search chapters',
  'Kein Kapitel passt zur Suche.': 'No chapter matches the search.',
  'Handbuch nicht verfügbar': 'Handbook unavailable',
  'Handbuch konnte nicht geladen werden': 'The handbook could not be loaded',
  'Dieses Kapitel ist für dich nicht freigegeben.': 'This chapter is not available to you.',
  'Grundlagen': 'Basics',
  'Für Anwender': 'For users',
  'Für Administratoren': 'For administrators',
  'Weiteres': 'Other',

  // ------------------------------------------------------------- Fehlertexte
  'Laden fehlgeschlagen': 'Loading failed',
  'Speichern fehlgeschlagen': 'Saving failed',
  'Löschen fehlgeschlagen': 'Deleting failed',
  'Start fehlgeschlagen': 'Start failed',
  'Aktion fehlgeschlagen': 'Action failed',
  'Konnte nicht geladen werden': 'Could not be loaded',
  'Die Daten konnten nicht geladen werden': 'The data could not be loaded',
  'Keine Verbindung zum Server. Läuft OTA noch?': 'No connection to the server. Is OTA still running?',
  'Unerwarteter Fehler ({code})': 'Unexpected error ({code})',

  // Meldungen des Servers
  'Benutzername oder Passwort ist falsch.': 'Username or password is incorrect.',
  'Bitte den Code aus deiner App eingeben.': 'Please enter the code from your app.',
  'Der Code stimmt nicht.': 'That code is not correct.',
  'Das aktuelle Passwort stimmt nicht.': 'The current password is not correct.',
  'Dieses Konto ist deaktiviert.': 'This account is disabled.',
  'Du kannst dich nicht selbst löschen.': 'You cannot delete yourself.',
  'Diese Anwendung ist nicht hinterlegt.': 'This application is not configured.',
  'Diese Anwendung läuft nicht.': 'This application is not running.',
  'Diese Session gehört dir nicht': 'This session does not belong to you',
  'Für diese Session gibt es keinen Container.': 'There is no container for this session.',
  'Gruppe nicht gefunden': 'Group not found',
  'Nutzer nicht gefunden': 'User not found',
  'Session nicht gefunden': 'Session not found',
  'Sicherung nicht gefunden': 'Backup not found',
  'Workspace nicht gefunden': 'Workspace not found',
  'Konto nicht verfügbar': 'Account unavailable',
  'Nicht angemeldet': 'Not signed in',
  'Sitzung abgelaufen': 'Session expired',
  'Sitzung wurde beendet': 'The session was ended',
  'Unbekannte Aktion': 'Unknown action',
  'Ungültige Session': 'Invalid session',
  'Für diese Aktion fehlen dir die Rechte.': 'You do not have permission for this action.',

  // ------------------------------------------------ Eigener Tab, Verknüpfung
  'In eigenem Tab öffnen': 'Open in its own tab',
  'Tab schliessen': 'Close tab',
  'Auf den Desktop legen': 'Add to desktop',
  'Wird auf dem Desktop abgelegt…': 'Adding to your desktop…',
  '{name} liegt jetzt auf deinem Desktop.': '{name} is on your desktop now.',
  'Der Browser hat die Verknüpfung abgelehnt.': 'The browser refused the shortcut.',
  '{name} auf den Desktop legen': 'Add {name} to desktop',
  'Meine Ablage': 'My files',
  'Einmal': 'One-time',
  'Einmal-Skript anlegen': 'Add a one-time script',
  'Noch kein Einmal-Skript': 'No one-time script yet',
  'Nochmal': 'Run again',
  'Bearbeiten': 'Edit',
  'Angelegt {when}': 'Created {when}',
  '{n}× gelaufen': 'ran {n}×',
  '{n} gescheitert': '{n} failed',
  '(keine Ausgabe)': '(no output)',
  'Ohne Namen findet es später niemand wieder.': 'Without a name nobody will find it again.',
  'Zurückgesetzt für {n} Nutzer.': 'Reset for {n} users.',
  'Zurücksetzen fehlgeschlagen': 'Reset failed',
  'z. B. „VS Code 1.99 — settings.json umziehen"':
    'e.g. "VS Code 1.99 — move settings.json"',
  'Läuft je Nutzer genau einmal, beim nächsten Start dieses Workspace — für Änderungen am Zuhause, die das Skeleton nicht mehr erreicht, weil dort schon etwas liegt.':
    'Runs exactly once per user, at their next start of this workspace — for changes to the home directory that the skeleton can no longer reach because something is already there.',
  'Typischer Fall: Ein Update braucht eine neue Einstellungsdatei im Home. Kopiere sie aus der gemeinsamen Ablage — $OTA_SHARED zeigt darauf.':
    'Typical case: an update needs a new settings file in the home directory. Copy it from the shared files — $OTA_SHARED points there.',
  'Bei {names} endete es mit einem Fehler.': 'It ended with an error for {names}.',
  '„{name}" bei allen erneut laufen lassen? Es passiert beim nächsten Start, nicht sofort.':
    'Run "{name}" again for everyone? It happens at their next start, not right now.',
  '„{name}" löschen? Die Buchführung geht mit.':
    'Delete "{name}"? The record of who has run it goes too.',
  'Gespeichert. Es läuft beim nächsten Start jedes Nutzers, der es noch nicht hatte.':
    'Saved. It runs at the next start for every user who has not had it yet.',
  'Läuft als Nutzer im Container, nicht als root — was dort entsteht, soll ihm gehören. Scheitert es, startet der Arbeitsplatz trotzdem, und es wird als gelaufen verbucht: Ein kaputtes Skript soll nicht bei jedem Start jedes Nutzers wieder anlaufen. Der Fehler steht dann hier.':
    'Runs as the user inside the container, not as root — whatever it creates should belong to them. If it fails, the workspace still starts and the run is recorded anyway: a broken script must not fire again at every start for every user. The error shows up here.',
  'Eine Änderung am Text lässt es nicht erneut laufen. Wer es schon hatte, hat es gehabt — dafür ist „Nochmal" da.':
    'Editing the text does not make it run again. Whoever has had it, has had it — that is what "Run again" is for.',
  'Gemeinsame Ablage': 'Shared files',
  'Deine Dateien': 'Your files',
  'Eigene Ablage': 'Personal shelf',
  'Eigene Ablage einhängen': 'Mount the personal shelf',
  'Der übliche Weg, Dateien hinein und heraus zu bekommen':
    'The usual way to get files in and out',
  'Im Container unter /mnt/austausch und als „Austausch" im Home.':
    'In the container at /mnt/austausch and as "Austausch" in the home directory.',
  'Liegt in deinem Arbeitsplatz unter /mnt/austausch und als „Austausch" im Home — beschreibbar. Was du hier ablegst, liegt gleich darauf im Container; was du dort hineinlegst, findest du hier.':
    'Sits in your workspace at /mnt/austausch and as "Austausch" in your home directory — writable. What you put here shows up in the container moments later; what you put there shows up here.',
  'Liegt im Container unter /mnt/austausch und als „Austausch" im Home. Jeder sieht nur seine eigene.':
    'Sits in the container at /mnt/austausch and as "Austausch" in the home directory. Everyone sees only their own.',
  'Ohne sie führt kein Weg über den Browser in diesen Container hinein oder heraus — ausser dem, den die Rechte ohnehin erlauben.':
    'Without it there is no route through the browser into this container or out of it — beyond whatever the permissions already allow.',
  'Belegt insgesamt {size}. Das hier sieht ausser dir niemand — auch die Administration nicht.':
    'Using {size} in total. Nobody but you sees this — not even the administration.',
  '{name} löschen': 'Delete {name}',
  'Auf dem Desktop': 'On your desktop',
  'Verknüpfung anlegen': 'Add a shortcut',
  'Zuklappen': 'Close',
  'Ganzer Arbeitsplatz': 'Whole workspace',
  'Jetzt öffnen': 'Open it now',
  'Abgebrochen. Du kannst es jederzeit erneut versuchen.':
    'Cancelled. You can try again any time.',
  'Diese Anwendung gibt es nicht.': 'There is no such application.',
  'Jede Anwendung lässt sich als Symbol ablegen und startet dann in einem eigenen Fenster ohne Browserleiste. Wer nicht angemeldet ist, meldet sich beim Öffnen an.':
    'Every application can be added as an icon and then opens in its own window without browser chrome. If you are not signed in, you sign in when you open it.',
  'Als eigenes Fenster ohne Browserleiste. Wer noch nicht angemeldet ist, meldet sich beim Öffnen an — danach geht es direkt weiter.':
    'Its own window, no browser chrome. If you are not signed in yet, you sign in when you open it — and carry straight on.',
  'Dein Browser bietet das Ablegen über sein eigenes Menü an — in Chrome und Edge über das Symbol rechts in der Adressleiste, in Firefox über „Diese Seite installieren".':
    'Your browser offers this through its own menu — in Chrome and Edge via the icon at the right of the address bar, in Firefox via "Install this site".',
  '{name} wird gestartet…': 'Starting {name}…',
  'Das lässt sich gerade nicht öffnen': 'That cannot be opened right now',
  'Diese Sitzung gibt es nicht mehr.': 'That session no longer exists.',
  'Diesen Arbeitsplatz gibt es nicht.': 'There is no such workspace.',
  'Zum Dashboard': 'To the dashboard',

  // --------------------------------------------------------- Einstellungen
  'Einstellungen': 'Settings',
  'Abmelden nach Untätigkeit': 'Sign out after inactivity',
  'Die Frist läuft nur, solange niemand etwas tut. Wer in einer Session arbeitet, wird nicht abgemeldet — jede Anfrage schiebt sie nach vorn.':
    'The clock only runs while nothing is happening. Anyone working in a session is never signed out — every request pushes it forward.',
  'Gilt ab der nächsten Anmeldung und für jede Sitzung, die danach weiterläuft. Bereits ausgestellte Zugänge behalten ihre alte Frist bis zu ihrer nächsten Verlängerung.':
    'Applies from the next sign-in and to every session that continues after it. Already issued sessions keep their old limit until they are next extended.',
  'Anmeldefrist auf {value} gesetzt': 'Sign-in limit set to {value}',

  '{n} Nutzer in der Liste': '{n} users in the list',

  // ------------------------------------------------- Firefox-Erweiterung
  'Firefox lässt Webseiten nicht in die Zwischenablage sehen. Mit der OTA-Erweiterung geht Kopieren und Einfügen wie gewohnt; ohne sie bleibt Strg+V im Stream.':
    'Firefox does not let web pages read the clipboard. With the OTA add-on, copy and paste work as usual; without it, Ctrl+V inside the stream is the way.',
  'Erweiterung herunterladen': 'Download the add-on',
  'Firefox gibt die Zwischenablage nicht frei. Einfügen geht mit Strg+V, für den bequemen Weg gibt es die OTA-Erweiterung.':
    'Firefox withholds clipboard access. Pasting works with Ctrl+V; for the comfortable route there is the OTA add-on.',

  // ------------------------------------------------ Software und Freigabe
  'Software einbauen': 'Install software',
  'Ausgewählte Pakete kommen ins Golden Image. Laufende Sessions bleiben unberührt — die neue Fassung gilt ab dem nächsten Start.':
    'Selected packages go into the golden image. Running sessions are untouched — the new version applies from the next start.',
  'Pakete': 'Packages',
  'Debian-Paketnamen. Was hier steht, wird beim Bauen mit apt installiert.':
    'Debian package names. Whatever is listed here is installed with apt during the build.',
  'Weiteres Paket, z. B. audacity': 'Another package, e.g. audacity',
  'Paketname': 'Package name',
  'Hinzufügen': 'Add',
  'Eigene Schritte': 'Custom steps',
  'Für alles, was apt nicht kann. Läuft als root im Image, nach den Paketen.':
    'For anything apt cannot do. Runs as root inside the image, after the packages.',
  'Eigenes Skript verwenden': 'Use a custom script',
  'Nur nötig, wenn ein Paket nicht reicht — etwa für ein fremdes Repository.':
    'Only needed when a package is not enough — for a third-party repository, say.',
  'Eigenes Skript': 'Custom script',
  'Image bauen': 'Build image',
  'Build läuft…': 'Build running…',
  '{n} Pakete ausgewählt': '{n} packages selected',
  'Der Build läuft. Das dauert ein paar Minuten.': 'The build is running. This takes a few minutes.',
  'Fassung {n} ist gebaut. Jetzt aktivieren.': 'Version {n} is built. Activate it now.',
  'Der Build ist gescheitert. Das Protokoll sagt, woran.':
    'The build failed. The log says why.',
  'Fassung {n} ist jetzt in Betrieb. Neue Sessions bekommen sie.':
    'Version {n} is live. New sessions get it.',
  'Es ist nichts ausgewählt, was eingebaut werden soll.': 'Nothing is selected to install.',
  'Aktivieren fehlgeschlagen': 'Activating failed',
  'Durchsehen fehlgeschlagen': 'Scanning failed',
  'Fassung {n}': 'Version {n}',
  'Fassungen': 'Versions',
  'Fassung': 'Version',
  'Inhalt': 'Contents',
  'Gebaut': 'Built',
  'ohne Zusätze': 'no additions',
  'in Betrieb': 'live',
  'Aktivieren': 'Activate',
  'Wird vorbereitet…': 'Preparing…',
  'wartet': 'queued',
  'wird gebaut': 'building',
  'gescheitert': 'failed',

  'Anwendungen freigeben': 'Publish applications',
  'OTA sieht im aktiven Image nach, was installiert ist, und liest Name, Symbol und Startbefehl aus den Programmdateien. Du entscheidest nur, was die Nutzer bekommen.':
    'OTA looks inside the active image, and reads name, icon and start command from the program files. All you decide is what your users get.',
  'Im Image nachsehen': 'Look inside the image',
  'Wird durchgesehen…': 'Scanning…',
  'Neu durchsehen': 'Scan again',
  'Auswahl übernehmen': 'Apply selection',
  '{n} Anwendungen freigegeben.': '{n} applications published.',
  'Anderes Zeichen wählen': 'Pick another symbol',
  'Name von {app}': 'Name of {app}',
  'Im aktiven Image nicht mehr vorhanden.': 'No longer present in the active image.',
  'Braucht ein Terminal — startet allein auf leerem Bildschirm.':
    'Needs a terminal — on its own it starts on an empty screen.',
  'Die Reihenfolge bestimmt, welches Display eine Anwendung bekommt. Wer sie ändert, muss laufende Arbeitsplätze neu starten.':
    'The order decides which display an application gets. Changing it means restarting running workspaces.',

  // ------------------------------------------------------- Paketpruefung
  'Wird im Image nachgeschlagen…': 'Looking it up in the image…',
  'kennt dieses Image nicht.': 'is unknown to this image.',
  'gibt es hier nur als Verweis auf ein Snap. Im Container läuft kein Snap; installiert würde ein Platzhalter ohne Programm. Nimm dafür ein Rezept unten.':
    'exists here only as a pointer to a snap. Snaps do not run in a container; installing it would leave a stub with no program. Use a recipe below instead.',
  'Gemeint war vielleicht:': 'Perhaps you meant:',
  '{list} gibt es in diesem Image nicht. Der Build würde daran scheitern.':
    '{list} does not exist in this image. The build would fail on it.',
  'Rezepte': 'Recipes',
  'Für Software, die kein einfaches Paket ist. Ein Rezept hängt seine Schritte unten an — sichtbar und änderbar.':
    'For software that is not a plain package. A recipe appends its steps below — visible and editable.',

  // ------------------------------------------------------------- Images
  'Images': 'Images',
  'Image holen': 'Fetch an image',
  'Adresse wie bei docker pull. Danach steht es beim Anlegen eines Workspace zur Auswahl.':
    'An address like docker pull takes. Afterwards it is available when creating a workspace.',
  'Image-Adresse': 'Image address',
  'Holen': 'Fetch',
  'Wird geholt…': 'Fetching…',
  'wird begonnen': 'starting',
  '{ref} liegt jetzt auf diesem Host.': '{ref} is on this host now.',
  'Das Image liess sich nicht holen.': 'The image could not be fetched.',
  '{ref} vom Host entfernen?': 'Remove {ref} from the host?',
  '{ref} entfernt.': '{ref} removed.',
  'Auf diesem Host': 'On this host',
  '{n} · {size} GB': '{n} · {size} GB',
  'Herkunft': 'Origin',
  'Von OTA gebaut': 'Built by OTA',
  'Von Kasm': 'From Kasm',
  'Übrige': 'Others',
  'Alle': 'All',
  'Nichts in dieser Gruppe': 'Nothing in this group',
  'Sobald du im Workspace-Editor unter Software ein Image baust, erscheint es hier.':
    'As soon as you build an image under Software in the workspace editor, it shows up here.',
  'Hole ein Image über das Feld oben.': 'Fetch an image using the field above.',
  'Benutzt von': 'Used by',
  'Entfernen': 'Remove',
  'Images von Kasm bleiben unangetastet — sie gehören dem anderen System auf diesem Host. Ein Image, das ein Workspace benutzt, lässt sich nicht entfernen.':
    'Kasm images are left alone — they belong to the other system on this host. An image a workspace uses cannot be removed.',
  'Die Auswahl zeigt, was auf diesem Host liegt — von OTA gebaute zuerst. Ein Image, das noch nicht da ist, holst du unter Images.':
    'The list shows what is on this host, OTA-built first. An image that is not here yet you fetch under Images.',
  'Dieses Image liegt nicht auf dem Host. Hol es unter Images, sonst scheitert der erste Start.':
    'This image is not on the host. Fetch it under Images, or the first start will fail.',
  '„{name}“ löschen?': 'Delete “{name}”?',
  'App-Katalog, Zuteilungen je Nutzer und die Image-Fassungen dieses Workspace verschwinden mit. Die Profile der Nutzer bleiben erhalten.':
    'The app catalogue, per-user allocations and this workspace’s image versions go with it. User profiles are kept.',
  '{name} gelöscht': '{name} deleted',
  '{name} ist bereit. Wähle oben eine Anwendung.':
    '{name} is ready. Pick an application above.',

  // ------------------------------------------------------------ Werkbank
  'Pfad': 'Path',
  'Bereiche': 'Sections',
  'Workspaces': 'Workspaces',

  // -------------------------------------------------------- Rezept-Bauer
  'Neues Rezept': 'New recipe',
  'Rezept speichern': 'Save recipe',
  'Das Rezept braucht einen Namen.': 'The recipe needs a name.',
  'Rezept „{name}" gespeichert.': 'Recipe “{name}” saved.',
  'Rezept „{name}" löschen?': 'Delete recipe “{name}”?',
  'Rezept „{name}" gelöscht.': 'Recipe “{name}” deleted.',
  '{name} bearbeiten': 'Edit {name}',
  '{name} ändern': 'Change {name}',
  'Kopie von {name}': 'Copy of {name}',
  'Mitgeliefert — als Kopie öffnen': 'Built in — opens as a copy',
  'Ändern': 'Change',
  'So steht es später auf der Schaltfläche.': 'This is what the button will say.',
  'Adresse des Schlüssels': 'Key address',
  'Der Signaturschlüssel des Depots. Ohne ihn nimmt apt nichts an.':
    'The repository’s signing key. Without it apt accepts nothing.',
  'Depot-Zeile': 'Repository line',
  'Wie in einer sources.list. Den Teil mit signed-by lässt du weg — der wird eingesetzt.':
    'As it would stand in a sources.list. Leave out the signed-by part — that is filled in.',
  'Paket': 'Package',
  'Was aus diesem Depot installiert werden soll.': 'What to install from this repository.',
  'Vorrang': 'Priority',
  'Diesem Depot Vorrang geben': 'Give this repository priority',
  'Nötig, wenn die Distribution ein gleichnamiges Paket führt — sonst gewinnt deren Fassung. Genau der Fall bei Firefox auf Ubuntu.':
    'Needed when the distribution carries a package of the same name — otherwise its version wins. Exactly the case with Firefox on Ubuntu.',
  'Adresse der Datei': 'File address',
  'Fehlende Abhängigkeiten zieht apt selbst nach.': 'apt pulls in missing dependencies itself.',
  'Kennung': 'Identifier',
  'Kleingeschrieben, ohne Leerzeichen. Wird zum Verzeichnis unter /opt und zum Befehl.':
    'Lowercase, no spaces. Becomes the directory under /opt and the command.',
  'Programm im Archiv': 'Program inside the archive',
  'Pfad innerhalb des Archivs, ohne das oberste Verzeichnis.':
    'Path inside the archive, without the top-level directory.',
  'Anzeigename im Menü': 'Display name in the menu',
  'Unter diesem Namen findet OTA die Anwendung später im Image wieder.':
    'This is the name by which OTA finds the application in the image later.',
  'Wozu es da ist': 'What it is for',
  'Ein Satz, der beim Überfahren der Schaltfläche erscheint. Am hilfreichsten ist der Grund, warum es kein einfaches Paket tut.':
    'One sentence shown on hover. Most useful is the reason a plain package will not do.',
  'Nicht in den Ubuntu-Quellen.': 'Not in the Ubuntu sources.',
  'Das wird ausgeführt': 'This is what runs',
  'Wieder erzeugen': 'Generate again',
  'Skript': 'Script',
  'Von Hand geändert — die Angaben oben überschreiben den Text nicht mehr.':
    'Edited by hand — the fields above no longer overwrite this text.',
  'Läuft als root im Image, nach den Paketen. Änderst du hier etwas, bleibt deine Fassung stehen.':
    'Runs as root inside the image, after the packages. Edit here and your version stands.',
  'APT-Depot': 'APT repository',
  '.deb-Datei': '.deb file',
  'Archiv': 'Archive',
  'AppImage': 'AppImage',
  'Ein fremdes Paketdepot einbinden und daraus installieren. Der häufigste Fall — so kommen Firefox, Chrome und VSCodium ins Image.':
    'Attach a third-party package repository and install from it. The common case — this is how Firefox, Chrome and VSCodium get into the image.',
  'Ein einzelnes Debian-Paket von einer Adresse holen. Für Software, die als Datei ausgeliefert wird statt über ein Depot.':
    'Fetch a single Debian package from an address. For software shipped as a file rather than through a repository.',
  'Ein .tar.gz nach /opt auspacken und einen Starter anlegen. Für alles mit eigenem Verzeichnis — JetBrains, Blender.':
    'Unpack a .tar.gz into /opt and create a launcher. For anything with its own directory — JetBrains, Blender.',
  'Eine AppImage-Datei ablegen und ausführbar machen.': 'Place an AppImage file and make it executable.',
  'Freier Text. Wenn keines der Muster passt.': 'Free text. When none of the patterns fit.',

  // ------------------------------------------------------------- Ablage
  'Liegt in jedem Arbeitsplatz unter /mnt/ota und als „Gemeinsam" im Home — dort nur lesbar. Geschrieben wird ausschliesslich hier.':
    'Present in every workspace at /mnt/ota and as “Gemeinsam” in the home directory — read-only there. Writing happens only here.',
  'Ordner anlegen': 'New folder',
  'Name des Ordners': 'Folder name',
  'Dateien wählen': 'Choose files',
  'Dateien hierher ziehen': 'Drag files here',
  '{name} wird abgelegt…': 'Storing {name}…',
  '{n} Datei(en) abgelegt.': '{n} file(s) stored.',
  '{name} liess sich nicht ablegen.': '{name} could not be stored.',
  'Hier liegt nichts': 'Nothing here',
  'Zieh Dateien in die Fläche oben oder leg einen Ordner an.':
    'Drag files into the area above, or create a folder.',
  'Die Administration legt hier Dateien für alle Arbeitsplätze ab.':
    'Administrators put files here for every workspace.',
  'Geändert': 'Changed',
  'Herunterladen': 'Download',
  'Ordner „{name}" mit allem darin löschen?': 'Delete folder “{name}” and everything in it?',
  '„{name}" löschen?': 'Delete “{name}”?',
  'Belegt insgesamt {size}. Was hier liegt, sieht jeder Nutzer in jedem Arbeitsplatz — es ist kein Ort für Vertrauliches.':
    'Takes up {size} in total. Everything here is visible to every user in every workspace — it is not a place for anything confidential.',
  // -------------------------------------------------------- Skript beim Start
  'Skript beim Start': 'Script on start',
  'Läuft bei jedem Sessionstart als Nutzer im Container, bevor der Arbeitsplatz bereit ist. Für alles, was ins Home gehört, aber nicht ins Image.':
    'Runs at every session start, as the user inside the container, before the workspace is ready. For anything that belongs in the home directory but not in the image.',
  'Nicht für Installationen — die gehören ins Golden Image, sonst wartet jeder Nutzer bei jedem Start darauf. Scheitert das Skript, startet der Arbeitsplatz trotzdem; die Ausgabe steht im Container unter /tmp/ota-start.log.':
    'Not for installing software — that belongs in the golden image, or every user waits for it at every start. If the script fails the workspace still starts; its output is in the container at /tmp/ota-start.log.',

  // --------------------------------------------------------- Mein Konto
  'Mein Konto': 'My account',
  'Noch einmal': 'Once more',
  'Die beiden neuen Passwörter sind nicht gleich.': 'The two new passwords do not match.',
  'Passwort geändert. Deine anderen Sitzungen sind jetzt abgemeldet.':
    'Password changed. Your other sessions are signed out now.',
  'Ein Passwortwechsel meldet alle anderen Sitzungen ab — diese hier bleibt bestehen.':
    'Changing the password signs out all your other sessions — this one stays.',

  'Zwei-Faktor': 'Two-factor',
  'Zwei-Faktor einrichten': 'Set up two-factor',
  'Zwei-Faktor ist eingeschaltet.': 'Two-factor is on.',
  'Zwei-Faktor abschalten': 'Turn two-factor off',
  'Zwei-Faktor abgeschaltet.': 'Two-factor turned off.',
  'Mit dem zweiten Faktor reicht dein Passwort allein nicht mehr aus. Du brauchst dafür eine Authenticator-App auf dem Telefon.':
    'With a second factor your password alone is no longer enough. You need an authenticator app on your phone.',
  'Scanne den Code mit deiner Authenticator-App und tippe danach die sechs Ziffern ein, die sie zeigt.':
    'Scan the code with your authenticator app, then type the six digits it shows.',
  'Geht das Scannen nicht?': 'Cannot scan it?',
  'Dann trage dieses Geheimnis von Hand in der App ein.': 'Then enter this secret in the app by hand.',
  'Einschalten': 'Turn on',
  'Abschalten': 'Turn off',
  'Einrichtung fehlgeschlagen': 'Setup failed',
  'Abschalten fehlgeschlagen': 'Turning it off failed',
  'Erneuern fehlgeschlagen': 'Renewing failed',
  'Diese Codes siehst du nur jetzt. Drucke sie aus oder leg sie in deinen Passwortspeicher — mit ihnen kommst du herein, wenn dein Telefon weg ist. Jeder gilt einmal.':
    'You see these codes only now. Print them or put them in your password manager — they get you in when your phone is gone. Each one works once.',
  'Kopieren': 'Copy',
  'Codes in die Zwischenablage kopiert.': 'Codes copied to the clipboard.',
  'Der Browser gibt die Zwischenablage nicht frei.': 'The browser withholds clipboard access.',
  'Ich habe sie gesichert': 'I have saved them',
  '{n} Rückfallcodes übrig.': '{n} recovery codes left.',
  'Nur noch {n} Rückfallcodes übrig — erneuere sie.': 'Only {n} recovery codes left — renew them.',
  'Neue Rückfallcodes': 'New recovery codes',
  'Codes erneuern': 'Renew codes',
  'Die bisherigen gelten danach nicht mehr.': 'The previous ones stop working.',
  'Für beide Handlungen unten.': 'For both actions below.',
  'Verlangt zusätzlich einen gültigen Code — wer nur dein Passwort hat, soll ihn nicht entfernen können.':
    'Also requires a valid code — someone with only your password should not be able to remove it.',
  'Code': 'Code',

  'Sprache gemerkt.': 'Language remembered.',
  'Gilt sofort und wird am Konto gemerkt — an einem anderen Rechner musst du sie nicht erneut suchen.':
    'Applies at once and is remembered on your account — on another machine you will not have to find it again.',
  'Die Auflösung deiner Anwendungen musst du nicht einstellen: Der ferne Bildschirm folgt der Grösse deines Browserfensters.':
    'You do not have to set a resolution: the remote screen follows the size of your browser window.',
  'Sechs Ziffern aus der App — oder einer deiner Rückfallcodes.':
    'Six digits from the app — or one of your recovery codes.',

  // --------------------------------------------------------- Registries
  'Registries': 'Registries',
  'Registry': 'Registry',
  'Registry eintragen': 'Add a registry',
  'Eintragen': 'Add',
  'Eintragen fehlgeschlagen': 'Adding failed',
  'Wird gelesen…': 'Reading…',
  'Adresse der Registry': 'Registry address',
  'Die Adresse ohne Schema-Pfad. OTA liest dort {schema}.':
    'The address without the schema path. OTA reads {schema} there.',
  'Fremde Kataloge mit fertigen Anwendungen. Eintragen liest nur den Katalog — heruntergeladen wird erst, was du übernimmst und startest.':
    'Third-party catalogues of ready-made applications. Adding one only reads the catalogue — nothing is downloaded until you take something over and start it.',
  'Noch keine Registry eingetragen': 'No registry added yet',
  'Trage eine Adresse ein oder nimm einen der Vorschläge oben.':
    'Enter an address, or take one of the suggestions above.',
  'Anwendungen': 'Applications',
  'Übernommen': 'Taken over',
  'übernommen': 'taken over',
  'Zuletzt gelesen': 'Last read',
  'Auffrischen': 'Refresh',
  'Auffrischen fehlgeschlagen': 'Refreshing failed',
  '{name} aufgefrischt.': '{name} refreshed.',
  '{name} eingetragen — {n} Anwendungen im Katalog.':
    '{name} added — {n} applications in the catalogue.',
  '„{name}" entfernen? Bereits übernommene Workspaces bleiben.':
    'Remove “{name}”? Workspaces already taken over are kept.',
  'Eine Registry ist eine Vertrauensentscheidung. Ihr Katalog trägt zwar eine Signatur, aber der Schlüssel dafür liegt beim Betreiber — OTA prüft sie nicht. Was du übernimmst, läuft anschliessend in deinem Netz.':
    'A registry is a matter of trust. Its catalogue carries a signature, but the key for it belongs to the operator — OTA does not verify it. Whatever you take over then runs in your network.',

  'Katalog': 'Catalogue',
  'Katalog durchsuchen': 'Search the catalogue',
  '{n} von {total} Anwendungen': '{n} of {total} applications',
  'Übernehmen': 'Take over',
  'Wird übernommen…': 'Taking over…',
  'Übernehmen fehlgeschlagen': 'Taking over failed',
  'Nichts passt zu dieser Suche.': 'Nothing matches that search.',
  'Das ist ein grosser Teil der freien {free} GB auf diesem Host.':
    'That is a large share of the {free} GB free on this host.',
  'Übernehmen legt nur eine Vorlage an — abgeschaltet, ohne Gruppe. Das Image wird erst beim ersten Start geholt. Die Lizenz der Anwendung gilt unverändert; dass ein Katalog sie listet, sagt darüber nichts.':
    'Taking over only creates a workspace — switched off, with no group. The image is fetched at the first start. The application’s own licence still applies; a catalogue listing it says nothing about that.',
  'Nur für {archs} — dieser Host ist {here}.': 'Only for {archs} — this host is {here}.',
  'Läuft auf dieser Architektur nicht.': 'Does not run on this architecture.',
  'Sichtbar für alle': 'Visible to everyone',
  'Nur für: {names}': 'Only for: {names}',
  'gelöschte Gruppe': 'deleted group',
  'Sichtbar für welche Gruppen': 'Visible to which groups',
  'Platz': 'Storage',
  'Kontingent je Zuhause': 'Quota per home',
  'Wie viel ein Nutzer in seinem Home belegen darf. Wer darüber liegt, startet keine neue Session mehr — laufende bleiben unberührt. 0 schaltet die Grenze ab.':
    'How much a user may occupy in their home directory. Anyone above it starts no new session — running ones are untouched. 0 turns the limit off.',
  'Untergrenze für den freien Plattenplatz': 'Floor for free disk space',
  'Fällt der freie Platz auf dem Host darunter, startet keine Session mehr. Ein volles Dateisystem bringt laufende Arbeitsplätze zum Stehen — das hier ist die Bremse davor. 0 schaltet sie ab.':
    'If free space on the host drops below this, no session starts. A full filesystem brings running workspaces to a halt — this is the brake before that. 0 turns it off.',
  'Beides wirkt beim Start einer Session, nicht beim Schreiben einer Datei. Es ist kein Dateisystem-Kontingent — wer schon drin ist, kann weiter schreiben.':
    'Both apply when a session starts, not when a file is written. This is not a filesystem quota — anyone already inside can keep writing.',
  'Kontingent abgeschaltet': 'Quota turned off',
  'Kontingent auf {n} GB gesetzt': 'Quota set to {n} GB',
  'Untergrenze abgeschaltet': 'Floor turned off',
  'Untergrenze auf {n} GB gesetzt': 'Floor set to {n} GB',
  'GB': 'GB',
  'Zweiter Faktor ist für deine Gruppe Pflicht.': 'Two-factor is mandatory for your group.',
  'Bis er eingerichtet ist, lässt sich kein Arbeitsplatz starten.':
    'Until it is set up, no workspace will start.',
  'Jetzt einrichten': 'Set it up now',
  'Zweiter Faktor ist Pflicht': 'Two-factor is mandatory',
  'Mitglieder ohne zweiten Faktor können keinen Arbeitsplatz starten, bis sie ihn unter „Mein Konto“ eingerichtet haben. Die Anmeldung selbst bleibt möglich — sonst käme niemand an die Einrichtung.':
    'Members without a second factor cannot start a workspace until they have set one up under “My account”. Signing in still works — otherwise nobody could reach the setup.',
  'Dein Zuhause ist voll.': 'Your home directory is full.',
  'Dein Zuhause wird knapp.': 'Your home directory is getting tight.',
  '{used} von {quota} belegt ({pct} %).': '{used} of {quota} used ({pct} %).',
  'Bis du aufräumst, startet kein Arbeitsplatz mehr.':
    'Until you clear some space, no workspace will start.',
  'Downloads, Caches und alte Abbilder sind meist die Größten.':
    'Downloads, caches and old images are usually the biggest.',
  'VS-Code-Erweiterungen': 'VS Code extensions',
  'Kennungen wie ms-python.python, durch Leerzeichen oder Komma getrennt. Sie werden beim Bauen installiert, nicht beim Start — sonst wartet jeder Nutzer bei jedem Start auf Downloads.':
    'Identifiers like ms-python.python, separated by spaces or commas. They are installed at build time, not at start — otherwise every user waits for downloads at every start.',
  'Erweiterungen mitbauen': 'Build in extensions',
  'Sie landen ausschliesslich in Microsofts VS Code. VSCodium hat seinen eigenen Satz aus Open VSX und sieht diese hier nicht — dieselbe Kennung ist dort nicht dieselbe Installation.':
    'They land in Microsoft VS Code only. VSCodium has its own set from Open VSX and does not see these — the same identifier is not the same installation there.',
  'Breite von {app}': 'Width of {app}',
  'Höhe von {app}': 'Height of {app}',
  'Session einfrieren': 'Freeze the session',
  'Der kurze Weg: In deinem eigenen Arbeitsplatz einrichten, was alle bekommen sollen — und daraus eine neue Fassung machen. Was ausserhalb deines Home passiert ist, kommt mit; dein Home selbst nicht, dort liegen deine Schlüssel.':
    'The short way: set up what everyone should get inside your own workspace, then turn it into a new version. Whatever happened outside your home directory comes along; the home directory itself does not — your keys live there.',
  'Ansehen, was mitkäme': 'See what would come along',
  'Wird verglichen…': 'Comparing…',
  'Vorschau fehlgeschlagen': 'Preview failed',
  '{n} Änderung(en) ausserhalb des Home, {skip} übersprungen.':
    '{n} change(s) outside the home directory, {skip} skipped.',
  'Wird vorher entfernt: {list} — sonst bekäme jeder Nutzer des Images root.':
    'Removed first: {list} — otherwise every user of the image would get root.',
  '{n} Datei(en) sehen nach einem Geheimnis aus.': '{n} file(s) look like a secret.',
  'Sie kämen ins Image und damit zu jedem, der es benutzt: {list}':
    'They would go into the image and thus to everyone who uses it: {list}',
  '… und weitere. Insgesamt {n}.': '… and more. {n} in total.',
  'Trotz der Funde einfrieren': 'Freeze despite the findings',
  'Als neue Fassung einfrieren': 'Freeze as a new version',
  'Wird eingefroren…': 'Freezing…',
  'Einfrieren fehlgeschlagen': 'Freezing failed',
  'Eingefroren aus der laufenden Session': 'Frozen from the running session',
  'Fassung {n} eingefroren. Jetzt aktivieren.': 'Version {n} frozen. Activate it now.',
  'Zweiter Faktor': 'Second factor',
  'Für den Fall, dass Telefon und Rückfallcodes verloren sind. Ohne diesen Weg käme der Mensch nie wieder herein. Alle Sitzungen des Kontos werden dabei beendet, und es steht mit deinem Namen im Protokoll.':
    'For when both the phone and the recovery codes are gone. Without this, the person could never get back in. All sessions of the account are ended, and it is logged under your name.',
  'Zweiten Faktor abnehmen': 'Remove the second factor',
  'Abnehmen fehlgeschlagen': 'Removal failed',
  'Skeleton': 'Skeleton',
  'Was hier liegt, kommt beim ersten Start in das Zuhause eines Nutzers — solange es noch leer ist. Danach gehört das Zuhause ihm. Punktdateien sind erlaubt und der Normalfall.':
    'Whatever is here goes into a user\u2019s home directory at their first start — as long as it is still empty. After that the home belongs to them. Dotfiles are allowed and are the normal case.',
  'Dateien ablegen': 'Add files',
  'Verzeichnis anlegen': 'Create directory',
  'Name des Verzeichnisses': 'Name of the directory',
  'Pfad:': 'Path:',
  'eine Ebene höher': 'one level up',
  'Noch nichts hinterlegt. Dateien hierher ziehen oder oben ablegen.':
    'Nothing here yet. Drag files in, or add them above.',
  'durchsetzen': 'enforce',
  'Bei jedem Start überschreiben': 'Overwrite at every start',
  '{n} Pfad(e) werden bei jedem Start überschrieben:':
    '{n} path(s) are overwritten at every start:',
  'Was der Nutzer dort ändert, ist beim nächsten Start weg. Für ein Wurzelzertifikat richtig, für Einstellungen selten.':
    'Whatever the user changes there is gone at the next start. Right for a root certificate, rarely right for settings.',
  'Änderungen an „durchsetzen“ gelten erst nach dem Speichern. Die Dateien selbst sind sofort abgelegt.':
    'Changes to “enforce” take effect only after saving. The files themselves are stored immediately.',
  'Entfernen fehlgeschlagen': 'Removal failed',
  'Verzeichnis (LDAP / Active Directory)': 'Directory (LDAP / Active Directory)',
  'Konten aus einem Verzeichnis anmelden lassen, statt sie von Hand anzulegen. Lokale Konten bleiben davon unberührt — sie werden weiterhin lokal geprüft, auch wenn im Verzeichnis ein gleichnamiger Eintrag steht.': 'Let accounts sign in from a directory instead of creating them by hand. Local accounts are untouched — they are still checked locally, even if the directory holds an entry with the same name.',
  'Verbindung': 'Connection',
  'Adresse': 'Address',
  'ldaps://server:636 für eine verschlüsselte Verbindung, oder ldap://server:389 mit StartTLS.': 'ldaps://server:636 for an encrypted connection, or ldap://server:389 with StartTLS.',
  'Verschlüsselung': 'Encryption',
  'StartTLS': 'StartTLS',
  'ohne': 'none',
  'Ohne Verschlüsselung geht jedes Anmeldepasswort im Klartext über das Netz. Für einen Testaufbau in Ordnung, für den Betrieb nicht.': 'Without encryption every sign-in password crosses the network in the clear. Fine for a test setup, not for production.',
  'Dienstkonto': 'Service account',
  'Wird zum Suchen gebraucht und braucht nur Leserecht. Der Mensch, der sich anmeldet, kennt seinen eigenen Eintrag nicht.': 'Needed for searching and needs read access only. The person signing in does not know their own entry.',
  'Kennwort': 'Password',
  'hinterlegt — leer lassen, um es zu behalten': 'stored — leave empty to keep it',
  'Kennwort des Dienstkontos': 'Service account password',
  'Basis': 'Base',
  'Ab wo gesucht wird.': 'Where the search starts.',
  'Anmeldemerkmal': 'Login attribute',
  'Womit sich jemand anmeldet: uid bei OpenLDAP, sAMAccountName im Active Directory.': 'What people sign in with: uid on OpenLDAP, sAMAccountName on Active Directory.',
  'Gruppen-Basis': 'Group base',
  'Leer lassen, wenn die Gruppen unter derselben Basis liegen.': 'Leave empty if groups live under the same base.',
  'Prüfen': 'Check',
  'Ein Name zur Probe': 'A name to try',
  'Freiwillig. Mit einem Namen zeigt die Prüfung ausserdem, was das Verzeichnis über diesen Menschen liefert — vor allem seine Gruppen.': 'Optional. With a name, the check also shows what the directory returns for that person — above all their groups.',
  'Speichern und prüfen': 'Save and check',
  'Die Prüfung schlug fehl': 'The check failed',
  'Gespeichert, wird geprüft…': 'Saved, checking…',
  '{n} Einträge sichtbar, {g} Gruppen.': '{n} entries visible, {g} groups.',
  'Gruppen im Verzeichnis:': 'Groups in the directory:',
  'Gruppen zuordnen': 'Map groups',
  'Was nicht zugeordnet ist, bringt keine Rechte mit. Ein Verzeichnis hat Dutzende Gruppen, die OTA nichts angehen — sie automatisch zu übernehmen hiesse, nach dem ersten Abgleich vierzig Gruppen zu haben, die niemand wollte.': 'Anything unmapped brings no permissions. A directory has dozens of groups that are none of OTA\u2019s business — adopting them automatically would mean forty groups nobody wanted after the first sync.',
  'Erst prüfen — dann stehen die Gruppen des Verzeichnisses hier zur Auswahl.': 'Run the check first — then the directory\u2019s groups appear here.',
  'Zuordnung für {name}': 'Mapping for {name}',
  '— keine —': '— none —',
  'Zuordnung speichern': 'Save mapping',
  'Zuordnung gespeichert.': 'Mapping saved.',
  'Konten beim ersten Anmelden anlegen': 'Create accounts at first sign-in',
  'Ohne das muss jedes Konto vorher von Hand angelegt werden.': 'Without this, every account must be created by hand first.',
  'Nächtlich abgleichen': 'Sync nightly',
  'Holt Gruppenänderungen nach. Wer sich anmeldet, wird ohnehin bei jeder Anmeldung aufgefrischt.': 'Picks up group changes. Anyone who signs in is refreshed at every sign-in anyway.',
  'Jetzt abgleichen': 'Sync now',
  'zuletzt {when}': 'last {when}',
  '{n} Konten geprüft, {a} geändert, {d} deaktiviert.': '{n} accounts checked, {a} changed, {d} deactivated.',
  'Abgleich fehlgeschlagen': 'Sync failed',
  'Anmeldung über das Verzeichnis einschalten': 'Turn on directory sign-in',
  'Neue Namen werden im Verzeichnis gesucht. Lokale Konten bleiben lokal.': 'New names are looked up in the directory. Local accounts stay local.',
  'Abgeschaltet. An der Anmeldung ändert sich nichts.': 'Off. Nothing about signing in changes.',
  'Verzeichnis-Anmeldung eingeschaltet.': 'Directory sign-in turned on.',
  'Verzeichnis-Anmeldung abgeschaltet.': 'Directory sign-in turned off.',
  'Das Passwort eines lokalen Kontos wird nie gegen das Verzeichnis geprüft — auch dann nicht, wenn dort ein Eintrag mit demselben Namen steht. Sonst könnte jeder, der im Verzeichnis einen Eintrag anlegen darf, ein bestehendes Konto übernehmen.': 'A local account\u2019s password is never checked against the directory — not even when an entry with the same name exists there. Otherwise anyone who can create a directory entry could take over an existing account.',
  'Gespeichert.': 'Saved.',
  'Verbindung unterbrochen.': 'Connection lost.',
  'Wird neu verbunden…': 'Reconnecting…',
  'Wird neu verbunden — Versuch {n}.': 'Reconnecting — attempt {n}.',
  'Sofort versuchen': 'Try now',
  'Deine Dateien sind davon nicht betroffen — sie liegen im Profil, nicht in der Sitzung.': 'Your files are unaffected — they live in the profile, not in the session.',
}
