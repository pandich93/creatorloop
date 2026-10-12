# Content pipeline: one topic → a carousel and a Reel

creatorloop is built around a loop: **analyse → make → publish → review**. This is the workflow the bundled
examples follow. Adapt it to your account — the numbers below are starting points, not rules.

## Carousel vs Reel

Every topic becomes two posts. They share the topic and facts, **not the form**: the carousel is a reference people
save; the Reel is a short video people rewatch and that sends them to the carousel.

| | Carousel | Reel |
|---|---|---|
| Job | get saved, come back, copy the prompt | hook in 1 s, watched to the end, profile visit |
| Volume | all points (8–10 slides) | the 3–4 strongest points |
| Text | full: prompts, commands, explanations | one thought per scene, the rest is a picture |
| Hook | the carousel cover | a DIFFERENT one: a result or a surprising fact (first-second rule) |
| Visual | your slide style | a 3D object and a metaphor per point |
| Call to action | "Save this", a question for the comments | "The full list is in the carousel" |

## Steps

1. **Brief.** Topic and one sentence "what the viewer gets". Ask Claude for data first: `get_my_content_report`,
   `get_caption_insights`, the "Data-driven content ideas" prompt.
2. **Carousel.** A `build.py` like `examples/sample-carousel/build.py` plus `caption.txt`. Review the slides.
3. **Reel storyboard — separately.** A table: time / scene / on-screen text / object (hero) / metaphor (visual) /
   sound. 25–35 s. Agree on it BEFORE rendering.
4. **Render.** A `reel.config.json` from the storyboard (keep `"carousel"` pointing at the carousel script), then
   `python tools/make_reel.py --config ... --out ... --trial SS_PERFORMANCE` in `examples/reel-template`.
   The automatic checks must pass: text on frame 0, safe zones, the final card holds, not a copy of the carousel.
5. **Captions.** The Reel gets its own caption (a different first line) that points to the carousel.
6. **Publish.** Carousel first (a queue slot), the Reel as a trial 1–2 days later. Both via `queue_post` after you
   approve the preview. The 24 h / 72 h reviews come from `post_reviews`.

## Reel rules

### The first second
- Frame 0 already shows the result or a surprising fact. It doubles as the cover.
- No greeting, "today I'll show you…", logo, empty background, intro or slow text fade-in.
- First-frame text: up to 6 words, large, readable without sound.
- Good: a result, a number ("16 out of 16"), a claim people want to argue with ("This prompt doesn't work").
- `tools/check.py` fails the render if frame 0 has no text.

### Trial Reels
- Two hooks per video: the main Reel and a trial with a different first frame.
- In `reel.json`: `"trial": "SS_PERFORMANCE"` — Instagram shows it to followers if it performs;
  `"MANUAL"` — you move it to followers yourself in the app.
- After 72 h compare watch-through and saves (`post_reviews`).

### Text and timing
- Every on-screen phrase stays at least 1.5 s. One thought per frame.
- Nothing important above 250 px from the top or below 350 px from the bottom (the Reels UI lives there).
- Font size follows the real line width: longer languages and diacritics must not be clipped.
- The final card holds 2–4 s: one action ("Save this"), your handle, your signature.

### Structure (30–40 s)
hook (0–2 s) → pain → the solution on the music drop → 3–8 points → the takeaway in one sentence → final card.

### Sound
- Original music from `music/compose.py` (you own it) or a licensed track, credited in the caption.
- −14 LUFS integrated, true peak ≤ −1 dBTP. Do not duck the music before the drop.

### Theme (`reel.config.json` → `"theme"`)
- `light` — practical topics, tools, lists.
- `dark` — technical topics, terminal, security.
- `amber` — emotional, "loud" topics; or only as `"bg": "amber"` on ONE key scene (takeaway, drop).
The background does not flash every few seconds.

### Before publishing
- [ ] Frame 0 makes sense without sound
- [ ] Every caption can be read on a phone in time
- [ ] Nothing important in the UI zones
- [ ] The cover (`cover_ms` in `reel.json`) is the hook frame
- [ ] Video: H.264, yuv420p, 30 fps, AAC 128k, moov atom first (`prepare_post` checks this)

## Remotion notes

- All motion comes from `useCurrentFrame()` + `interpolate()`; CSS transitions and animations are not rendered.
- Easing: `Easing.bezier(0.16, 1, 0.3, 1)` for a soft exit, `Easing.spring({damping: 200})` for a push without bounce.
- Timing is computed from `fps` (`useVideoConfig()`); use `premountFor={fps}` on sequences and media.
- Lottie: fetch + `delayRender` / `continueRender`, errors via `cancelRender` (see `src/components/Obj.tsx`).
- Keep all `@remotion/*` packages on the same version: `npx remotion add @remotion/<pkg>`.
- `@remotion/effects` (shine, shadows, light leaks) needs WebGL; their default strengths are too strong — tune them
  on still frames.
- Remotion's licence is free for individuals and small companies; check [remotion.dev/license](https://www.remotion.dev/license).
