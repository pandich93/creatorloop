// Layers on the GLOBAL timeline (never inside a <Sequence>): background, camera, wipes, warm flash, hero burst, HUD.
import React from 'react';
import {AbsoluteFill, Easing, Solid, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {lightLeak} from '@remotion/effects/light-leak';
import {FX_ON} from './Fx';
import cfg from '../reel.config.json';
import {BREAK, DROP, DROP_BEAT, FINAL_BEAT, FPB, OUTRO_BEAT, POINTS, SCENES, bf, sceneAt, themeOf} from '../grid';
import {C, FONT, MONO, NAMED, PAD, W} from '../theme';
import {Obj} from './Obj';
import {clamp} from './Type';

export const Background: React.FC = () => {
  const s = sceneAt(useCurrentFrame() / FPB);
  return <AbsoluteFill style={{background: themeOf(s).bg}} />;
};

/** Smooth camera: slow drift per scene (none on the final card), decaying punch on the drop and the outro,
 *  tiny pulse on every kick. */
export const Camera: React.FC<{children: React.ReactNode}> = ({children}) => {
  const f = useCurrentFrame();
  const beat = f / FPB;
  const sc = sceneAt(beat);
  let scale = sc.type === 'final' ? 1 : 1 + 0.025 * ((beat - sc.start) / (sc.end - sc.start));
  let x = 0;
  let y = 0;
  let rot = 0;
  for (const [b, amp] of [[DROP_BEAT, 1], [OUTRO_BEAT, 0.45]] as const) {
    const d = f - bf(b);
    if (d < 0) continue;
    scale *= 1 + 0.07 * amp * Math.exp(-d / 6);
    const sh = amp * Math.exp(-d / 9); // shake fades out — never a hard jitter
    x += sh * 12 * Math.sin(d * 0.85);
    y += sh * 9 * Math.sin(d * 1.25 + 1);
    rot += sh * 0.35 * Math.sin(d * 0.6 + 2);
  }
  if (f >= DROP && beat < FINAL_BEAT && !(beat >= BREAK[0] && beat < BREAK[1])) {
    scale *= 1 + 0.005 * Math.exp(-(f % FPB) / 3);
  }
  return <AbsoluteFill style={{transform: `translate(${x}px, ${y}px) scale(${scale}) rotate(${rot}deg)`}}>{children}</AbsoluteFill>;
};

/** Skewed panel that hides a cut exactly on the beat (only for scenes entered with a wipe). */
export const Wipes: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <>
      {SCENES.filter((s) => s.enter === 'wipe' && s.wipe).map((s) => {
        const B = bf(s.start);
        if (f < B - 7 || f > B + 7) return null;
        const cx = interpolate(f, [B - 7, B + 7], [-1150, W + 1150], {easing: Easing.inOut(Easing.cubic)});
        const color = NAMED[s.wipe!];
        return (
          <div key={s.id} style={{position: 'absolute', top: -200, bottom: -200, left: cx - 800, width: 1600, background: color, transform: 'skewX(-12deg)'}}>
            <div style={{position: 'absolute', top: 0, bottom: 0, left: 60, width: 26, background: s.wipe === 'amber' ? C.ink : C.amber, opacity: 0.9}} />
          </div>
        );
      })}
    </>
  );
};

/** Warm flash on the drop: a white flash on a dark frame reads as a grey wash. */
export const Flash: React.FC = () => {
  const f = useCurrentFrame();
  const o = interpolate(f, [DROP - 1, DROP, DROP + 5], [0, 0.35, 0], clamp);
  return o > 0 ? <AbsoluteFill style={{background: C.amber, opacity: o}} /> : null;
};

type SceneCfg = {hero?: string; heroes?: string[]};
const BURST: string[] = (() => {
  const all = (cfg.scenes as SceneCfg[]).flatMap((s) => [s.hero, ...(s.heroes ?? [])]).filter(Boolean) as string[];
  return [...new Set(all)].slice(0, 10);
})();

