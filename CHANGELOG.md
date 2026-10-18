# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Reel template: English search tags for all 167 objects in the object catalog; `python tools/assets.py find`
  now searches Uzbek, Russian and English tags (`find coffee`, `find kofe` and `find кофе` give the same objects).
- One-click install for Claude Desktop: every GitHub Release carries a `creatorloop-X.Y.Z.mcpb` bundle
  (`manifest.json`, `uv` server type). The access token and account ID are optional, masked fields: leave them empty
  and connect through `open_setup`. CI packs the bundle and checks that it starts and lists the tools.

### Fixed
- An empty `IG_ACCESS_TOKEN` / `IG_USER_ID` environment variable no longer hides the values saved in `.env`.

## [0.2.0] - 2026-10-14

### Added
- `Dockerfile` to run the server without a local Python (settings and data in a `/data` volume, `cloudflared`
  included); CI builds the image and checks that it answers MCP `initialize` and lists the tools.
- Setup page: `creatorloop-setup`, `creatorloop-auth login` and the new `open_setup` tool open a local page that
  checks your Meta app, logs in with Facebook, finds your Instagram account and saves the settings — no Graph API
  Explorer, no editing `.env`, no restart when started from Claude. English, Russian and Uzbek.

### Changed
- `.env` is written atomically and readable by its owner only.
- Errors about missing settings or an expired token point to `open_setup` / `creatorloop-auth login`.

## [0.1.0] - 2026-10-13

First public release.

### Added
- MCP server with 33 tools for one Instagram professional account via the official Instagram Graph API v26.0:
  own analytics and content reports, caption insights, audience demographics, competitor analysis and tracking
  (Business Discovery), viral-post detection, post analysis by URL, hashtag research with a 30-per-week quota guard.
- Two-step publishing of carousels and Reels (resumable upload for Reels), a publishing queue with fingerprints,
  24 h / 72 h post reviews, new-comment inbox and replies.
- `creatorloop-setup`: connects Claude Desktop on Windows (incl. Microsoft Store), macOS and Linux; quits and reopens
  Claude Desktop on macOS so it does not overwrite the config.
- `creatorloop-auth`: token exchange, account ID lookup, token check.
- Per-user home folder (`CREATORLOOP_HOME`) for settings, database and content; system timezone by default.
- Three MCP prompts: weekly report, competitor brief, data-driven content ideas.
- `examples/`: a sample carousel, a sample Reel storyboard and a Remotion Reel template with automatic checks.

[Unreleased]: https://github.com/pandich93/creatorloop/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/pandich93/creatorloop/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/pandich93/creatorloop/releases/tag/v0.1.0
