"""Carousel build.py (COVER / PROJECTS / FINAL dicts) -> src/reel.config.json for the Reel template.

    python tools/from_carousel.py ../sample-carousel/build.py [--out src/reel.config.json]

The carousel script is NOT executed: its dicts are read with ast.literal_eval.
Edit the resulting JSON by hand if a line reads badly in motion (shorter is better).
"""

from __future__ import annotations

import argparse
import ast
import html
import json
import re
from pathlib import Path

MISSING = object()


def literal(tree: ast.Module, name: str, default=MISSING):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    if default is not MISSING:
        return default
    raise SystemExit(f"{name} not found in the carousel script")


def plain(text: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def key_line(body: str) -> str:
    """The bold part of the slide body is the one sentence that survives in motion."""
    bold = re.findall(r"\*\*(.+?)\*\*", body)
    line = plain(bold[0] if bold else re.split(r"(?<=[.!?])\s", plain(body))[0])
    return line[:1].upper() + line[1:]


def card(p: dict) -> dict:
    code = p.get("code", "")
    lines = [ln.strip() for ln in code.splitlines() if ln.strip()]
    bad = next((ln[1:].strip() for ln in lines if ln.startswith("✗")), None)
    good = next((ln[1:].strip() for ln in lines if ln.startswith("✓")), None)
    if bad and good:
        return {"kind": "beforeafter", "bad": bad, "good": good}
    kind = "terminal" if p.get("card") == "terminal" else "text"
    return {"kind": kind, "title": p.get("card") or "", "text": code}


def convert(build_py: Path) -> dict:
    tree = ast.parse(build_py.read_text(encoding="utf-8"))
    cover, projects, final = literal(tree, "COVER"), literal(tree, "PROJECTS"), literal(tree, "FINAL")
    save = final.get("save") or ("SAVE THIS", "")
    signature = [plain(line) for line in literal(tree, "SIGNATURE", [])]
    return {
        "source": str(build_py),
        "handle": literal(tree, "HANDLE", "@YOUR.HANDLE"),
        "hook": {"label": cover.get("label", ""), "rows": cover["title"], "sub": plain(cover.get("sub", ""))},
        "items": [
            {"label": p["label"], "rows": p["title"], "line": key_line(p.get("body", "")), "card": card(p)}
            for p in projects
        ],
        "outro": {"rows": final["title"]},
        "final": {"cta": save[0], "sub": plain(save[1]), "signature": signature},
        "secondsPerItem": 4,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("build_py", type=Path)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "src" / "reel.config.json")
    args = ap.parse_args()
    cfg = convert(args.build_py)
    args.out.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.out}: {len(cfg['items'])} items")


if __name__ == "__main__":
    main()
