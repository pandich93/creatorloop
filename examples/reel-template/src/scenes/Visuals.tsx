// Metaphor library: one visual per point instead of a wall of text. All take the reel theme and start at `at`
// (local frame); their inner steps land on the following beats.
import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {FPB} from '../grid';
import {C, FONT, MONO, Theme} from '../theme';
import {Obj} from '../components/Obj';
import {StrikeThrough} from '@remotion/rough-notation';
import {Terminal} from '../components/Fixes';
import {clamp, rise} from '../components/Type';

export type Visual =
  | {kind: 'chat'; ask: string; answer: string; bot?: string}
  | {kind: 'notify'; title: string; rows: string[]; icon?: string}
  | {kind: 'receipt'; rows: [string, string][]; totalLabel: string; total: string; strike?: boolean}
  | {kind: 'terminal'; cmd: string; out: string[]}
  | {kind: 'counter'; from: number; to: number; prefix?: string; suffix?: string; caption: string}
  | {kind: 'beforeafter'; bad: string; good: string}
  | {kind: 'checklist'; items: string[]}
  | {kind: 'chart'; bars: {label: string; value: number}[]; caption: string};

export const pop = (f: number, at: number, fps: number) => spring({frame: f - at, fps, config: {damping: 9, stiffness: 160, mass: 0.6}});
const B = FPB;

const Chat: React.FC<{v: Extract<Visual, {kind: 'chat'}>; t: Theme; at: number}> = ({v, t, at}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const q = pop(f, at, fps);
  const typing = f >= at + B - 6 && f < at + B + 6;
  const ans = pop(f, at + B + 6, fps);
  const bubble: React.CSSProperties = {fontFamily: FONT, fontWeight: 600, fontSize: 44, lineHeight: 1.3, padding: '24px 32px', borderRadius: 36, maxWidth: 780, boxShadow: t.shadow};
  return (
    <div style={{display: 'flex', flexDirection: 'column', gap: 24}}>
      <div style={{...bubble, alignSelf: 'flex-end', background: C.amber, color: C.ink, borderBottomRightRadius: 8, opacity: q, transform: `translateY(${(1 - q) * 30}px) scale(${0.9 + 0.1 * q})`}}>{v.ask}</div>
      <div style={{display: 'flex', alignItems: 'flex-end', gap: 16}}>
        <Obj id={v.bot ?? '1f916'} style={{width: 88, opacity: typing ? 1 : ans}} />
        {typing ? (
          <div style={{...bubble, background: t.card, color: t.cardSub, letterSpacing: 6}}>• • •</div>
        ) : (
          <div style={{...bubble, background: t.card, color: t.cardFg, borderBottomLeftRadius: 8, opacity: ans, transform: `translateY(${(1 - ans) * 30}px) scale(${0.9 + 0.1 * ans})`}}>{v.answer}</div>
        )}
      </div>
    </div>
  );
};

const Notify: React.FC<{v: Extract<Visual, {kind: 'notify'}>; t: Theme; at: number}> = ({v, t, at}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = pop(f, at, fps);
  return (
    <div style={{background: t.card, borderRadius: 36, padding: '30px 36px', opacity: p, transform: `translateY(${(1 - p) * -60}px)`, boxShadow: t.shadow}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 18, fontFamily: FONT, fontWeight: 800, fontSize: 40, color: t.cardFg}}>
        <Obj id={v.icon ?? '23f0'} style={{width: 66}} />
        {v.title}
      </div>
      <div style={{marginTop: 18, display: 'flex', flexDirection: 'column', gap: 10}}>
        {v.rows.map((r, i) => {
          const q = rise(f, at + B + i * 6, fps);
          return <div key={r} style={{fontFamily: FONT, fontWeight: 600, fontSize: 42, color: t.cardSub, opacity: q, transform: `translateX(${(1 - q) * 40}px)`}}>{r}</div>;
        })}
      </div>
    </div>
  );
};

