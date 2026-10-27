# 36 · Terms

*For users.* The words that come up in OTA and in this handbook, in plain language.

| Term | Meaning |
|---|---|
| **Workspace** | a template created by the administrators: which programs, how much computing power, which permissions. On your start page it is a tile |
| **Desktop workspace** | a whole Linux desktop with several programs, started from a workspace |
| **Single application** | a workspace with exactly one program, without a desktop around it |
| **Session** | a started workspace that is running or paused right now |
| **Container** | the isolated environment on the server in which your session runs. When the session ends, the container can disappear, your home cannot |
| **Home** | your personal folder `/home/…`. Always kept |
| **Persistence** | what survives a restart. For you: the home; for a root workspace the system too |
| **Image** | a workspace's basic equipment: operating system and programs. When the administrators update the image, you get the new programs at the next start; your home stays |
| **Root workspace** | a workspace in which you are administrator, with Docker ([chapter 32](32-root-arbeitsplatz-nutzen.md)) |
| **Stop / resume** | for a root workspace: put it to sleep and wake it up exactly as it was |
| **Pause** | the session freezes, memory stays allocated. It continues in under a second |
| **Rebuild** | rebuild a root workspace from the current image. The home stays |
| **My files** | your exchange folder between browser and workspace (`~/Austausch`) |
| **Shared files** | files from the administrators for everyone, read-only (`~/Gemeinsam`) |
| **Group drive** | a folder for all members of a group (`~/Gruppen/…`) |
| **Control bar** | the foldable bar on the right edge of a session ([chapter 34](34-bedienung.md)) |
| **Central sign-in** | your company's sign-in page, through which you also get into OTA |
| **Second factor** | a code from an app or a passkey in addition to the password ([chapter 30](30-mein-konto.md)) |
| **Core**, CPU | computing power. The number on the tile is your share when the server is full. When it is not, you may use more |
| **Memory**, RAM | what your programs may hold in memory at the same time. If it gets more, the server ends the largest program |
| **Selkies** | the technology that transmits your workspace's picture to the browser |
| **OTA-Git**, Forgejo | OTA's Git server ([chapter 33](33-entwickeln.md)) |
| **IDE-AI**, Continue | the AI assistant in the editor ([chapter 33](33-entwickeln.md)) |
| **News** | announcements from the administrators to everyone, in the sidebar |

## Frequent questions

**Can the administrators see what I do?**
An administrator can connect to your screen or open a terminal in your workspace. Both are logged
([chapter 3](03-arbeitsplatz.md#who-else-can-see-your-screen)). Nobody looks into your
**My files**.

**Is anything lost when I close the tab?**
No. The session keeps running until you end it or it ends because it was idle. You open it again
on the start page.

**Is anything lost when the session ends?**
Not your home. In a standard workspace, everything you installed outside it
([chapter 31](31-dateien.md#what-is-still-there-after-ending)).

**Can I work from home?**
If the administrators have made OTA reachable from outside: yes, with any current browser. You do
not need to install anything on your own computer.

**Which browser?**
Chrome, Edge or Firefox, each current. In Firefox, automatic pasting needs a small add-on
([chapter 4](04-zwischenablage.md#firefox-)).
