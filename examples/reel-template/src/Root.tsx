import React from 'react';
import {Composition} from 'remotion';
import {FPS, TOTAL} from './grid';
import {H, W} from './theme';
import {Reel} from './Reel';

export const Root: React.FC = () => (
  <Composition id="Reel" component={Reel} durationInFrames={TOTAL} fps={FPS} width={W} height={H} defaultProps={{withAudio: true}} />
);
