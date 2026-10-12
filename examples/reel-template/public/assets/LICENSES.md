# Bundled assets and their licences

| Folder / file | What | Source | Licence |
|---|---|---|---|
| `emoji/*.webp` | Fluent Emoji 3D (Microsoft), 256×256 RGBA, ref `fluent:<code>` | github.com/microsoft/fluentui-emoji; npm `@lobehub/fluent-emoji-3d@1.1.0` | MIT |
| `3dicons/*.webp` | 3dicons (Vijay Verma), 512 px, ref `3d:<name>` | 3dicons.co | CC0 1.0 (no attribution required) |
| `noto/*.json` | Animated Noto Emoji (Google), Lottie, ref `noto:<code>` | googlefonts.github.io/noto-emoji-animation | CC BY 4.0: the Reel caption must carry "Animated emoji: Google Noto Emoji (CC BY 4.0)" |
| `catalog.json` | every object: source, licence, uz/ru search tags | `python tools/assets.py build` | — |
| `../fonts/Inter-*.otf` | Inter typeface | rsms.me/inter | SIL Open Font License 1.1, full text in `../fonts/OFL-Inter.txt` |
| `../fonts/DejaVuSansMono*.ttf` | DejaVu Sans Mono | dejavu-fonts.github.io | Bitstream Vera / public domain changes, full text in `../fonts/LICENSE-DejaVu.txt` |
| `../track.wav` | music and sound effects | synthesised by `music/compose.py` | yours |
| Lucide icons (if added) | SVG pictograms | npm `lucide-static` | ISC |

The emoji file name is the Unicode code point (e.g. `1f916.webp` = 🤖). No brand logos are used in the template.
`tools/check.py` rejects a Reel if an object has no licence record and prints the credit line for CC BY objects.

NOT used: OpenMoji (CC BY-SA would force the same licence on the video), paid packs, "animated Fluent" from
third-party repositories (unverified origin), brand logos.

## MIT (Fluent Emoji 3D (Microsoft))
Copyright (c) Microsoft Corporation.
Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions: The above copyright notice
and this permission notice shall be included in all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.

## CC0 1.0 (3dicons (Vijay Verma))
3dicons by Vijay Verma are dedicated to the public domain under CC0 1.0: free for personal and commercial use,
copying, editing, remixing and sharing, no attribution required. https://creativecommons.org/publicdomain/zero/1.0/

## CC BY 4.0 (Animated Noto Emoji (Google))
Animated Noto Emoji © Google, licensed under Creative Commons Attribution 4.0 International.
https://creativecommons.org/licenses/by/4.0/ — credit required: "Animated emoji: Google Noto Emoji (CC BY 4.0)".