const Receipt: React.FC<{v: Extract<Visual, {kind: 'receipt'}>; t: Theme; at: number}> = ({v, t, at}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = pop(f, at, fps);
  const tot = pop(f, at + 2 * B, fps);
  return (
    <div style={{background: C.paper, color: C.ink, borderRadius: 18, padding: '30px 38px 26px', opacity: p, transform: `rotate(-2deg) translateY(${(1 - p) * 80}px)`, boxShadow: t.shadow, border: '2px solid #e6dccb', fontFamily: MONO}}>
      {v.rows.map(([name, sum], i) => {
        // strike (default): rows get crossed out = money saved. strike: false: rows simply print one by one = a bill.
        const s = interpolate(f, [at + B + i * 5, at + B + i * 5 + 6], [0, 100], clamp);
        const shown = v.strike === false ? interpolate(f, [at + 4 + i * 5, at + 10 + i * 5], [0, 1], clamp) : 1;
        return (
          <div key={name} style={{position: 'relative', display: 'flex', justifyContent: 'space-between', fontSize: 40, lineHeight: 1.7, opacity: shown, translate: `${(1 - shown) * 30}px 0px`}}>
            <span>{name}</span>
            <span>{sum}</span>
            {v.strike !== false && <span style={{position: 'absolute', left: -6, top: '52%', height: 6, width: `${s}%`, background: C.amber}} />}
          </div>
        );
      })}
      <div style={{borderTop: '3px dashed #c9bfae', marginTop: 14, paddingTop: 14, display: 'flex', justifyContent: 'space-between', fontFamily: FONT, fontWeight: 900, fontSize: 46, opacity: tot, transform: `scale(${0.8 + 0.2 * tot})`, transformOrigin: '0% 50%'}}>
        <span>{v.totalLabel}</span>
        <span style={{background: C.amber, padding: '0 10px'}}>{v.total}</span>
      </div>
    </div>
  );
};

const Term: React.FC<{v: Extract<Visual, {kind: 'terminal'}>; t: Theme; at: number}> = ({v, at}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = pop(f, at, fps);
  const shown = Math.round(interpolate(f, [at + 2, at + B], [0, v.cmd.length], clamp));
  return (
    <div style={{opacity: p, transform: `translateY(${(1 - p) * 60}px)`}}>
      <Terminal title="terminal" fontSize={36}>
        <div>
          <span style={{color: C.amber}}>$ </span>
          {v.cmd.slice(0, shown)}
          <span style={{color: 'transparent'}}>{v.cmd.slice(shown)}</span>
        </div>
        {v.out.map((ln, i) => {
          const q = f >= at + B + 4 + i * 6;
          const warn = ln.startsWith('⚠') || ln.startsWith('✗');
          return <div key={i} style={{opacity: q ? 1 : 0, color: warn ? C.amber : ln.startsWith('✓') ? '#9ad17b' : '#e8e4dc', fontWeight: warn ? 700 : 400}}>{ln}</div>;
        })}
      </Terminal>
    </div>
  );
};

const Counter: React.FC<{v: Extract<Visual, {kind: 'counter'}>; t: Theme; at: number}> = ({v, t, at}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = pop(f, at, fps);
  const n = Math.round(interpolate(f, [at, at + 2 * B], [v.from, v.to], {...clamp, easing: (x) => 1 - (1 - x) ** 3}));
  return (
    <div style={{opacity: p}}>
      <div style={{fontFamily: FONT, fontWeight: 900, fontSize: 210, lineHeight: 1, color: t.fg, letterSpacing: '-0.03em'}}>
        {v.prefix}
        <span style={{background: t.hlBg, color: t.hlFg, padding: '0 0.08em'}}>{n.toLocaleString('ru-RU')}</span>
        {v.suffix}
      </div>
      <div style={{marginTop: 18, fontFamily: FONT, fontWeight: 700, fontSize: 46, color: t.sub, opacity: rise(f, at + B, fps)}}>{v.caption}</div>
    </div>
  );
};

