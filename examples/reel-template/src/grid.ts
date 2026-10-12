// Beat grid: the ONLY place that converts beats to frames. Everything else talks in beats.
import tl from './timeline.json';
import {THEMES, ThemeName} from './theme';

export type SceneType = 'hook' | 'montage' | 'point' | 'compare' | 'outro' | 'final';
export type Scene = {
  id: string; type: SceneType; start: number; end: number; index: number; // index into reel.config.json scenes
  theme: ThemeName; enter: 'cut' | 'wipe' | 'zoom'; wipe: string | null; point?: number;
};

export const FPS: number = tl.fps;
export const BPM: number = tl.bpm;
export const FPB = (FPS * 60) / BPM; // frames per beat (15 at 120 BPM / 30 fps)

/** Global frame of beat n (n may be fractional). "Кадр n-го удара". */
export const bf = (beat: number) => Math.round(beat * FPB);

export const TOTAL = bf(tl.totalBeats);
export const DROP_BEAT: number = tl.dropBeat;
export const OUTRO_BEAT: number = tl.outroBeat;
export const FINAL_BEAT: number = tl.finalBeat;
export const DROP = bf(DROP_BEAT);
export const SCENES = tl.scenes as Scene[];
export const POINTS = SCENES.filter((s) => s.type === 'point');
export const BREAK: number[] = (tl.breakBeats as number[]).length ? (tl.breakBeats as number[]) : [0, 0];

export const sfxBeats = (type: string): number[] => tl.sfx.filter((s) => s.type === type).flatMap((s) => s.beats);
export const sceneAt = (beat: number): Scene => SCENES.filter((s) => s.start <= beat).pop() ?? SCENES[0];
export const nextScene = (s: Scene): Scene | undefined => SCENES[SCENES.indexOf(s) + 1];
export const themeOf = (s: Scene) => THEMES[s.theme];
