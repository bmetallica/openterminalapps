// Abnahmefall 7 aus plan.md §10.5 — die Zwischenablage aus Java/AWT heraus.
//
// **Warum Java eine eigene Zeile in der Abnahme hat.** X11 kennt keinen
// Zwischenspeicher, in dem etwas liegt: Es gibt einen *Besitzer* der Auswahl,
// und wer den Inhalt will, fragt den Besitzer danach. AWT bedient diese Frage
// aus einem eigenen Thread heraus und gibt den Besitz auf, sobald die
// virtuelle Maschine endet. Ein Programm, das setzt und sich sofort beendet,
// hinterlaesst deshalb eine leere Zwischenablage — was aussieht, als sei die
// Bruecke kaputt, und was bei Gtk- oder Electron-Anwendungen nicht passiert.
//
// Genau darum haelt `set` den Besitz eine Weile: So verhaelt sich auch
// IntelliJ, das waehrend des Kopierens ohnehin laeuft.
//
//   java ClipPruef.java set "text"  <millisekunden>
//   java ClipPruef.java get

import java.awt.Toolkit;
import java.awt.datatransfer.Clipboard;
import java.awt.datatransfer.DataFlavor;
import java.awt.datatransfer.StringSelection;

public class ClipPruef {
    public static void main(String[] args) throws Exception {
        Clipboard cb = Toolkit.getDefaultToolkit().getSystemClipboard();

        if (args.length > 0 && args[0].equals("set")) {
            cb.setContents(new StringSelection(args[1]), null);
            Thread.sleep(args.length > 2 ? Long.parseLong(args[2]) : 8000L);
            return;
        }

        Object inhalt = cb.getData(DataFlavor.stringFlavor);
        System.out.print(inhalt == null ? "" : inhalt.toString());
    }
}