const BeforeAfter: React.FC<{v: Extract<Visual, {kind: 'beforeafter'}>; t: Theme; at: number}> = ({v, t, at}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const a = pop(f, at, fps);
  const strike = interpolate(f, [at + B, at + B + 7], [0, 100], clamp);
  const b = pop(f, at + 2 * B, fps);
  const row: React.CSSProperties = {borderRadius: 26, padding: '26px 32px', fontFamily: FONT, fontWeight: 700, fontSize: 44, lineHeight: 1.3, display: 'flex', gap: 20};
  return (
    <div style={{display: 'flex', flexDirection: 'column', gap: 22}}>
      <div style={{...row, background: t.tone === 'light' ? '#e8dfcf' : '#2a2f3a', color: t.cardSub, opacity: a, transform: `translateX(${(1 - a) * 120}px)`}}>
        <span>✗</span>
        <StrikeThrough color={C.amber} strokeWidth={6} iterations={2} seed={3} progress={strike / 100}>
          {v.bad}
        </StrikeThrough>
      </div>
      <div style={{...row, background: t.card, color: t.cardFg, borderLeft: `12px solid ${C.amber}`, boxShadow: t.shadow, opacity: b, transform: `scale(${0.85 + 0.15 * b})`, transformOrigin: '0% 50%'}}>
        <span style={{color: C.amber}}>✓</span>
        <span>{v.good}</span>
      </div>
    </div>
  );
};

const Checklist: React.FC<{v: Extract<Visual, {kind: 'checklist'}>; t: Theme; at: number}> = ({v, t, at}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  return (
    <div style={{display: 'flex', flexDirection: 'column', gap: 18}}>
      {v.items.map((it, i) => {
        const s = at + i * Math.round(B / 2);
        const p = pop(f, s, fps);
        const tick = pop(f, s + 6, fps);
        return (
          <div key={it} style={{display: 'flex', alignItems: 'center', gap: 22, opacity: p, transform: `translateX(${(1 - p) * -60}px)`}}>
            <span style={{width: 62, height: 62, borderRadius: 16, background: C.amber, color: C.ink, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: FONT, fontWeight: 900, fontSize: 42, transform: `scale(${tick})`}}>✓</span>
            <span style={{fontFamily: FONT, fontWeight: 700, fontSize: 46, color: t.fg}}>{it}</span>
          </div>
        );
      })}
    </div>
  );
};

const Chart: React.FC<{v: Extract<Visual, {kind: 'chart'}>; t: Theme; at: number}> = ({v, t, at}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const max = Math.max(...v.bars.map((b) => b.value));
  return (
    <div style={{background: t.card, borderRadius: 32, padding: '30px 36px', boxShadow: t.shadow, opacity: pop(f, at, fps)}}>
      <div style={{display: 'flex', alignItems: 'flex-end', gap: 22, height: 200}}>
        {v.bars.map((b, i) => {
          const g = rise(f, at + 4 + i * 4, fps);
          const last = i === v.bars.length - 1;
          return (
            <div key={b.label} style={{flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10}}>
              <div style={{width: '100%', height: (b.value / max) * 160 * g, borderRadius: 12, background: last ? C.amber : t.tone === 'light' ? '#e8dfcf' : '#3a3f4b'}} />
              <span style={{fontFamily: MONO, fontSize: 28, color: t.cardSub}}>{b.label}</span>
            </div>
          );
        })}
      </div>
      <div style={{marginTop: 16, fontFamily: FONT, fontWeight: 700, fontSize: 40, color: t.cardFg, opacity: rise(f, at + 2 * B, fps)}}>{v.caption}</div>
    </div>
  );
};

export const VisualView: React.FC<{v: Visual; t: Theme; at: number}> = ({v, t, at}) => {
  switch (v.kind) {
    case 'chat': return <Chat v={v} t={t} at={at} />;
    case 'notify': return <Notify v={v} t={t} at={at} />;
    case 'receipt': return <Receipt v={v} t={t} at={at} />;
    case 'terminal': return <Term v={v} t={t} at={at} />;
    case 'counter': return <Counter v={v} t={t} at={at} />;
    case 'beforeafter': return <BeforeAfter v={v} t={t} at={at} />;
    case 'checklist': return <Checklist v={v} t={t} at={at} />;
    case 'chart': return <Chart v={v} t={t} at={at} />;
  }
};
