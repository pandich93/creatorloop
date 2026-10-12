// Shared @remotion/effects presets (WebGL: renders use gl "angle" on Windows/macOS, "swangle" in the cloud; see remotion.config.ts).
import {interpolate} from 'remotion';
import {dropShadow} from '@remotion/effects/drop-shadow';
import {shine} from '@remotion/effects/shine';
import cfg from '../reel.config.json';
import {clamp} from './Type';

/** "effects": false in reel.config.json switches every effect off (fallback if a machine has no WebGL). */
export const FX_ON = (cfg as {effects?: boolean}).effects !== false;

/** Soft contact shadow under a 3D object: lifts it off the background without a CSS box. */
export const softShadow = (dark: boolean) =>
  dropShadow({radius: 22, offsetX: 0, offsetY: 18, opacity: dark ? 0.45 : 0.22, disabled: !FX_ON});

/** One light sweep across the object, starting at local frame `at` and lasting `len` frames. */
export const sweep = (frame: number, at: number, len = 18) =>
  shine({
    progress: interpolate(frame, [at, at + len], [0, 1], clamp),
    angle: 25,
    coreSigma: 40,
    haloSigma: 120,
    coreIntensity: 0.35,
    haloIntensity: 0.15,
    disabled: !FX_ON || frame < at || frame > at + len,
  });
