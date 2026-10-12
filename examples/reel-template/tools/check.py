"""Automatic checks on rendered stop-frames (out/stills/fNNNN.png):

1. Rule of the first second: frame 0 must carry text (enough pixels far from the background colour).
2. Safe zones: the top 250 px and bottom 350 px stay clean (Reels UI covers them). Frames next to a wipe are skipped.
3. The final card holds still for at least 2 s.
4. The Reel is NOT a copy of its carousel ("carousel" in reel.config.json): different hook, at most half of the
   slide titles reused, fewer point scenes than slides (no "one slide = one scene" rhythm).
5. Every object used (hero, heroes, visual.bot, visual.icon) exists and has a licence in public/assets/catalog.json;
   CC BY objects print the credit line the caption must carry.

    python tools/check.py        -> exit code 1 if anything fails
"""

from __future__ import annotations

import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
STILLS = ROOT / "out" / "stills"
TOP, BOTTOM = 250, 350
FPB = 15


def load(frame: int) -> np.ndarray:
    return np.asarray(Image.open(STILLS / f"f{frame:04d}.png").convert("RGB"), dtype=np.int16)


def text_fraction(img: np.ndarray) -> float:
    bg = np.median(img.reshape(-1, 3), axis=0)
    far = np.abs(img - bg).sum(axis=2) > 120
    return float(far.mean())


def band_dirty(band: np.ndarray) -> float:
    bg = np.median(band.reshape(-1, 3), axis=0)
    return float((np.abs(band - bg).sum(axis=2) > 90).mean())


def norm(rows: list[str]) -> str:
    return re.sub(r"[^\w\s]", "", " ".join(rows).replace("[", "").replace("]", "")).upper().strip()


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def carousel_problems(cfg: dict) -> list[str]:
    src = cfg.get("carousel")
    if not src:
        print("--  no 'carousel' in reel.config.json: similarity check skipped")
        return []
    path = Path(src) if Path(src).is_absolute() else (ROOT / src).resolve()
    if not path.exists():
        return [f"carousel script not found: {path}"]
    sys.path.insert(0, str(ROOT / "tools"))
    from from_carousel import convert  # noqa: E402

    car = convert(path)
    problems = []
    hook = next((s for s in cfg["scenes"] if s["type"] == "hook"), None)
    if hook and similar(norm(hook.get("rows", [])), norm(car["hook"]["rows"])) > 0.6:
        problems.append("the Reel hook repeats the carousel cover: write a different first frame")
    reel_titles = [norm(s.get("rows", [])) for s in cfg["scenes"] if s.get("rows")]
    reused = [norm(it["rows"]) for it in car["items"] if any(similar(norm(it["rows"]), r) > 0.8 for r in reel_titles)]
    if len(reused) > len(car["items"]) / 2:
        problems.append(f"{len(reused)} of {len(car['items'])} slide titles reused in the Reel (max half): {reused}")
    points = sum(1 for s in cfg["scenes"] if s["type"] == "point")
    if points >= len(car["items"]):
        problems.append(f"{points} point scenes for {len(car['items'])} slides: that is the carousel as a slideshow")
    if not problems:
        print(f"ok  not a carousel copy (hook differs, {len(reused)}/{len(car['items'])} titles reused, {points} points)")
    return problems


def object_refs(cfg: dict) -> list[str]:
    refs = []
    for sc in cfg.get("scenes", []):
        refs += [r for r in [sc.get("hero"), *sc.get("heroes", [])] if r]
        v = sc.get("visual") or {}
        refs += [v[k] for k in ("bot", "icon") if v.get(k)]
    return refs


def object_problems(cfg: dict) -> list[str]:
    sys.path.insert(0, str(Path(__file__).parent))
    import assets

    refs = object_refs(cfg)
    probs = assets.check_refs(refs)
    if not probs:
        print(f"ok  {len(set(refs))} objects, all licensed")
    for line in assets.attributions(refs):
        print(f"NOTE caption must credit: {line}")
    return probs


def main() -> int:
    tl = json.loads((ROOT / "src" / "timeline.json").read_text(encoding="utf-8"))
    cuts = [round(c * FPB) for c in tl["cuts"]]
    frames = sorted(int(p.stem[1:]) for p in STILLS.glob("f*.png"))
    problems = []

    if 0 not in frames:
        problems.append("frame 0 was not rendered")
    elif (frac := text_fraction(load(0))) < 0.015:
        problems.append(f"frame 0 is almost empty ({frac:.1%} text pixels): the hook must be visible at once")
    else:
        print(f"ok  frame 0 carries text ({frac:.1%} of pixels)")

    dirty = []
    for fr in frames:
        if any(abs(fr - c) <= 8 for c in cuts) or abs(fr - round(tl["dropBeat"] * FPB)) <= 8:
            continue
        img = load(fr)
        top, bottom = band_dirty(img[:TOP]), band_dirty(img[-BOTTOM:])
        if top > 0.002 or bottom > 0.002:
            dirty.append(f"f{fr} (top {top:.1%}, bottom {bottom:.1%})")
    if dirty:
        problems.append("content inside the Reels UI zones: " + ", ".join(dirty))
    else:
        print("ok  safe zones clean")

    final_start = round(tl["finalBeat"] * FPB)
    total = round(tl["totalBeats"] * FPB)
    tail = [fr for fr in frames if fr >= final_start + 20]
    if len(tail) >= 2 and (tail[-1] - tail[0]) >= 45:
        diff = np.abs(load(tail[0]) - load(tail[-1])).mean()
        if diff > 1.0:
            problems.append(f"final card is still moving (mean diff {diff:.2f})")
        else:
            print(f"ok  final card holds {(total - tail[0]) / 30:.1f} s")
    cfg = json.loads((ROOT / "src" / "reel.config.json").read_text(encoding="utf-8"))
    problems += carousel_problems(cfg)
    problems += object_problems(cfg)
    for p in problems:
        print("FAIL", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
