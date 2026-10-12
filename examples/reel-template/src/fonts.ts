import {staticFile} from 'remotion';
import {FONT, MONO} from './theme';

const FACES: [string, string, string][] = [
  [FONT, 'fonts/Inter-Regular.otf', '400'],
  [FONT, 'fonts/Inter-Medium.otf', '500'],
  [FONT, 'fonts/Inter-SemiBold.otf', '600'],
  [FONT, 'fonts/Inter-Bold.otf', '700'],
  [FONT, 'fonts/Inter-ExtraBold.otf', '800'],
  [FONT, 'fonts/Inter-Black.otf', '900'],
  [MONO, 'fonts/DejaVuSansMono.ttf', '400'],
  [MONO, 'fonts/DejaVuSansMono-Bold.ttf', '700'],
];

let loading: Promise<void> | null = null;

/** Loads every face once. Text is measured (fitText) only after this resolves. */
export const loadFonts = () => {
  loading ??= Promise.all(
    FACES.map(async ([family, file, weight]) => {
      const face = new FontFace(family, `url(${staticFile(file)})`, {weight});
      document.fonts.add(await face.load());
    }),
  ).then(() => undefined);
  return loading;
};
