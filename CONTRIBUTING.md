# Contributing to creatorloop

Thanks for helping! Bug reports, setup problems, ideas and pull requests are all welcome.

## Development setup

```bash
git clone https://github.com/pandich93/creatorloop && cd creatorloop
uv sync
uv run pytest -q            # offline: the Graph API is mocked, no token needed
uv run ruff check src tests
```

To try your changes in Claude Desktop, run `uv run creatorloop-setup` from the checkout: it points Claude Desktop at
your working copy. After editing code, ask Claude to call `restart_server` — no Desktop restart needed unless you
changed dependencies or added a new tool.

Use `CREATORLOOP_HOME=/some/test/folder` to keep a test account's settings and database apart from your real ones.

## Adding a tool

1. Put API calls in `src/creatorloop/instagram.py` and pure calculations in `src/creatorloop/analytics.py`.
2. Register the tool in `src/creatorloop/server.py` with `@tool(annotations=...)`: mark read-only tools
   `readOnlyHint=True`; anything that changes Instagram must say in its description that it runs only after the user
   approves.
3. Add tests with `httpx.MockTransport` (see `tests/conftest.py`). Real response shapes go to `tests/fixtures/`
   with IDs and usernames anonymised.
4. Update the tools table in `README.md` and `CHANGELOG.md` (under *Unreleased*).

## Pull requests

- One topic per PR; tests and `ruff check` must pass on Ubuntu, macOS and Windows (CI runs all three).
- Never commit tokens, `.env` files, databases or real account data.
- Describe what you tested. If you checked against the live API, say which endpoint and API version.

## Releases (maintainer)

Bump `__version__` in `src/creatorloop/__init__.py`, both versions in `server.json` and the version in `manifest.json`
(`tests/test_release.py` fails until they match), move *Unreleased* to the new version in `CHANGELOG.md`, then push a
tag `vX.Y.Z`. The release workflow publishes to PyPI, GitHub Releases (with the Claude Desktop `.mcpb` bundle) and the
MCP Registry.

To try the bundle locally: `npx -y @anthropic-ai/mcpb@2.1.2 pack . /tmp/creatorloop.mcpb`, then open the file in
Claude Desktop. `.mcpbignore` lists what goes into it.
