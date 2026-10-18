"""Reel template object catalog: tags in all three languages, catalog.json in sync, `find` searches uz / ru / en."""

import importlib.util
import json
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "examples" / "reel-template" / "tools"


def load_tool(name: str):
    spec = importlib.util.spec_from_file_location(f"reel_{name}", TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def assets():
    return load_tool("assets")


def test_every_object_has_uz_ru_en_tags(assets):
    tags = load_tool("catalog_tags").TAGS
    refs = {i["ref"] for i in json.loads(assets.CATALOG.read_text(encoding="utf-8"))["items"]}
    assert set(tags) == refs
    for ref, langs in tags.items():
        assert len(langs) == 3 and all(t.strip() for t in langs), ref


def test_committed_catalog_is_up_to_date(assets, tmp_path, monkeypatch, capsys):
    committed = json.loads(assets.CATALOG.read_text(encoding="utf-8"))
    monkeypatch.setattr(assets, "CATALOG", tmp_path / "catalog.json")
    assert assets.build() == committed, "run: python tools/assets.py build"
    assert "without tags" not in capsys.readouterr().out


@pytest.mark.parametrize("word", ["coffee", "kofe", "кофе", "Coffee"])
def test_find_searches_all_languages(assets, capsys, word):
    assets.find([word])
    refs = {line.split()[0] for line in capsys.readouterr().out.splitlines()}
    assert {"fluent:2615", "3d:takeaway-cup", "3d:tea-cup"} <= refs
