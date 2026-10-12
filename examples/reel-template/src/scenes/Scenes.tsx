// Scenes driven by reel.config.json "scenes" (written from the Reel storyboard, NOT from the carousel slides).
// Inside each scene useCurrentFrame() is LOCAL to its <Sequence>.
import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import cfg from '../reel.config.json';
import {FPB, Scene, bf, nextScene, themeOf} from '../grid';
import {CONTENT_W, FONT, MONO, PAD, Theme} from '../theme';
import {Obj} from '../components/Obj';
import {softShadow, sweep} from '../components/Fx';
import {Label, Title, clamp, rise} from '../components/Type';
import {Visual, VisualView, pop} from './Visuals';

type SceneCfg = {
  type: string;
  label?: string;
  rows?: string[];
  line?: string;
  hero?: string;
  heroes?: string[];
  kicker?: string[];
  visual?: Visual;
  cta?: string;
  sub?: string;
  signature?: string[];
};

const bob = (f: number) => Math.sin((f / FPB) * Math.PI) * 10; // one smooth bob per beat
const cfgOf = (s: Scene) => (cfg.scenes as SceneCfg[])[s.index];

/** Wraps a scene: if the next scene enters "through the camera", this one zooms out of frame in its last 6 frames. */
export const SceneView: React.FC<{scene: Scene}> = ({scene}) => {
  const f = useCurrentFrame();
  const len = bf(scene.end) - bf(scene.start);
  const zoomOut = nextScene(scene)?.enter === 'zoom';
  const e = zoomOut ? interpolate(f, [len - 6, len], [0, 1], {...clamp, easing: Easing.in(Easing.cubic)}) : 0;
  const enter = scene.enter === 'zoom' ? interpolate(f, [0, 7], [0.82, 1], {...clamp, easing: Easing.out(Easing.cubic)}) : 1;
  const c = cfgOf(scene);
  const t = themeOf(scene);
  const body =
    scene.type === 'hook' ? <Hook c={c} t={t} /> :
    scene.type === 'montage' ? <Montage c={c} t={t} /> :
    scene.type === 'point' ? <Point c={c} t={t} n={scene.point!} /> :
    scene.type === 'compare' ? <Compare c={c} t={t} /> :
    scene.type === 'outro' ? <Outro c={c} t={t} /> : <Final c={c} t={t} />;
  return (
    <AbsoluteFill style={{transform: `scale(${(1 + e * 0.35) * enter})`, opacity: (1 - e) * (scene.enter === 'zoom' ? interpolate(f, [0, 4], [0, 1], clamp) : 1)}}>
      {body}
    </AbsoluteFill>
  );
};

type P = {c: SceneCfg; t: Theme};

