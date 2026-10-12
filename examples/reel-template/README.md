# Reel template (Remotion)

A 1080×1920, 30 fps Reel rendered from **its own storyboard** — not the carousel turned into a slideshow
(see `docs/content-pipeline.md`). Original music (`music/compose.py`, synthesised, no samples), 3D objects and
one visual metaphor per point. The finished folder goes straight into `prepare_post` / `queue_post`.

> **Remotion licence.** This template uses [Remotion](https://www.remotion.dev), which is free for individuals and
> small companies but requires a company licence above a certain size. Check
> [remotion.dev/license](https://www.remotion.dev/license) before using it commercially. creatorloop's MIT licence
> covers this template's own code, not Remotion.

## Requirements

- Node.js 20+ and `ffmpeg` 5.1+ on `PATH`
- Python 3.10+ with `pip install numpy scipy soundfile pyloudnorm pillow`
- WebGL for the effects (see below), or `"effects": false` in the config

## One command

```bash
cd examples/reel-template
npm install
python tools/make_reel.py --config ../sample-reel/reel.config.json --out ../sample-reel/out --trial SS_PERFORMANCE
```

`--out` receives `reel.mp4`, `cover.png`, `miniatyuralar.png` (contact sheet), `reel.json` and a copy of
`reel.config.json`. Write `caption.txt` yourself, then copy the folder into your creatorloop content folder and ask
Claude to prepare or queue it.

## reel.config.json

```json
{
  "handle": "@YOUR.HANDLE",
  "theme": "light",                    // light | dark | amber — match the post's mood
  "carousel": "../sample-carousel/build.py",  // the matching carousel: "not a copy" check
  "scenes": [
    {"type": "hook", "rows": ["A PROJECT", "[THAT WORKS]", "IN 48 HOURS"], "kicker": ["SATURDAY", "→", "SUNDAY"], "heroes": ["1f6e0-fe0f"]},
    {"type": "montage", "rows": ["8 IDEAS."], "heroes": ["1f916", "23f0"]},
    {"type": "point", "label": "FOR CUSTOMERS", "rows": ["THE BOT", "[ANSWERS FOR YOU]"], "hero": "1f916",
     "visual": {"kind": "chat", "ask": "...", "answer": "..."}},
    {"type": "outro", "bg": "amber", "rows": ["PICK ONE", "[THIS WEEK]"]},
    {"type": "final", "cta": "SAVE THIS", "sub": "The full list is in the carousel.", "signature": ["Your Name · what you do."]}
  ]
}
```

- `beats` on a scene — length in beats (0.5 s). Defaults: hook 4, montage 4, point 8, compare 8, outro 4, final 8.
- `bg` on a scene — a different background for ONE key moment only.
- `[...]` — the row gets a highlight.
- Metaphors `visual.kind`: `chat {ask, answer}`, `notify {title, rows}`, `receipt {rows, totalLabel, total, strike?}`,
  `terminal {cmd, out}`, `counter {from, to, prefix?, suffix?, caption}`, `beforeafter {bad, good}`,
  `checklist {items}`, `chart {bars:[{label,value}], caption}`.
- Objects (`hero`, `heroes`, `visual.bot`, `visual.icon`): `fluent:2615` (or just `2615`), `3d:wallet`, `noto:1f525`
  (animated Lottie). Search: `python tools/assets.py find coffee` (tags are in Uzbek and Russian today; English tags
  are welcome as a contribution). All objects on one image: `python tools/assets.py sheet` → `public/assets/assets.png`.
- `tools/from_carousel.py ../sample-carousel/build.py` drafts a config from a carousel script (reads its `HANDLE`,
  `SIGNATURE` and slide dicts without running it). Rewrite the hook afterwards — the Reel needs its own first frame.

## Effects

- `[...]` is drawn as a hand-made marker on the beat (`@remotion/rough-notation`); `"highlight": "bar"` keeps a flat bar.
- In `compare` scenes the "before" side is struck through by hand.
- Hero objects get a soft shadow and one shine (`@remotion/effects`); a light leak on the drop.
- Effects need WebGL: `remotion.config.ts` uses `angle` on Windows/macOS and `swangle` on Linux/cloud; override with
  `REMOTION_GL=...`. No WebGL → `"effects": false` in the config turns all effects off.

## What the template does for you

The music drop lands on the second scene, where all objects fly in; a warm flash; transitions alternate (through the
camera and a wipe — always a wipe when the background changes); objects bob on the beat; a "02 / 04" counter on top.

`tools/check.py` fails the render when:
1. frame 0 has no text (the first-second rule);
2. anything sits in the Reels UI zones (top 250 px, bottom 350 px);
3. the final card is still moving;
4. the Reel copies its carousel (same hook, more than half of the slide titles, as many points as slides);
5. an object has no licence record (CC BY objects print the credit line your caption must carry).

## Object library

| Source | Ref | Licence | How to add |
|---|---|---|---|
| Fluent Emoji 3D (Microsoft) | `fluent:<code>` | MIT | `python tools/assets.py add-fluent 1f355` |
| 3dicons (Vijay Verma) | `3d:<name>` | CC0 | `python tools/assets.py import-3d archive.zip wallet=wallet-iso-color.png` |
| Animated Noto Emoji (Google) | `noto:<code>` | CC BY 4.0 | `python tools/assets.py import-noto folder_with_json` |

After adding: tags in `tools/catalog_tags.py`, then `python tools/assets.py build && python tools/assets.py sheet`.
Licences of every bundled file: `public/assets/LICENSES.md`.
