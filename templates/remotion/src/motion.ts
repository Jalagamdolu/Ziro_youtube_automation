import { createContext, useContext } from "react";
import { Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

// Frames between the scene's start and the current shot's start (D-58). A shot re-mounts its card,
// so without this the entrance would replay at every cut; with it, a card enters once per scene.
export const SceneOffset = createContext(0);

// The one card entrance (D-58): fade in and rise 12 px over 250 ms, then hold still. `delay` (s)
// staggers items within a card.
export const useEnter = (delay = 0) => {
  const frame = useCurrentFrame() + useContext(SceneOffset);
  const { fps } = useVideoConfig();
  const t = interpolate(frame - delay * fps, [0, 0.25 * fps], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  return { opacity: t, transform: `translateY(${(1 - t) * 12}px)` };
};
