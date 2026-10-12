import React from 'react';
import {Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {fitText} from '@remotion/layout-utils';
import {Highlight} from '@remotion/rough-notation';
import cfg from '../reel.config.json';
import {C, CONTENT_W, FONT} from '../theme';

const strip = (r: string) => r.replace(/[[\]]/g, '');

/** "highlight": "marker" (default, hand-drawn marker drawn on the beat) or "bar" (v2 flat sweep) in reel.config.json. */
const MARKER = (cfg as {highlight?: string}).highlight !== 'bar';

/** Font size so that every row fits the real line width in this font (Uzbek runs long). */
export const fitRows = (rows: string[], max: number, width = CONTENT_W, weight = '900') => {
  const sizes = rows.map(
    (r) => fitText({text: strip(r), withinWidth: width * 0.9, fontFamily: FONT, fontWeight: weight}).fontSize,
  );
  return Math.floor(Math.min(max, ...sizes));
};

export const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export const rise = (frame: number, start: number, fps: number, damping = 14) =>
  spring({frame: frame - start, fps, config: {damping, stiffness: 170, mass: 0.7}});

type TitleProps = {
  rows: string[]; // "[...]" marks the highlighted row
  max: number;
  at: number[]; // local frame each row enters
  color?: string;
  hlBg?: string;
  hlFg?: string;
  align?: 'left' | 'center';
  slam?: boolean; // scale-in instead of slide-up
};

/** Kinetic headline: rows enter on beats, the highlight bar sweeps in after its row lands. */
export const Title: React.FC<TitleProps> = ({rows, max, at, color = '#f2efe9', hlBg = C.amber, hlFg = C.ink, align = 'left', slam}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const size = fitRows(rows, max);
  return (
    <div style={{fontFamily: FONT, fontWeight: 900, fontSize: size, lineHeight: 1.04, color, textAlign: align, letterSpacing: '-0.01em'}}>
      {rows.map((r, i) => {
        const p = rise(frame, at[i] ?? at[at.length - 1], fps);
        const hl = /^\[.*\]$/.test(r);
        const sweep = interpolate(frame, [(at[i] ?? 0) + 3, (at[i] ?? 0) + 11], [0, 100], {...clamp, easing: Easing.out(Easing.cubic)});
        const motion: React.CSSProperties = slam
          ? {scale: String(interpolate(p, [0, 1], [1.6, 1], {output: 'perceptual-scale'}))}
          : {translate: `0px ${interpolate(p, [0, 1], [70, 0])}px`};
        return (
          <div key={i} style={{opacity: Math.min(1, p * 1.6), ...motion, transformOrigin: align === 'center' ? '50% 50%' : '0% 50%'}}>
            {hl && MARKER ? (
              <Highlight
                color={hlBg}
                progress={sweep / 100}
                iterations={2}
                padding={{left: 14, right: 14, top: 4, bottom: 4}}
                seed={7 + i}
                style={{marginLeft: align === 'left' ? -14 : 0}}
              >
                <span style={{color: sweep > 45 ? hlFg : color}}>{strip(r)}</span>
              </Highlight>
            ) : hl ? (
              <span
                style={{
                  color: sweep > 50 ? hlFg : color,
                  backgroundImage: `linear-gradient(${hlBg}, ${hlBg})`,
                  backgroundRepeat: 'no-repeat',
                  backgroundSize: `${sweep}% 100%`,
                  padding: '0 0.12em',
                  marginLeft: align === 'left' ? '-0.12em' : 0,
                }}
              >
                {strip(r)}
              </span>
            ) : (
              r
            )}
          </div>
        );
      })}
    </div>
  );
};

export const Label: React.FC<{text: string; at: number; color?: string}> = ({text, at, color = C.amber}) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame, [at, at + 6], [0, 1], clamp);
  return (
    <div style={{fontFamily: FONT, fontWeight: 700, fontSize: 30, letterSpacing: '0.16em', color, opacity: o, transform: `translateX(${(1 - o) * -30}px)`}}>
      {text}
    </div>
  );
};

/** Characters of `text` revealed between local frames a..b. */
export const typed = (text: string, frame: number, a: number, b: number) =>
  text.slice(0, Math.round(interpolate(frame, [a, b], [0, text.length], clamp)));
