"""Sample carousel: 10 slides (1080x1350 PNG) rendered from HTML with Playwright.

    pip install playwright && playwright install chromium
    python build.py            # -> slides/slide_01.png ... slide_10.png

Edit HANDLE, SIGNATURE and the COVER / PROJECTS / FINAL dicts. The Reel template reads these dicts
(without running this script) to check that the Reel is not a copy of the carousel.
"""

import asyncio
import html
import re
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path(__file__).resolve().parent / "slides"
OUT.mkdir(parents=True, exist_ok=True)

TOTAL = 10
HANDLE = "@YOUR.HANDLE"
SIGNATURE = ["<b>Your Name</b> · what you do.", "One line about why people should follow you."]

COVER = {
    "label": "WEEKEND BUILDS",
    "title": ["8 PROJECTS", "FOR ONE", "[WEEKEND]"],
    "sub": "Each one comes with a ready prompt.<br>Start on Saturday, it works by Sunday.",
}

PROJECTS = [
    {
        "label": "FOR CUSTOMERS",
        "title": ["CHAT BOT", "[24/7 ANSWERS]"],
        "body": "A friend runs a shop or a cafe? **The bot answers the usual questions and takes the order.** "
        "That is your first client.",
        "card": "prompt",
        "code": "Write a Telegram bot in Python with aiogram: menu, prices, FAQ. "
        "It takes an order and forwards it to the owner.",
    },
    {
        "label": "EVERY DAY 08:00",
        "title": ["MORNING", "[DIGEST]"],
        "body": "Calendar, email and the channels you follow — **in one message.** "
        "You know how the day starts before your coffee is done.",
        "card": "prompt",
        "code": "Write a script that collects today's events from Google Calendar and Gmail at 08:00 "
        "and sends a short summary to Telegram.",
    },
    {
        "label": "VOICE TO TEXT",
        "title": ["VOICE NOTE", "[→ IDEAS]"],
        "body": "Ideas come on the go. **Send the bot a voice note — it transcribes it "
        "and adds it to your ideas list.**",
        "card": "prompt",
        "code": "Write a Telegram bot that transcribes voice notes with Whisper, "
        "extracts the main idea and appends it to an ideas list.",
    },
    {
        "label": "WHERE THE MONEY GOES",
        "title": ["SUBSCRIPTION", "[AUDIT]"],
        "body": "Upload a bank statement — **it finds the subscriptions you pay for every month and forgot about.** "
        "Pays for itself in the first month.",
        "card": "prompt",
        "code": "Write a script that reads a bank statement (CSV), finds recurring payments "
        "and shows the monthly total.",
    },
    {
        "label": "FIRST PROJECT",
        "title": ["CURRENCY", "[RATE BOT]"],
        "body": "Exchange rates change every day — **the bot sends the rate each morning and the change since "
        "yesterday.** A free API and 50 lines of code.",
        "card": "prompt",
        "code": "Write a bot that fetches the USD rate from a free exchange-rate API every morning "
        "and sends the change since yesterday to Telegram.",
    },
    {
        "label": "FOR CREATORS",
        "title": ["INSTAGRAM", "[ANALYST]"],
        "body": "An MCP server connected to Claude: **which post worked, which did not, what went viral "
        "for competitors** — through the official API.",
        "card": "prompt",
        "code": "Set up creatorloop and ask Claude: which of my last 20 posts worked best, and why?",
    },
    {
        "label": "OPEN DATA",
        "title": ["NICHE", "[FINDER]"],
        "body": "Finds viral videos on small channels — **shows which topics are growing right now.**",
        "card": "prompt",
        "code": "Write a script that uses the YouTube Data API to find videos with few subscribers "
        "but many views and groups them by topic.",
    },
    {
        "label": "BEFORE YOU PUSH",
        "title": ["SECRETS", "[SCANNER]"],
        "body": "An API key left in the code costs money and data. **A pre-commit check "
        "takes 5 minutes to set up.**",
        "card": "prompt",
        "code": "Add a pre-commit hook to my project that blocks commits containing API keys "
        "or passwords (gitleaks).",
    },
]

