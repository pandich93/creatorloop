import {staticFile} from 'remotion';

/**
 * One way to name every object of the template, whatever library it comes from:
 *   "fluent:1f4f1"  3D Fluent Emoji (Microsoft, MIT)          -> public/assets/emoji/1f4f1.webp
 *   "3d:wallet"     3dicons (Vijay Verma, CC0)                -> public/assets/3dicons/wallet.webp
 *   "noto:1f525"    animated Noto Emoji (Google, CC BY 4.0)   -> public/assets/noto/1f525.json (Lottie)
 *   "1f4f1"         no prefix = Fluent (old configs keep working)
 * Every object must have an entry in public/assets/catalog.json (source + licence); tools/check.py enforces it.
 * Find objects by word: python tools/assets.py find kofe
 */
export type Source = 'fluent' | '3d' | 'noto';

export const parseRef = (ref: string): {src: Source; id: string} => {
  const i = ref.indexOf(':');
  if (i < 0) return {src: 'fluent', id: ref};
  const src = ref.slice(0, i) as Source;
  if (src !== 'fluent' && src !== '3d' && src !== 'noto') throw new Error(`Unknown asset source in "${ref}"`);
  return {src, id: ref.slice(i + 1)};
};

const DIR: Record<Source, [string, string]> = {
  fluent: ['emoji', 'webp'],
  '3d': ['3dicons', 'webp'],
  noto: ['noto', 'json'],
};

export const asset = (ref: string) => {
  const {src, id} = parseRef(ref);
  const [dir, ext] = DIR[src];
  return staticFile(`assets/${dir}/${id}.${ext}`);
};

export const isAnimated = (ref: string) => parseRef(ref).src === 'noto';

/** Backwards compatible name: emoji('1f916') still works. */
export const emoji = asset;
