# 22 · Your own brand — name, colour, logo ✅

*For administrators.*

OTA sits in a company and is rarely called "OpenTerminalApps" there. Three things decide whether an
installation feels like *our tool* or like third-party software: what it is called, what colour it
has and which logo is at the top left. Exactly these three can be set, and nothing more — this is not
meant to become a design kit.

Found under **Settings → Brand**. It needs the permission `settings.manage`.

## What changes

| Setting | Where it shows |
|---|---|
| **Name of the installation** | browser tab, sign-in form, start screen, name of the desktop shortcut (PWA) |
| **Accent colour** | active buttons, sliders, highlights, links — also on Keycloak's sign-in form |
| **Logo** | sign-in form, start screen, bar on the left edge, icon in the browser tab |

Everything applies immediately and for everyone — it is a setting of the installation, not of the
individual browser. The opposite of **theme** (dark/light) and **language**: those live in the
browser, because they belong to the workplace and not to the installation. (For people who never
switch, the language falls back to the installation's default language, under Settings → Language.)

## The logo

SVG, PNG, WebP or JPEG, at most 512 KB.

**An SVG may draw and nothing else.** If it contains a `<script>`, an event handler (`onload=…`) or a
`<foreignObject>`, it is rejected — with a reason, not silently trimmed. The reason: an SVG is a
document, and whoever opens it directly would get it executed on the installation's origin. Only
those who administer the installation may upload anyway; this is the second line. Whoever exports a
logo from a drawing program has none of that in it — and if they do, a PNG helps.

**Preferably square.** The same picture appears large on the sign-in form and small in the bar and
the browser tab. A wide lettering becomes very small there — it is not distorted, but it is not
readable any more either. Whoever wants both takes the square logo; the lettering is shown next to
it as the name anyway.

The logo lives in the database, not as a file on disk. That way it is in every backup and comes back
by itself on a restore — without another mount point that can be forgotten when setting up.

## The colour

One colour, given as `#RRGGBB`. For the light theme it is darkened automatically, otherwise it would
vanish on a white surface. Whoever resets it gets OTA's cool blue `#06B6D4` again — and with it its
specially tuned light variant.

**On Keycloak's sign-in form** the colour appears as well, but only from the second visit: the form
reads it from the browser without a round trip, so that it does not briefly flash in the wrong
colour — and it is only there once OTA has been opened. The **name** and the **logo** stay out of
this form; it belongs to Keycloak, and what is shown there is decided by its own theme
(`deploy/keycloak-theme/ota/`).

## What deliberately does not work

- **No second logo** for the bar. One picture, three sizes — that is the restriction that keeps this
  section small.
- **No free colours** for surfaces, text or borders. The ladder of base surface, cards and borders is
  tuned to each other and calculated through in both themes; a colour picker for it would mainly
  produce unreadable installations.
- **No brand per group.** One installation, one face.