FINAL = {
    "label": "TAKEAWAY",
    "title": ["PICK ONE", "[THIS WEEK]"],
    "body": "Not all of them — **one, to the end.** One small working project beats ten started ones.",
    "comment": ("COMMENT", "Which one will you build?<br>Drop the number ↓"),
    "save": ("SAVE THIS", "Keep the prompts <span class='hl'>at hand</span> for when you need them."),
    "note": "Made with creatorloop",
}

CSS = """
:root{--dark:#1b1e25;--cream:#f3eee5;--amber:#e9a43a;--amber-d:#d4902a;--ink:#16181d;--gray:#5f5f63;--card:#1e2129}
*{box-sizing:border-box;margin:0;padding:0}
body{width:1080px;height:1350px;font-family:'Inter',sans-serif;-webkit-font-smoothing:antialiased}
.slide{position:relative;width:1080px;height:1350px;padding:96px 84px 0;overflow:hidden}
.dark{background:var(--dark);color:#f2efe9}
.light{background:var(--cream);color:var(--ink)}
.label{font-weight:700;font-size:27px;letter-spacing:.16em;color:var(--amber-d);text-transform:uppercase}
.dark .label{color:var(--amber)}
.arrow{position:absolute;top:84px;right:84px;font-size:44px;color:var(--amber-d);font-weight:600}
.dark .arrow{color:var(--amber)}
h1{font-weight:900;line-height:1.02;letter-spacing:-.01em;text-transform:uppercase}
h1 .row{display:block}
h1 .hl,.hl{background:var(--amber);color:var(--ink);padding:0 .12em;box-decoration-break:clone;-webkit-box-decoration-break:clone}
.cover h1{font-size:140px;margin-top:22px}
.content h1{font-size:104px;margin-top:26px}
.sub{font-size:38px;line-height:1.4;color:#a9a7a2;margin-top:44px;font-weight:500}
.body{font-size:38px;line-height:1.45;margin-top:40px;color:#3b3b3f;font-weight:400}
.body b{color:var(--ink);font-weight:700}
.rule{width:150px;height:7px;background:var(--amber);margin-top:40px}
.sign{position:absolute;left:84px;bottom:132px;border-left:7px solid var(--amber);padding-left:26px;font-size:30px;line-height:1.45;color:#c9c6c0}
.sign b{color:#fff}
.foot{position:absolute;left:84px;right:84px;bottom:52px;display:flex;justify-content:space-between;font-size:23px;letter-spacing:.14em;font-weight:600;color:#8d8a84}
.light .foot{color:#9b968c}
.term{position:absolute;left:84px;right:84px;bottom:120px;background:var(--card);border-radius:22px;overflow:hidden;box-shadow:0 18px 40px rgba(0,0,0,.18)}
.term .bar{height:62px;background:#262a33;display:flex;align-items:center;padding:0 26px;gap:12px;font-family:'DejaVu Sans Mono',monospace;font-size:24px;color:#c9c6c0}
.term .dot{width:14px;height:14px;border-radius:50%;background:#4a4f5b}
.term .bar span.t{margin-left:14px}
.term pre{white-space:pre-wrap;font-family:'DejaVu Sans Mono',monospace;font-size:29px;line-height:1.55;color:#e8e4dc;padding:30px 34px 36px}
.term pre .p{color:var(--amber)}
.boxes{margin-top:56px;display:flex;flex-direction:column;gap:28px}
.box{border-radius:20px;padding:34px 38px}
.box.c{background:#e8dfcf}
.box.d{background:var(--dark);color:#f2efe9}
.box .k{font-size:24px;letter-spacing:.16em;font-weight:700;color:#7d756a;margin-bottom:12px}
.box.d .k{color:#a9a7a2}
.box .v{font-size:40px;line-height:1.35;font-weight:800}
.note{position:absolute;left:84px;bottom:112px;font-size:24px;color:#9b968c}
"""


