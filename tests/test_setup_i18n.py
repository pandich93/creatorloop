import re

import pytest

from creatorloop.meta_auth import SCOPES
from creatorloop.setup_i18n import DEFAULT, LANGS, STRINGS, pick_language

ERROR_CODES = ["bad_app_id", "bad_app", "no_app", "access_denied", "missing_permissions", "no_pages", "no_instagram",
               "bad_state", "code_exchange", "network", "meta_error"]


def placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def test_every_language_has_the_same_keys():
    for lang in LANGS:
        assert STRINGS[lang].keys() == STRINGS[DEFAULT].keys(), lang


def test_placeholders_match_english():
    for lang in LANGS:
        for key, text in STRINGS[DEFAULT].items():
            assert placeholders(STRINGS[lang][key]) == placeholders(text), (lang, key)


def test_every_error_code_and_scope_has_a_text():
    for code in ERROR_CODES:
        assert f"err_{code}" in STRINGS[DEFAULT]
    for scope in SCOPES:
        assert f"perm_{scope}" in STRINGS[DEFAULT]


@pytest.mark.parametrize(
    ("header", "override", "expected"),
    [
        ("ru-RU,ru;q=0.9,en;q=0.8", None, "ru"),
        ("uz-Latn-UZ,uz;q=0.9", None, "uz"),
        ("de-DE,de;q=0.9", None, "en"),
        ("de-DE,ru;q=0.5", None, "ru"),
        (None, None, "en"),
        ("ru", "uz", "uz"),
        ("ru", "xx", "ru"),
    ],
)
def test_pick_language(header, override, expected):
    assert pick_language(header, override) == expected
