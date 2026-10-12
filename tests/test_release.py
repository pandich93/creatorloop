"""Release metadata stays consistent: the MCP Registry rejects a publish otherwise."""

import json
import tomllib
from pathlib import Path

import creatorloop

ROOT = Path(__file__).resolve().parents[1]


def test_server_json_matches_package():
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert server["version"] == creatorloop.__version__
    [pkg] = server["packages"]
    assert pkg["registryType"] == "pypi"
    assert pkg["identifier"] == project["name"]
    assert pkg["version"] == creatorloop.__version__
    assert pkg["transport"] == {"type": "stdio"}


def test_readme_carries_registry_ownership_marker():
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert f"<!-- mcp-name: {server['name']} -->" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_changelog_has_current_version():
    assert f"## [{creatorloop.__version__}]" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
