// Render stop-frames (+ a contact sheet) without audio: node scripts/stills.mjs [frames...]
import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';
import path from 'node:path';
import fs from 'node:fs';

const root = path.resolve(import.meta.dirname, '..');
const out = path.join(root, 'out', 'stills');
fs.mkdirSync(out, {recursive: true});
const browserExecutable = process.env.REMOTION_BROWSER || undefined;
const serveUrl = await bundle({entryPoint: path.join(root, 'src/index.ts')});
const inputProps = {withAudio: false};
const chromiumOptions = {gl: process.env.REMOTION_GL || (process.platform === 'linux' ? 'swangle' : 'angle')};
const composition = await selectComposition({serveUrl, id: process.env.COMP || 'Reel', inputProps, browserExecutable, chromiumOptions});
const frames = process.argv.slice(2).length
  ? process.argv.slice(2).map(Number)
  : Array.from({length: Math.ceil(composition.durationInFrames / 45)}, (_, i) => i * 45);
for (const frame of frames) {
  const output = path.join(out, `f${String(frame).padStart(4, '0')}.png`);
  await renderStill({serveUrl, composition, frame, output, inputProps, browserExecutable, chromiumOptions, scale: 1});
  console.log('still', frame);
}
