"""One command: Reel storyboard config -> finished Reel folder ready for prepare_post / queue_post.

    python tools/make_reel.py --config ../../8-loyiha-dam-olish/reel.config.json --out ../../8-loyiha-dam-olish/reel --trial SS_PERFORMANCE

The config is written from the Reel's OWN storyboard (content/_rules/pipeline.md), not converted from the carousel.
Steps: config -> timeline -> music -> render -> Reels encode (faststart, AAC 128k) -> cover -> stop-frames +
contact sheet -> checks (first frame, safe zones, final hold, not a carousel copy).
Writes <out>/reel.mp4, cover.png, miniatyuralar.png, reel.json, reel.config.json. caption.txt: write it yourself.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BROWSER = os.getenv("REMOTION_BROWSER")  # e.g. a headless Chromium in a CI / cloud box
COVER_FRAME = 50  # hook fully composed


def run(*cmd: str, **kw) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True, **kw)


def remotion(*args: str) -> list[str]:
    # Windows ships npx as npx.cmd, which subprocess cannot run by bare name
    cmd = [shutil.which("npx") or "npx", "remotion", *args]
    return cmd + (["--browser-executable", BROWSER] if BROWSER else [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, help="reel.config.json to use (default: keep src/reel.config.json)")
    ap.add_argument("--out", type=Path, required=True, help="folder for the finished Reel")
    ap.add_argument("--trial", choices=["MANUAL", "SS_PERFORMANCE"], help="publish as a Trial Reel")
    args = ap.parse_args()
    py = sys.executable

    original = args.config.read_text(encoding="utf-8") if args.config else None
    if args.config:
        cfg = json.loads(original)
        if cfg.get("carousel") and not Path(cfg["carousel"]).is_absolute():
            # make it work from the template; keep it relative so no local absolute path ends up in src/
            carousel = (args.config.parent / cfg["carousel"]).resolve()
            try:
                cfg["carousel"] = Path(os.path.relpath(carousel, ROOT)).as_posix()
            except ValueError:  # another drive on Windows
                cfg["carousel"] = str(carousel)
        (ROOT / "src" / "reel.config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    run(py, "tools/plan.py")
    run(py, "music/compose.py")
    (ROOT / "out").mkdir(exist_ok=True)
    run(*remotion("render", "src/index.ts", "Reel", "out/render.mp4", "--codec", "h264", "--crf", "16",
                  "--concurrency", str(max(1, min(4, os.cpu_count() or 1)))))
    run("ffmpeg", "-y", "-loglevel", "error", "-i", "out/render.mp4", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
        "-profile:v", "high", "-pix_fmt", "yuv420p", "-vf", "scale=in_range=full:out_range=tv", "-color_range", "tv",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-r", "30", "-g", "60", "-bf", "0",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", "-use_editlist", "0",
        "out/reel.mp4")
    run(*remotion("still", "src/index.ts", "Reel", "out/cover.png", "--frame", str(COVER_FRAME),
                  "--props", '{"withAudio":false}'))
    shutil.rmtree(ROOT / "out" / "stills", ignore_errors=True)
    (ROOT / "out" / "stills").mkdir(parents=True)
    run("ffmpeg", "-loglevel", "error", "-i", "out/reel.mp4", "-vf", r"select=not(mod(n\,45))", "-fps_mode", "vfr",
        "-start_number", "0", "out/stills/tmp%03d.png")
    for p in (ROOT / "out" / "stills").glob("tmp*.png"):
        p.rename(p.with_name(f"f{int(p.stem[3:]) * 45:04d}.png"))
    run(py, "scripts/sheet.py", "out/sheet.png", "6")
    ok = subprocess.run([py, "tools/check.py"], cwd=ROOT).returncode == 0

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.mp4"):
        old.unlink()  # a Reel folder must hold exactly one video
    shutil.copy(ROOT / "out" / "reel.mp4", out / "reel.mp4")
    shutil.copy(ROOT / "out" / "cover.png", out / "cover.png")
    shutil.copy(ROOT / "out" / "sheet.png", out / "miniatyuralar.png")
    if original is not None:  # keep the relative carousel path as written
        (out / "reel.config.json").write_text(original, encoding="utf-8")
    else:
        shutil.copy(ROOT / "src" / "reel.config.json", out / "reel.config.json")
    reel = {"cover_ms": round(COVER_FRAME / 30 * 1000), "share_to_feed": True}
    if args.trial:
        reel["trial"] = args.trial
    (out / "reel.json").write_text(json.dumps(reel) + "\n", encoding="utf-8")
    print(f"\n{'OK' if ok else 'CHECKS FAILED'}: {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