// ---------------------------------------------------------------- HOOK: frame 0 already states the result
const Hook: React.FC<P> = ({c, t}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const k = c.kicker ?? [];
  const heroes = c.heroes ?? [];
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', top: 520, left: PAD, width: CONTENT_W}}>
        <Label text={`${cfg.handle}${c.label ? ` · ${c.label}` : ''}`} at={-10} color={t.label} />
        <div style={{marginTop: 26}}>
          <Title rows={c.rows ?? []} max={170} at={(c.rows ?? []).map(() => -30)} color={t.fg} hlBg={t.hlBg} hlFg={t.hlFg} />
        </div>
        {k.length > 0 && (
          <div style={{marginTop: 46, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 22, fontFamily: MONO, fontWeight: 700, fontSize: 50, color: t.fg}}>
            {k.map((w, i) => {
              const p = pop(f, bf(1 + i * 0.5), fps);
              const accent = w === '→' || w === '=' || w === '✓';
              return <span key={i} style={{opacity: p, transform: `scale(${p})`, color: accent ? t.label : t.fg}}>{w}</span>;
            })}
          </div>
        )}
      </div>
      {heroes[0] && (
        <Obj id={heroes[0]} effects={[softShadow(t.tone !== 'light'), sweep(f, 8)]} style={{position: 'absolute', top: 1220, right: 120, width: 300, transform: `rotate(${-12 + 6 * Math.sin(f / 9)}deg) scale(${0.9 + 0.1 * pop(f, 0, fps)}) translateY(${bob(f)}px)`}} />
      )}
      {heroes[1] && (
        <Obj id={heroes[1]} effects={[softShadow(t.tone !== 'light')]} style={{position: 'absolute', top: 1300, left: 110, width: 220, opacity: pop(f, bf(1), fps), transform: `rotate(10deg) scale(${pop(f, bf(1), fps)}) translateY(${-bob(f)}px)`}} />
      )}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- MONTAGE: all objects pop in on 8ths, one line
const Montage: React.FC<P> = ({c, t}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const heroes = c.heroes ?? [];
  const cols = 4;
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', top: 430, left: PAD, width: CONTENT_W, display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 20}}>
        {heroes.map((h, i) => {
          const p = pop(f, Math.round(i * FPB * 0.25), fps);
          return (
            <div key={h + i} style={{aspectRatio: '1', borderRadius: 34, background: t.card, boxShadow: t.shadow, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: p, transform: `scale(${p}) rotate(${(1 - p) * (i % 2 ? 20 : -20)}deg)`}}>
              <Obj id={h} style={{width: '78%', transform: `translateY(${bob(f + i * 4) * 0.6}px)`}} />
            </div>
          );
        })}
      </div>
      <div style={{position: 'absolute', top: 1060, left: PAD, width: CONTENT_W}}>
        <Title rows={c.rows ?? []} max={130} at={[bf(1), bf(1.5), bf(2)]} color={t.fg} hlBg={t.hlBg} hlFg={t.hlFg} />
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- POINT: hero object + big outlined number + metaphor
const Point: React.FC<P & {n: number}> = ({c, t, n}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const hero = pop(f, 0, fps);
  const num = String(n).padStart(2, '0');
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', top: 360, left: PAD - 20, fontFamily: FONT, fontWeight: 900, fontSize: 470, lineHeight: 1, color: 'transparent', WebkitTextStroke: `4px ${t.outline}`, letterSpacing: '-0.04em'}}>{num}</div>
      <div style={{position: 'absolute', top: 420, right: 70, width: 400, height: 400, borderRadius: 200, background: `radial-gradient(circle, ${t.glow} 0%, transparent 70%)`}} />
      {c.hero && (
        <Obj id={c.hero} effects={[softShadow(t.tone !== 'light'), sweep(f, 10)]} style={{position: 'absolute', top: 430, right: 90, width: 380, transform: `scale(${hero}) rotate(${(1 - hero) * -30}deg) translateY(${bob(f)}px)`}} />
      )}
      <div style={{position: 'absolute', top: 830, left: PAD, width: CONTENT_W}}>
        {c.label && <Label text={c.label} at={2} color={t.label} />}
        <div style={{marginTop: 18}}>
          <Title rows={c.rows ?? []} max={112} at={[3, 7, 11]} color={t.fg} hlBg={t.hlBg} hlFg={t.hlFg} />
        </div>
        {!c.visual && c.line && (
          <div style={{marginTop: 28, opacity: rise(f, bf(1), fps), fontFamily: FONT, fontWeight: 700, fontSize: 52, lineHeight: 1.3, color: t.sub}}>{c.line}</div>
        )}
      </div>
      {c.visual && (
        <div style={{position: 'absolute', top: 1170, left: PAD, width: CONTENT_W}}>
          <VisualView v={c.visual} t={t} at={bf(1)} />
        </div>
      )}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- COMPARE: big before/after, no hero
const Compare: React.FC<P> = ({c, t}) => (
  <AbsoluteFill>
    <div style={{position: 'absolute', top: 470, left: PAD, width: CONTENT_W}}>
      {c.label && <Label text={c.label} at={2} color={t.label} />}
      <div style={{marginTop: 18}}>
        <Title rows={c.rows ?? []} max={130} at={[3, 7, 11]} color={t.fg} hlBg={t.hlBg} hlFg={t.hlFg} />
      </div>
      {c.visual && (
        <div style={{marginTop: 60}}>
          <VisualView v={c.visual} t={t} at={bf(1)} />
        </div>
      )}
    </div>
  </AbsoluteFill>
);

// ---------------------------------------------------------------- OUTRO: one-line conclusion
const Outro: React.FC<P> = ({c, t}) => (
  <AbsoluteFill>
    <div style={{position: 'absolute', top: 760, left: PAD, width: CONTENT_W}}>
      <Title rows={c.rows ?? []} max={150} at={(c.rows ?? []).map((_, i) => i * bf(0.5))} color={t.fg} hlBg={t.hlBg} hlFg={t.hlFg} slam />
    </div>
  </AbsoluteFill>
);

// ---------------------------------------------------------------- FINAL: clean frame, holds still
const Final: React.FC<P> = ({c, t}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const a = (i: number) => {
    const p = rise(f, 2 + i * 3, fps, 16);
    return {opacity: p, transform: `translateY(${(1 - p) * 40}px)`};
  };
  const sig = c.signature ?? [];
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', top: 520, left: PAD, width: CONTENT_W}}>
        <svg width="110" height="140" viewBox="0 0 110 140" style={a(0)}>
          <path d="M10 8 h90 v124 l-45 -34 l-45 34 z" fill="none" stroke={t.label} strokeWidth="12" strokeLinejoin="round" />
        </svg>
        <div style={{...a(1), marginTop: 36}}>
          <Title rows={[`[${c.cta ?? 'SAVE THIS'}]`]} max={150} at={[-30]} color={t.fg} hlBg={t.hlBg} hlFg={t.hlFg} />
        </div>
        {c.sub && <div style={{...a(2), marginTop: 30, fontFamily: FONT, fontWeight: 600, fontSize: 46, lineHeight: 1.4, color: t.sub}}>{c.sub}</div>}
        <div style={{...a(3), marginTop: 80, fontFamily: FONT, fontWeight: 900, fontSize: 88, color: t.fg, letterSpacing: '0.02em'}}>{cfg.handle}</div>
        <div style={{...a(4), marginTop: 34, borderLeft: `7px solid ${t.label}`, paddingLeft: 26, fontFamily: FONT, fontSize: 38, lineHeight: 1.45, color: t.sub}}>
          {sig.map((ln, i) => (
            <div key={i}>
              {i === 0 && ln.includes(' · ') ? (
                <>
                  <b style={{color: t.fg}}>{ln.split(' · ')[0]}</b> · {ln.split(' · ').slice(1).join(' · ')}
                </>
              ) : (
                ln
              )}
            </div>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};
