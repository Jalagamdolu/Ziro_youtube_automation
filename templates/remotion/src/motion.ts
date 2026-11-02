import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

// Fade + rise-in shared by every scene template; `delay` in seconds staggers items.
export const useEnter = (delay = 0) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = spring({ frame: frame - Math.round(delay * fps), fps, config: { damping: 200 } });
  return { opacity: t, transform: `translateY(${interpolate(t, [0, 1], [40, 0])}px)` };
};
