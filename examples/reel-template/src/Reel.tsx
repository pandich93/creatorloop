import React, {useEffect, useState} from 'react';
import {AbsoluteFill, Audio, Sequence, continueRender, delayRender, staticFile} from 'remotion';
import {SCENES, bf} from './grid';
import {loadFonts} from './fonts';
import {Background, Camera, DropBurst, DropLeak, StepsHud, Wipes} from './components/Global';
import {SceneView} from './scenes/Scenes';

export const Reel: React.FC<{withAudio?: boolean}> = ({withAudio = true}) => {
  const [handle] = useState(() => delayRender('fonts'));
  const [ready, setReady] = useState(false);
  useEffect(() => {
    loadFonts().then(() => {
      setReady(true);
      continueRender(handle);
    });
  }, [handle]);
  return (
    <AbsoluteFill>
      <Background />
      {ready && (
        <Camera>
          {SCENES.map((s) => (
            <Sequence key={s.id} from={bf(s.start)} durationInFrames={bf(s.end) - bf(s.start)} layout="none">
              <SceneView scene={s} />
            </Sequence>
          ))}
        </Camera>
      )}
      <Wipes />
      <DropLeak />
      {ready && <DropBurst />}
      {ready && <StepsHud />}
      {withAudio && <Audio src={staticFile('track.wav')} />}
    </AbsoluteFill>
  );
};
