export const C = {
  dark: '#1b1e25',
  deep: '#111318',
  cream: '#f3eee5',
  paper: '#fbf7f0',
  amber: '#e9a43a',
  amberD: '#d4902a',
  ink: '#16181d',
  gray: '#8d8a84',
  grayL: '#c9c6c0',
  card: '#1e2129',
  cardBar: '#262a33',
  sand: '#e8dfcf',
};

export const FONT = 'InterReel';
export const MONO = 'MonoReel';

export const W = 1080;
export const H = 1920;
export const PAD = 80;
export const SAFE_TOP = 250; // Reels UI covers the top 250 px…
export const SAFE_BOTTOM = H - 350; // …and the bottom 350 px
export const CONTENT_W = W - PAD * 2;

/** Colour names used in timeline.json (wipe colours). */
export const NAMED: Record<string, string> = {dark: C.dark, deep: C.deep, cream: C.cream, light: C.cream, amber: C.amber, ink: C.ink};

export type ThemeName = 'dark' | 'light' | 'amber';
export type Theme = {
  bg: string; fg: string; sub: string; label: string; hlBg: string; hlFg: string;
  card: string; cardFg: string; cardSub: string; outline: string; glow: string; shadow: string; tone: 'dark' | 'light';
};

/** One palette per reel (picked from the topic). Every component reads its colours from here. */
export const THEMES: Record<ThemeName, Theme> = {
  dark: {bg: C.dark, fg: '#f2efe9', sub: '#d8d4cc', label: C.amber, hlBg: C.amber, hlFg: C.ink, card: '#262a33', cardFg: '#f2efe9',
    cardSub: C.grayL, outline: `${C.amber}55`, glow: `${C.amber}40`, shadow: '0 30px 70px rgba(0,0,0,.4)', tone: 'dark'},
  light: {bg: C.cream, fg: C.ink, sub: '#3b3b3f', label: C.amberD, hlBg: C.amber, hlFg: C.ink, card: '#ffffff', cardFg: C.ink,
    cardSub: '#5f5f63', outline: '#16181d1f', glow: `${C.amber}66`, shadow: '0 24px 60px rgba(70,50,20,.16)', tone: 'light'},
  amber: {bg: C.amber, fg: C.ink, sub: '#2a2418', label: C.ink, hlBg: C.ink, hlFg: C.amber, card: C.ink, cardFg: '#f2efe9',
    cardSub: C.grayL, outline: '#16181d33', glow: '#ffffff66', shadow: '0 30px 70px rgba(0,0,0,.25)', tone: 'dark'},
};