def title_html(rows):
    out = []
    for r in rows:
        m = re.fullmatch(r"\[(.*)\]", r)
        out.append(f'<span class="row">{"<span class=hl>" + m.group(1) + "</span>" if m else r}</span>')
    return "".join(out)


def md_bold(text):
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def foot(n):
    return f'<div class="foot"><span>{n:02d} / {TOTAL:02d}</span><span>{HANDLE}</span></div>'


def page(inner, cls):
    return f"<!doctype html><html><head><meta charset=utf-8><style>{CSS}</style></head><body><div class='slide {cls}'>{inner}</div></body></html>"


def cover_html():
    c = COVER
    inner = f"""
<div class="arrow">→</div>
<div style="height:190px"></div>
<div class="label">{c['label']}</div>
<h1>{title_html(c['title'])}</h1>
<div class="sub">{c['sub']}</div>
<div class="sign">{"<br>".join(SIGNATURE)}</div>
{foot(1)}"""
    return page(inner, "dark cover")


def project_html(i, p):
    code = html.escape(p["code"])
    inner = f"""
<div class="arrow">→</div>
<div class="label">{i:02d} — {p['label']}</div>
<h1>{title_html(p['title'])}</h1>
<div class="body">{md_bold(p['body'])}</div>
<div class="rule"></div>
<div class="term"><div class="bar"><i class="dot"></i><i class="dot"></i><i class="dot"></i><span class="t">{p['card']}</span></div>
<pre><span class="p">›</span> {code}</pre></div>
{foot(i + 1)}"""
    return page(inner, "light content")


def final_html():
    f = FINAL
    inner = f"""
<div class="label">{f['label']}</div>
<h1>{title_html(f['title'])}</h1>
<div class="body">{md_bold(f['body'])}</div>
<div class="boxes">
  <div class="box c"><div class="k">{f['comment'][0]}</div><div class="v">{f['comment'][1]}</div></div>
  <div class="box d"><div class="k">{f['save'][0]}</div><div class="v">{f['save'][1]}</div></div>
</div>
<div class="note">{f['note']}</div>
{foot(TOTAL)}"""
    return page(inner, "light content")


async def main():
    pages = [cover_html()] + [project_html(i, p) for i, p in enumerate(PROJECTS, 1)] + [final_html()]
    assert len(pages) == TOTAL
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        pg = await browser.new_page(viewport={"width": 1080, "height": 1350})
        for n, doc in enumerate(pages, 1):
            await pg.set_content(doc)
            await pg.evaluate("document.fonts.ready")
            # shrink the headline until every row fits on one line
            await pg.evaluate(
                """() => { const h=document.querySelector('h1'); const rows=h.querySelectorAll('.row').length;
                let fs=parseFloat(getComputedStyle(h).fontSize);
                while (h.getBoundingClientRect().height > rows*fs*1.02*1.12 && fs>56) { fs-=2; h.style.fontSize=fs+'px'; } }"""
            )
            overflow = await pg.evaluate(
                """() => { const s=document.querySelector('.slide'); const t=s.querySelector('.term,.boxes,.note');
                const b=s.querySelector('.body'); const f=s.querySelector('.foot');
                const r = x => x ? x.getBoundingClientRect() : null;
                const tb=r(t), bb=r(b);
                return {body_bottom: bb && Math.round(bb.bottom), block_top: tb && Math.round(tb.top),
                        h1_w: Math.round(s.querySelector('h1').scrollWidth), foot_top: Math.round(r(f).top)}; }"""
            )
            await pg.screenshot(path=str(OUT / f"slide_{n:02d}.png"))
            print(n, overflow)
        await browser.close()


asyncio.run(main())
