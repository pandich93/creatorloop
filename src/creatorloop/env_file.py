"""Update KEY=value lines of the creatorloop .env without touching other lines or comments."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path


def update(path: Path, values: Mapping[str, str]) -> None:
    """Set the given keys (every existing line of a key is replaced, missing keys are appended) in one atomic write.
    The file is readable by its owner only on POSIX: it holds the App Secret and the access token."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and key in values:
            lines[i] = f"{key}={values[key]}"
            seen.add(key)
    lines += [f"{key}={value}" for key, value in values.items() if key not in seen]
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".env.", suffix=".tmp")  # mkstemp creates it with 0600
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
