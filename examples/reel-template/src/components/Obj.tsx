// Renders any template object (see assets.ts): a still 3D image or a frame-accurate Lottie animation.
import React, {useEffect, useState} from 'react';
import {Img, cancelRender, continueRender, delayRender, type EffectsProp} from 'remotion';
import {Lottie, LottieAnimationData} from '@remotion/lottie';
import {asset, isAnimated} from './assets';

const cache = new Map<string, LottieAnimationData>();

const AnimatedObj: React.FC<{src: string; style?: React.CSSProperties}> = ({src, style}) => {
  const [data, setData] = useState<LottieAnimationData | null>(cache.get(src) ?? null);
  const [handle] = useState(() => (cache.has(src) ? null : delayRender(`Lottie ${src}`)));
  useEffect(() => {
    if (data) return;
    fetch(src)
      .then((r) => r.json())
      .then((json) => {
        cache.set(src, json);
        setData(json);
        if (handle !== null) continueRender(handle);
      })
      .catch((e) => cancelRender(new Error(`Cannot load ${src}: ${e}`)));
  }, [src, data, handle]);
  if (!data) return null;
  // A Lottie fills its box: give it a square box with the requested width.
  const w = style?.width ?? 200;
  return (
    <div style={{...style, width: w, height: w}}>
      <Lottie animationData={data} loop style={{width: '100%', height: '100%'}} />
    </div>
  );
};

/**
 * <Obj id="fluent:2615" style={{width: 300}} />  ·  id may also be "3d:wallet", "noto:1f525" or a bare Fluent code.
 * `effects` (shine, dropShadow ... from @remotion/effects) apply to still objects; Lottie ignores them.
 */
export const Obj: React.FC<{id: string; style?: React.CSSProperties; effects?: EffectsProp}> = ({id, style, effects}) =>
  isAnimated(id) ? <AnimatedObj src={asset(id)} style={style} /> : <Img src={asset(id)} style={style} effects={effects} />;
