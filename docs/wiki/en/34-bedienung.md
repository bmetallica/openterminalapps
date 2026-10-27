# 34 · Using a session: screen, keyboard, sound

*For users.* What you have at hand in a running session.

## The control bar ✅

So the application gets all the space, the bar is folded away. You open it with the **handle on the
right edge**. In it:

| | |
|---|---|
| **Applications** | switch between the applications of your workspace, or to the whole **Desktop** |
| **Clipboard** | a text field for both directions, in case the browser does not release the clipboard ([chapter 4](04-zwischenablage.md)) |
| **My files** | files in and out without leaving the session ([chapter 31](31-dateien.md)) |
| **Full screen** | the application fills the screen. Back with `Esc` |
| **Focus session** | brings the keyboard back into the application |
| **Reconnect** | rebuilds the picture transmission. The application keeps running |
| **Back to dashboard** | to the start page; the session keeps running |

**Ctrl + Alt + Shift** opens the bar too, but only while the keyboard is **not** in the
application. As soon as you have clicked into the picture, the keyboard belongs to the remote
desktop, so you can use any key combination there. The handle always works.

## Screen ✅

- **The size follows your window.** If you make the browser window larger, the remote screen gets
  larger. Nothing is stretched or shrunk; you do not need to set a resolution.
- **Each application in a tab of its own.** Several applications side by side: simply several tabs
  or windows. A bookmark on a tab brings you back into the same application.
- **Several monitors:** one browser window per monitor, each with an application of its own.

## Keyboard ✅

- **Click into the picture first.** Without focus, key presses do not arrive. After switching tabs,
  **Focus session** helps if needed.
- **Umlauts and special characters** arrive when the workspace's keyboard layout matches your
  keyboard. The administrators set it for everyone, German by default. If umlauts are missing or
  `/` turns into `?`, let them know.
- Do **not** change the layout yourself with `setxkbmap` in the workspace. The picture transmission
  reads it only at start, after that it no longer matches.
- Shortcuts like **Ctrl+W** or **Ctrl+T** are caught by the browser before they reach the
  application, in full screen too. In full screen, `Esc` first ends full screen.

## Sound

Whatever plays sound in the workspace, you hear it in the browser. There is no **microphone**, and
no camera either.

## Slow or stuttering?

The picture transmission computes on the server and needs CPU time, just like your programs. If
compute-heavy things run in the workspace, such as tests, a build or indexing in the IDE, the
picture can stutter briefly. If it stutters permanently, tell the administrators in which workspace
and when. They see under Operations whether your workspace is running at its limit
([chapter 35](35-wenn-etwas-nicht-geht.md)).
