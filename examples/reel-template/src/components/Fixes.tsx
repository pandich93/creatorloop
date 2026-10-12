import React from 'react';
import {interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {C, FONT, MONO} from '../theme';
import {clamp, rise} from './Type';

type Tone = 'dark' | 'light';

/** "✗ before" card: enters at `at`, a strike line draws across at `strikeAt`. */
export const Bad: React.FC<{text: string; at: number; strikeAt: number; tone: Tone}> = ({text, at, strikeAt, tone}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = rise(frame, at, fps);
  const strike = interpolate(frame, [strikeAt, strikeAt + 7], [0, 100], clamp);
  const bg = tone === 'dark' ? C.cardBar : C.sand;
  const fg = tone === 'dark' ? C.grayL : '#5f5f63';
  return (
    <div style={{opacity: p, transform: `translateX(${(1 - p) * 120}px)`, background: bg, borderRadius: 24, padding: '30px 36px', display: 'flex', gap: 24, alignItems: 'flex-start'}}>
      <span style={{fontFamily: MONO, fontWeight: 700, fontSize: 44, color: C.gray, lineHeight: 1.3}}>✗</span>
      <span style={{position: 'relative', fontFamily: FONT, fontWeight: 600, fontSize: 44, lineHeight: 1.3, color: fg}}>
        {text}
        <span style={{position: 'absolute', left: 0, top: '50%', height: 5, width: `${strike}%`, background: C.amber, borderRadius: 3}} />
      </span>
    </div>
  );
};

export const Good: React.FC<{text: React.ReactNode; at: number; tone: Tone}> = ({text, at, tone}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = frame < at ? 0 : rise(frame, at, fps, 12);
  const bg = tone === 'dark' ? C.paper : C.ink;
  const fg = tone === 'dark' ? C.ink : '#f6f2ea';
  return (
    <div
      style={{
        opacity: Math.min(1, p * 1.5),
        transform: `scale(${interpolate(p, [0, 1], [0.85, 1])})`,
        transformOrigin: '0% 50%',
        background: bg,
        borderRadius: 24,
        padding: '32px 36px',
        display: 'flex',
        gap: 24,
        alignItems: 'flex-start',
        borderLeft: `12px solid ${C.amber}`,
        boxShadow: '0 24px 60px rgba(0,0,0,.25)',
      }}
    >
      <span style={{fontFamily: MONO, fontWeight: 700, fontSize: 48, color: C.amber, lineHeight: 1.3}}>✓</span>
      <span style={{fontFamily: FONT, fontWeight: 800, fontSize: 48, lineHeight: 1.3, color: fg}}>{text}</span>
    </div>
  );
};

/** Terminal card in the carousel style. */
export const Terminal: React.FC<{title: string; children: React.ReactNode; style?: React.CSSProperties; fontSize?: number}> = ({title, children, style, fontSize = 36}) => (
  <div style={{background: C.card, borderRadius: 26, overflow: 'hidden', boxShadow: '0 30px 70px rgba(0,0,0,.35)', ...style}}>
    <div style={{height: 70, background: C.cardBar, display: 'flex', alignItems: 'center', padding: '0 30px', gap: 14, fontFamily: MONO, fontSize: 26, color: C.grayL}}>
      {[0, 1, 2].map((i) => (
        <i key={i} style={{width: 16, height: 16, borderRadius: 8, background: '#4a4f5b'}} />
      ))}
      <span style={{marginLeft: 16}}>{title}</span>
    </div>
    <div style={{padding: '34px 38px 40px', fontFamily: MONO, fontSize, lineHeight: 1.55, color: '#e8e4dc', whiteSpace: 'pre-wrap'}}>{children}</div>
  </div>
);
