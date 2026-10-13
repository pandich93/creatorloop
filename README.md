<!-- mcp-name: io.github.pandich93/creatorloop -->
<div align="center">

# creatorloop

**Open-source AI content studio for Instagram creators, built on Claude and the official Instagram API.**

Analyse what works → make Reels and carousels → publish or queue them → review how they did. All from a chat with Claude.

[![CI](https://github.com/pandich93/creatorloop/actions/workflows/ci.yml/badge.svg)](https://github.com/pandich93/creatorloop/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/creatorloop.svg)](https://pypi.org/project/creatorloop/)
[![Python](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

[Русский](https://github.com/pandich93/creatorloop/blob/main/README.ru.md) · [Oʻzbekcha](https://github.com/pandich93/creatorloop/blob/main/README.uz.md)

![creatorloop demo](https://raw.githubusercontent.com/pandich93/creatorloop/main/docs/media/demo.gif)

</div>

## Why

There are plenty of "Instagram API for Claude" servers. creatorloop is built for the **creator's loop** instead:

- **Learn from data, not vibes.** Best and worst posts with their hooks, format comparison, follows per 1,000 reach,
  Reels watch time, best day and hour — and which captions (language, question hook, CTA, length) actually work.
- **Spy on competitors legally.** Track professional accounts, keep their follower history, and get alerted to the
  posts that did N× better than their median. Analyse any public post by URL, slides included.
- **Make the content.** A Remotion Reel template with automatic checks (first-second rule, safe zones, "not a copy of
  the carousel"), original music and licensed 3D objects.
- **Publish safely.** Two-step publishing with a preview, a queue with fingerprints (a changed file blocks the post),
  24 h / 72 h post reviews and comment replies — every public action needs your explicit OK.
- **Official API only.** No scraping, no browser automation, no risk to your account.

## Quick start

You need [uv](https://docs.astral.sh/uv/getting-started/installation/), [Claude Desktop](https://claude.ai/download),
an Instagram **Business or Creator** account linked to a **Facebook Page**, and your own Meta app
([5-minute guide](https://github.com/pandich93/creatorloop/blob/main/docs/meta-setup.md)).

```bash
uvx --from creatorloop creatorloop-setup        # 1. connect to Claude Desktop, create the settings file
```

2. Put your app's `META_APP_ID` and `META_APP_SECRET` into the settings file the command printed.
3. Save a 60-day token and find your account ID (the short-lived token comes from Graph API Explorer, see the guide):

```bash
uvx --from creatorloop creatorloop-auth exchange --short-token <TOKEN> --write
uvx --from creatorloop creatorloop-auth whoami --write
uvx --from creatorloop creatorloop-auth check   # → OK: @your_account followers=...
```

Restart Claude Desktop and ask: *"How did my last 10 posts do, and what should I post next?"*

<details>
<summary>Installing uv</summary>

| System | Command |
|---|---|
| Windows | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| macOS | `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Linux | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

uv downloads Python 3.14 by itself if you don't have it.
</details>

`creatorloop-setup` finds the Claude Desktop config on Windows (including the Microsoft Store build), macOS and Linux,
keeps your other servers, makes a backup and creates your settings file. Claude Desktop rewrites its config while it
runs, so on macOS the command quits and reopens it for you; on Windows and Linux it asks you to quit it first.

<details>
<summary>Running in Docker instead of uv</summary>

Build the image straight from GitHub and keep your settings in a folder on your computer:

```bash
docker build -t creatorloop https://github.com/pandich93/creatorloop.git
mkdir "$HOME/creatorloop"
```

Create a `.env` file in that folder with `META_APP_ID`, `META_APP_SECRET` and `IG_TIMEZONE` (the container runs
in UTC), then save the token and account ID:

```bash
docker run --rm -v "$HOME/creatorloop:/data" --entrypoint creatorloop-auth creatorloop exchange --short-token <TOKEN> --write
docker run --rm -v "$HOME/creatorloop:/data" --entrypoint creatorloop-auth creatorloop whoami --write
```

`creatorloop-setup` doesn't run inside Docker, so add the server to `claude_desktop_config.json` yourself, with the
full path to the folder:

```json
{
  "mcpServers": {
    "creatorloop": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-v", "/Users/you/creatorloop:/data", "creatorloop"]
    }
  }
}
```

Post folders for `prepare_post` and `queue_post` go into `creatorloop/content/`. The image includes `cloudflared` for
publishing carousels.
</details>

## What you can ask

- "Make a report on my content for the last 60 days. Reels or carousels — what works better, and when should I post?"
- "Compare me with @competitor1 and @competitor2. Who has the higher engagement and why?"
- "Analyse this post https://www.instagram.com/p/… and write my own version of it."
- "Track @competitor and tell me every week which of their posts took off."
- "Check the hashtags #ai, #productivity and #startup. Check the quota first."
- "Queue the post from folder `my-first-reel` for the next free slot." → preview → "yes" → it goes out on time.
- "Which new comments haven't I answered? Draft replies." → you approve each reply.

Ready-made prompts in Claude Desktop's **+** menu: *Weekly Instagram report*, *Competitor brief*, *Data-driven content ideas*.

## Tools

| Area | Tools |
|---|---|
| Your account | `get_my_profile`, `get_my_media`, `get_media_insights`, `get_account_insights`, `get_audience_demographics` |
| Content analysis | `get_my_content_report`, `get_caption_insights`, `get_post_history`, `post_reviews` |
| Competitors | `get_competitor`, `compare_accounts`, `get_follower_history`, `track_competitor`, `untrack_competitor`, `list_tracked_competitors`, `update_tracked_competitors`, `find_viral_posts`, `get_competitor_post` |
| Hashtags | `search_hashtag`, `compare_hashtags`, `plan_hashtag_research` |
| Publishing | `prepare_post`, `get_post_job`, `publish_media`, `list_publications` |
| Queue | `queue_post`, `list_queue`, `cancel_queued` |
| Comments | `get_new_comments`, `reply_comment` |
| Service | `get_api_status`, `clear_cache`, `restart_server` |

33 tools in total. Tools that change something on Instagram are annotated as such for Claude, and their descriptions
tell it to act only after you approve: `publish_media` and `reply_comment` after you OK the preview or the exact
text, `queue_post` only with `confirm=true` after you saw the preview.

## Publishing

Put the files into a folder inside your **content folder** (`<creatorloop home>/content/<name>/`):

```
my-carousel/                   my-reel/
  slide_01.png … slide_10.png    reel.mp4        # H.264/HEVC, 23–60 fps, ≤1920 px wide, 3 s–15 min, ≤300 MB
  caption.txt                    caption.txt
                                 reel.json       # optional: {"cover_ms": 1667, "share_to_feed": true, "trial": "SS_PERFORMANCE"}
```

- Slides: 1–10 PNG/JPG (API limit), aspect ratio 4:5 to 1.91:1, ordered by file name. Everything below a `---` line in
  `caption.txt` is notes and is not published.
- Then: "prepare the post from folder `my-carousel`" → preview → "publish". Or queue it for a slot.
- Carousels: Instagram downloads images from a public URL, so creatorloop opens a temporary
  [Cloudflare Quick Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/)
  for that minute. Install `cloudflared` once: `winget install --id Cloudflare.cloudflared -e` (Windows),
  `brew install cloudflared` (macOS) or a package from [pkg.cloudflare.com](https://pkg.cloudflare.com/index.html) (Linux).
- Reels upload directly to Meta (no tunnel). The MP4 header is checked before upload (duration, size, width,
  `moov` first) with the exact `ffmpeg` fix if something is off.
- Queue slots default to Tue/Thu/Sun 19:00 in your timezone — an example, change `QUEUE_SLOTS` in the settings file.
  A queued post is blocked if its files or caption change after you approved it, and is marked missed if your
  computer was asleep for more than 3 hours past the slot.
- Meta's limit is 100 posts per rolling 24 hours; `list_publications` shows what is left. Publishing is never retried
  automatically, so there are no duplicates.

Making the content itself: see [`examples/`](https://github.com/pandich93/creatorloop/blob/main/examples) and the [content pipeline](https://github.com/pandich93/creatorloop/blob/main/docs/content-pipeline.md) —
a sample carousel, a sample Reel storyboard and the Remotion Reel template.

## What the Instagram API allows (and doesn't)

| | Possible | Not possible |
|---|---|---|
| **Your account** | Reach, views, likes, comments, saves, shares, profile visits, follows per post, Reels average watch time, audience demographics, account totals | Data older than 2 years; insights per carousel slide; Stories after 24 h |
| **Competitors** (Business Discovery) | Public data of Business/Creator accounts: followers, posts, bio, likes, comments, Reels views per post | Personal or private accounts; their reach, saves, shares, demographics; Stories |
| **Hashtags** | Top posts and posts from the last 24 h | More than **30 unique hashtags per rolling 7 days**; post authors; keyword, audio or trend search |
| **Follower growth** | creatorloop saves a daily snapshot for you and every competitor you look at | History before the first snapshot |

Engagement rate for your posts = Σ(likes + comments + saves + shares) / Σreach × 100 (weighted, so tiny posts don't
skew it). Posts younger than 72 h are reported separately as "still growing". Competitors' ER is per follower — the
API does not expose their reach.

## Settings

`creatorloop-setup` creates `.env` in your creatorloop home folder:

| System | Home folder |
|---|---|
| Windows | `%APPDATA%\creatorloop` |
| macOS | `~/Library/Application Support/creatorloop` |
| Linux | `~/.local/share/creatorloop` (or `$XDG_DATA_HOME/creatorloop`) |

Set `CREATORLOOP_HOME` to use another folder. The home folder holds `.env`, the `creatorloop.db` database and the
`content/` folder.

| Variable | Required | Meaning |
|---|---|---|
| `IG_ACCESS_TOKEN` | yes | Long-lived (60 days) or System User (never expires) token — see [Meta setup](https://github.com/pandich93/creatorloop/blob/main/docs/meta-setup.md) |
| `IG_USER_ID` | yes | Your Instagram professional account ID (`1784…`), not the username |
| `GRAPH_API_VERSION` | no | Default `v26.0` |
| `META_APP_ID`, `META_APP_SECRET` | no | Only for `creatorloop-auth exchange` |
| `IG_TIMEZONE` | no | IANA name, e.g. `Europe/Berlin`. Default: your computer's timezone |
| `QUEUE_SLOTS` | no | e.g. `Mon,Wed,Fri 20:00` |
| `IG_DB_PATH`, `CACHE_TTL_*_MIN` | no | Database location, cache lifetime in minutes |

The token expiry shows up in `get_api_status`, and every tool answer carries a `token_warning` 14 days before expiry.

## FAQ

<details><summary>Does it work with a personal Instagram account?</summary>
No. Meta's API only serves Business and Creator accounts linked to a Facebook Page. Switching is free:
Instagram → Settings → Account type and tools.
</details>

<details><summary>Do I need Meta App Review?</summary>
Not for your own account: keep the app in Development mode, you are its admin. Hashtag search may require the
"Instagram Public Content Access" feature for some accounts — creatorloop tells you if Meta refuses it.
</details>

<details><summary>Can it get my account banned?</summary>
creatorloop uses only the official Graph API with your own app and token, within Meta's rate limits. It does no
scraping and no browser automation.
</details>

<details><summary>Which AI clients does it work with?</summary>
It is a standard MCP server (stdio). It is developed and tested with Claude Desktop; other MCP clients that support
stdio servers should work too.
</details>

<details><summary>A metric is missing in the answer.</summary>
Meta regularly removes metrics (e.g. `impressions` and `plays` in April 2025, replaced by `views`). creatorloop
moves a refused metric to `unavailable` instead of failing and stops asking for it for 7 days. Insights can lag up to 48 h.
</details>

## Data & privacy

- Your token, settings, database and content stay on your computer in the creatorloop home folder.
- creatorloop talks to Meta only: the Instagram Graph API (`graph.facebook.com`, `rupload.facebook.com` for video
  uploads) and Instagram's media servers when it downloads the slides of a post you asked it to analyse.
- To publish carousels (and Reels, if the direct upload is refused) it opens a temporary Cloudflare Quick Tunnel to
  your local files for the minute Meta needs to fetch them, then closes it and deletes the temporary copies.
- No analytics, telemetry or third-party services.

## Development

```bash
git clone https://github.com/pandich93/creatorloop && cd creatorloop
uv sync
uv run pytest            # offline: mocked Graph API and captured response shapes
uv run creatorloop-setup # points Claude Desktop at this checkout instead of the PyPI package
```

See [CONTRIBUTING.md](https://github.com/pandich93/creatorloop/blob/main/CONTRIBUTING.md). Security issues: [SECURITY.md](https://github.com/pandich93/creatorloop/blob/main/SECURITY.md).

## Disclaimer

creatorloop is an independent open-source project. **Not affiliated with, endorsed or sponsored by Meta or
Instagram.** "Instagram" is a trademark of Meta Platforms, Inc. You are responsible for complying with the
[Meta Platform Terms](https://developers.facebook.com/terms/) and Instagram's policies when you use it.

## License

[MIT](https://github.com/pandich93/creatorloop/blob/main/LICENSE). The Reel template in `examples/reel-template` uses [Remotion](https://www.remotion.dev), which has
its own licence; bundled assets and fonts are listed in
[`examples/reel-template/public/assets/LICENSES.md`](https://github.com/pandich93/creatorloop/blob/main/examples/reel-template/public/assets/LICENSES.md).
