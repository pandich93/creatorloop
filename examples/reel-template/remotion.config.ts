// @remotion/effects need WebGL. Windows/macOS: "angle" (GPU). Linux/cloud without GPU: "swangle" (software).
// Override with REMOTION_GL=angle|swangle|swiftshader|egl.
import {Config} from '@remotion/cli/config';

type GL = 'angle' | 'swangle' | 'swiftshader' | 'egl' | 'vulkan' | 'angle-egl';
Config.setChromiumOpenGlRenderer((process.env.REMOTION_GL as GL) || (process.platform === 'linux' ? 'swangle' : 'angle'));