/** On the drop every hero of the reel explodes out of the centre: the payoff in one frame. */
export const DropBurst: React.FC = () => {
  const f = useCurrentFrame();
  const d = f - DROP;
  if (d < -2 || d > 16 || !BURST.length) return null;
  const t = interpolate(d, [-2, 16], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  return (
    <AbsoluteFill>
      {BURST.map((code, k) => {
        const ang = (k / BURST.length) * Math.PI * 2 - Math.PI / 2;
        const r = 120 + t * 900;
        return (
          <Obj
            key={code}
            id={code}
            style={{position: 'absolute', left: 430 + Math.cos(ang) * r, top: 850 + Math.sin(ang) * r, width: 220, opacity: 1 - t * 0.9, transform: `rotate(${t * 90 * (k % 2 ? 1 : -1)}deg) scale(${1.2 - t * 0.4})`}}
          />
        );
      })}
    </AbsoluteFill>
  );
};

/** "2 / 4" counter + segmented progress over the point scenes: the viewer knows how much is left. */
export const StepsHud: React.FC = () => {
  const f = useCurrentFrame();
  const beat = f / FPB;
  if (!POINTS.length) return null;
  const first = POINTS[0].start;
  const last = POINTS[POINTS.length - 1].end;
  const show = interpolate(beat, [first - 0.4, first, last - 0.3, last], [0, 1, 1, 0], clamp);
  if (show <= 0) return null;
  const cur = POINTS.findIndex((s) => beat >= s.start && beat < s.end);
  const before = beat < first;
  const idx = cur >= 0 ? cur : before ? 0 : POINTS.length - 1;
  const within = cur >= 0 ? (beat - POINTS[idx].start) / (POINTS[idx].end - POINTS[idx].start) : before ? 0 : 1;
  const pop = interpolate(beat - POINTS[idx].start, [0, 0.25, 0.6], [1.25, 1.25, 1], clamp);
  return (
    <div style={{position: 'absolute', top: 270, left: PAD, right: PAD, height: 92, borderRadius: 46, background: C.ink, border: `2px solid ${C.amber}88`, display: 'flex', alignItems: 'center', padding: '0 30px', gap: 22, opacity: show, transform: `translateY(${(1 - show) * -40}px)`, boxShadow: '0 16px 40px rgba(0,0,0,.25)'}}>
      <span style={{fontFamily: FONT, fontWeight: 900, fontSize: 46, color: C.amber, width: 74, transform: `scale(${pop})`, transformOrigin: '0% 50%'}}>{String(idx + 1).padStart(2, '0')}</span>
      <span style={{fontFamily: MONO, fontWeight: 700, fontSize: 24, color: C.gray}}>/ {String(POINTS.length).padStart(2, '0')}</span>
      <div style={{flex: 1, display: 'flex', gap: 8}}>
        {POINTS.map((_, i) => (
          <div key={i} style={{flex: 1, height: 14, borderRadius: 7, background: '#2c303a', overflow: 'hidden'}}>
            <div style={{width: `${i < idx ? 100 : i === idx ? within * 100 : 0}%`, height: '100%', background: C.amber}} />
          </div>
        ))}
      </div>
      <span style={{fontFamily: MONO, fontWeight: 700, fontSize: 24, color: '#f2efe9', letterSpacing: '0.06em'}}>{cfg.handle}</span>
    </div>
  );
};

/** Warm light leak over the drop (replaces the flat Flash when effects are on). */
export const DropLeak: React.FC = () => {
  const f = useCurrentFrame();
  const {width, height} = useVideoConfig();
  if (!FX_ON) return <Flash />;
  if (f < DROP - 3 || f > DROP + 22) return null;
  // On a dark frame "screen" is strong: keep it a glint, not an orange wash. On light frames it only warms the page.
  const dark = themeOf(sceneAt(DROP_BEAT)).tone !== 'light';
  const fade = interpolate(f, [DROP - 3, DROP + 2, DROP + 22], [0, 1, 0], clamp);
  return (
    <AbsoluteFill style={{mixBlendMode: 'screen', opacity: (dark ? 0.4 : 0.85) * fade, pointerEvents: 'none'}}>
      <Solid
        width={width}
        height={height}
        color="#000000"
        effects={[lightLeak({seed: 4, hueShift: 0, progress: interpolate(f, [DROP - 3, DROP + 22], [0, 1], clamp)})]}
      />
    </AbsoluteFill>
  );
};
