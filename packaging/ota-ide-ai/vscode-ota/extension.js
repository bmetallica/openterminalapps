// OTA IDE-AI: öffnet Continue einmal je Ordner (bzw. leerem Fenster) rechts
// in der zweiten Seitenleiste. Von selbst ginge die Leiste nicht auf: Beim
// Start ist sie noch leer, weil Continue erst danach lädt — und eine leere
// Leiste schliesst VS Code. Wer sie danach zumacht, dem bleibt sie zu; das
// merkt sich der Editor je Ordner selbst.
//
// Den eingebauten Copilot schaltet package.json ab (chat.disableAIFeatures),
// als Vorgabe: Eine eigene Einstellung übersteuert sie.
const vscode = require("vscode");

exports.activate = async (ctx) => {
  if (ctx.workspaceState.get("ota.continueGezeigt")) return;
  await ctx.workspaceState.update("ota.continueGezeigt", true);
  try {
    await vscode.commands.executeCommand("workbench.view.extension.continue");
  } catch (e) {
    // Ohne Continue gibt es nichts zu zeigen.
  }
};

exports.deactivate = () => {};
