from __future__ import annotations

from pathlib import Path

import pytest

from creatorloop import tunnel


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("darwin", Path("/opt/homebrew/bin/cloudflared")),
        ("darwin", Path("/usr/local/bin/cloudflared")),
        ("linux", Path("/usr/bin/cloudflared")),
        ("linux", Path("/usr/local/bin/cloudflared")),
    ],
)
def test_unix_fallbacks(platform, expected, tmp_path):
    candidates = tunnel._fallback_candidates(platform, home=tmp_path, env={})
    assert expected in candidates
    assert tmp_path / ".local" / "bin" / "cloudflared" in candidates


def test_windows_fallbacks(tmp_path):
    env = {"LOCALAPPDATA": str(tmp_path), "ProgramFiles": r"C:\Program Files"}
    pkg = tmp_path / "Microsoft" / "WinGet" / "Packages" / "Cloudflare.cloudflared_abc"
    pkg.mkdir(parents=True)
    (pkg / "cloudflared.exe").write_bytes(b"")
    candidates = tunnel._fallback_candidates("win32", home=tmp_path, env=env)
    assert tmp_path / "Microsoft" / "WinGet" / "Links" / "cloudflared.exe" in candidates
    assert Path(r"C:\Program Files") / "cloudflared" / "cloudflared.exe" in candidates
    assert pkg / "cloudflared.exe" in candidates


def test_find_uses_fallback_when_not_on_path(tmp_path, monkeypatch):
    binary = tmp_path / "cloudflared"
    binary.write_bytes(b"")
    monkeypatch.delenv("CLOUDFLARED_PATH", raising=False)
    monkeypatch.setattr(tunnel.shutil, "which", lambda name: None)
    monkeypatch.setattr(tunnel, "_fallback_candidates", lambda *a, **kw: [tmp_path / "missing", binary])
    assert tunnel.find_cloudflared() == str(binary)


def test_find_prefers_env_override(tmp_path, monkeypatch):
    binary = tmp_path / "my-cloudflared"
    binary.write_bytes(b"")
    monkeypatch.setenv("CLOUDFLARED_PATH", str(binary))
    assert tunnel.find_cloudflared() == str(binary)


@pytest.mark.parametrize(
    ("platform", "needle"),
    [("win32", "winget install"), ("darwin", "brew install cloudflared"), ("linux", "pkg.cloudflare.com")],
)
def test_install_hint_per_platform(platform, needle):
    assert needle in tunnel.install_hint(platform)
