import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { theme } from "./theme";

// The presenter zone (v2 §8, D-48). Sir's lip-synced clip goes here once it exists (LatentSync
// is deferred); until then a clean brand placeholder: the official wordmark, unaltered, on a light
// studio panel with a slow push-in. Never a drawn or generated person.
export const Presenter: React.FC<{ wordmark: string; frames: number; alt?: boolean; full: boolean }> = (
  { wordmark, frames, alt, full }) => {
  const t = Math.min(1, useCurrentFrame() / Math.max(1, frames));
  const scale = interpolate(t, [0, 1], alt ? [1.08, 1.0] : [1.0, 1.06]);
  return (
    <AbsoluteFill style={{
      background: `radial-gradient(circle at 50% ${full ? 45 : 40}%, #FFFFFF 0%, ${theme.studio} 55%, #E4DAF6 100%)`,
      alignItems: "center", justifyContent: "center",
    }}>
      {wordmark ? <Img src={staticFile(wordmark)} style={{ width: full ? 780 : 600, transform: `scale(${scale})` }} /> : null}
    </AbsoluteFill>
  );
};
