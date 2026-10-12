"""Object library of the Reel template: catalog, search, import, contact sheet, licence check.

    python tools/assets.py find kofe            objects whose tags/name contain the word (uz / ru / en)
    python tools/assets.py build                rebuild public/assets/catalog.json from the files on disk
    python tools/assets.py sheet                public/assets/assets.png: every object on one picture, with its ref
    python tools/assets.py verify               every file has a catalog entry with a licence (exit 1 if not)
    python tools/assets.py add-fluent 1f355 2615      copy Fluent 3D emoji from npm @lobehub/fluent-emoji-3d (MIT)
    python tools/assets.py import-3d <zip|dir> wallet=wallet-iso-color.png ...
                                                3dicons PNG (CC0) -> public/assets/3dicons/<name>.webp, 512 px
    python tools/assets.py import-noto <dir>    Lottie JSON files named <code>.json (animated Noto, CC BY 4.0)

Refs used in reel.config.json: "fluent:<code>" (or bare code), "3d:<name>", "noto:<code>".
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import tarfile
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "public" / "assets"
CATALOG = ASSETS / "catalog.json"
CACHE = Path.home() / ".cache" / "reel-template"

SOURCES = {
    "fluent": {
        "dir": "emoji", "ext": "webp", "license": "MIT",
        "title": "Fluent Emoji 3D (Microsoft)", "url": "https://github.com/microsoft/fluentui-emoji",
    },
    "3d": {
        "dir": "3dicons", "ext": "webp", "license": "CC0-1.0",
        "title": "3dicons (Vijay Verma)", "url": "https://3dicons.co",
    },
    "noto": {
        "dir": "noto", "ext": "json", "license": "CC-BY-4.0",
        "title": "Animated Noto Emoji (Google)", "url": "https://googlefonts.github.io/noto-emoji-animation/",
        "attribution": "Animated emoji: Google Noto Emoji (CC BY 4.0)",
    },
}
FLUENT_NPM = "https://registry.npmjs.org/@lobehub/fluent-emoji-3d/-/fluent-emoji-3d-1.1.0.tgz"


def parse_ref(ref: str) -> tuple[str, str]:
    if ":" not in ref:
        return "fluent", ref
    src, _, ident = ref.partition(":")
    if src not in SOURCES:
        raise ValueError(f"unknown source in {ref!r} (use fluent:, 3d: or noto:)")
    return src, ident


def file_of(ref: str) -> Path:
    src, ident = parse_ref(ref)
    s = SOURCES[src]
    return ASSETS / s["dir"] / f"{ident}.{s['ext']}"


def char_of(code: str) -> str:
    try:
        return "".join(chr(int(p, 16)) for p in code.split("-"))
    except ValueError:
        return ""


def name_of(src: str, ident: str) -> str:
    if src in ("fluent", "noto"):
        ch = char_of(ident).replace("️", "")
        try:
            return unicodedata.name(ch[0]).lower() if ch else ident
        except (ValueError, IndexError):
            return ident
    return ident.replace("-", " ")


# ------------------------------------------------------------------------------------------------ catalog
def build() -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    from catalog_tags import TAGS

    items, untagged = [], []
    for src, s in SOURCES.items():
        d = ASSETS / s["dir"]
        for f in sorted(d.glob(f"*.{s['ext']}")) if d.exists() else []:
            ref = f"{src}:{f.stem}"
            uz, ru = TAGS.get(ref, ("", ""))
            if not uz:
                untagged.append(ref)
            items.append({
                "ref": ref, "file": f.relative_to(ROOT / "public").as_posix(), "source": s["title"],
                "license": s["license"], "char": char_of(f.stem) if src != "3d" else "",
                "name": name_of(src, f.stem), "animated": src == "noto",
                "uz": [t.strip() for t in uz.split(",") if t.strip()],
                "ru": [t.strip() for t in ru.split(",") if t.strip()],
            })
    cat = {"sources": SOURCES, "items": items}
    CATALOG.write_text(json.dumps(cat, ensure_ascii=False, indent=1), encoding="utf-8")
    by = {k: sum(i["ref"].startswith(k + ":") for i in items) for k in SOURCES}
    print(f"catalog: {len(items)} objects {by}")
    if untagged:
        print(f"warning: {len(untagged)} without tags (add them to tools/catalog_tags.py): {', '.join(untagged[:12])}")
    return cat


def load() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.exists() else build()


def find(words: list[str]) -> None:
    q = " ".join(words).lower()
    hits = [i for i in load()["items"] if q in " ".join([i["ref"], i["name"], *i["uz"], *i["ru"]]).lower()]
    for i in hits:
        anim = " (anim)" if i["animated"] else ""
        print(f"{i['ref']:<22} {i['char']:<3} {', '.join(i['uz'][:3])} | {', '.join(i['ru'][:2])}{anim}")
    if not hits:
        print("nothing found; try another word or: python tools/assets.py sheet")


def check_refs(refs: list[str]) -> list[str]:
    """Problems for refs used in a reel: missing file, no catalog entry, no licence."""
    cat = {i["ref"]: i for i in load()["items"]}
    out = []
    for ref in sorted(set(refs)):
        try:
            src, ident = parse_ref(ref)
        except ValueError as e:
            out.append(str(e))
            continue
        full = f"{src}:{ident}"
        if not file_of(ref).exists():
            out.append(f"object {ref}: file {file_of(ref).relative_to(ROOT)} is missing")
        elif full not in cat or not cat[full].get("license"):
            out.append(f"object {ref}: no licence entry in catalog.json (run: python tools/assets.py build)")
    return out


def attributions(refs: list[str]) -> list[str]:
    """Credit lines the caption must carry for the objects used (CC BY sources)."""
    return sorted({SOURCES[parse_ref(r)[0]].get("attribution", "") for r in refs} - {""})


def verify() -> int:
    cat = {i["ref"] for i in build()["items"]}
    lic = (ASSETS / "LICENSES.md").read_text(encoding="utf-8")
    bad = [s["title"] for k, s in SOURCES.items() if any(r.startswith(k + ":") for r in cat) and s["title"] not in lic]
    for b in bad:
        print(f"FAIL LICENSES.md has no section for {b}")
    print("ok  every object has a licence" if not bad else "")
    return 1 if bad else 0


# ------------------------------------------------------------------------------------------------ import
def add_fluent(codes: list[str]) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    tgz = CACHE / "fluent-emoji-3d-1.1.0.tgz"
    if not tgz.exists():
        print("downloading", FLUENT_NPM)
        urllib.request.urlretrieve(FLUENT_NPM, tgz)
    with tarfile.open(tgz) as t:
        names = {Path(m.name).stem: m for m in t.getmembers() if m.name.endswith(".webp")}
        for c in codes:
            m = names.get(c) or names.get(c + "-fe0f")
            if not m:
                print(f"skip {c}: not in Fluent 3D")
                continue
            out = ASSETS / "emoji" / Path(m.name).name
            out.write_bytes(t.extractfile(m).read())
            print("added", f"fluent:{out.stem}")
    build()


def import_3d(src: str, pairs: list[str]) -> None:
    from PIL import Image

    out_dir = ASSETS / "3dicons"
    out_dir.mkdir(exist_ok=True)
    p = Path(src)
    opener = zipfile.ZipFile(p) if p.suffix == ".zip" else None
    files = opener.namelist() if opener else [str(x.relative_to(p)) for x in p.rglob("*.png")]
    for pair in pairs:
        name, _, pattern = pair.partition("=")
        match = [f for f in files if f.lower().endswith(pattern.lower())]
        if not match:
            print(f"skip {name}: no file ending with {pattern}")
            continue
        data = opener.read(match[0]) if opener else (p / match[0]).read_bytes()
        im = Image.open(io.BytesIO(data)).convert("RGBA")
        im.thumbnail((512, 512))
        im.save(out_dir / f"{name}.webp", "WEBP", quality=88, method=6)
        print("added", f"3d:{name}", "<-", match[0])
    build()


def import_noto(src: str) -> None:
    out_dir = ASSETS / "noto"
    out_dir.mkdir(exist_ok=True)
    for f in sorted(Path(src).glob("*.json")):
        json.loads(f.read_text(encoding="utf-8"))  # must be valid Lottie JSON
        shutil.copy(f, out_dir / f.name)
        print("added", f"noto:{f.stem}")
    build()


# ------------------------------------------------------------------------------------------------ contact sheet
def sheet() -> Path:
    from PIL import Image, ImageDraw, ImageFont

    items = load()["items"]
    cols, tile, lab = 10, 180, 44
    rows = (len(items) + cols - 1) // cols
    img = Image.new("RGB", (cols * tile, rows * (tile + lab) + 70), "#f4efe6")
    d = ImageDraw.Draw(img)
    fnt = ImageFont.truetype(str(ROOT / "public" / "fonts" / "Inter-SemiBold.otf"), 17)
    big = ImageFont.truetype(str(ROOT / "public" / "fonts" / "Inter-Black.otf"), 30)
    d.text((20, 18), f"Reel template objects: {len(items)}  (ref -> reel.config.json)", font=big, fill="#1b1b1b")
    for k, it in enumerate(items):
        x, y = (k % cols) * tile, 70 + (k // cols) * (tile + lab)
        f = ROOT / "public" / it["file"]
        if it["animated"]:
            # Lottie cannot be drawn here: show the still Fluent twin (same code) with an ANIM badge
            twin = ASSETS / "emoji" / f"{it['ref'].split(':')[1]}.webp"
            d.rounded_rectangle((x + 8, y + 8, x + tile - 8, y + tile - 8), 22, fill="#ffe7a8")
            if twin.exists():
                ob = Image.open(twin).convert("RGBA")
                ob.thumbnail((tile - 50, tile - 50))
                img.paste(ob, (x + (tile - ob.width) // 2, y + (tile - ob.height) // 2), ob)
            d.rounded_rectangle((x + 14, y + 14, x + 84, y + 40), 8, fill="#1b1b1b")
            d.text((x + 49, y + 27), "ANIM", font=fnt, fill="#ffd166", anchor="mm")
        else:
            ob = Image.open(f).convert("RGBA")
            ob.thumbnail((tile - 30, tile - 30))
            img.paste(ob, (x + (tile - ob.width) // 2, y + (tile - ob.height) // 2), ob)
        d.text((x + tile / 2, y + tile + 4), it["ref"], font=fnt, fill="#1b1b1b", anchor="mt")
        d.text((x + tile / 2, y + tile + 24), (it["uz"] or [""])[0], font=fnt, fill="#7a6f60", anchor="mt")
    out = ASSETS / "assets.png"
    img.save(out, optimize=True)
    print("sheet:", out.relative_to(ROOT), img.size)
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "find":
        find(rest)
    elif cmd == "build":
        build()
    elif cmd == "sheet":
        sheet()
    elif cmd == "verify":
        return verify()
    elif cmd == "add-fluent":
        add_fluent(rest)
    elif cmd == "import-3d":
        import_3d(rest[0], rest[1:])
    elif cmd == "import-noto":
        import_noto(rest[0])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
