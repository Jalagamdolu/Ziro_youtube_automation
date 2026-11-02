import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { theme } from "./theme";

// A real photo that carries the scene (D-34): full frame, slow zoom and drift (Ken Burns), darkened
// only where text sits (cards at the top, captions lower down) so the photo stays the story.
export const Photo: React.FC<{ file: string; frames: number }> = ({ file, frames }) => {
  const t = Math.min(1, useCurrentFrame() / Math.max(1, frames)); // frame is scene-relative
  const scale = interpolate(t, [0, 1], [1.04, 1.14]);
  const drift = interpolate(t, [0, 1], [0, -40]);
  return (
    <AbsoluteFill>
      <Img src={staticFile(file)}
        style={{ width: "100%", height: "100%", objectFit: "cover",
                 transform: `scale(${scale}) translateY(${drift}px)` }} />
      <AbsoluteFill style={{
        background: `linear-gradient(180deg, ${theme.background}d9 0%, ${theme.background}66 30%, ` +
                    `${theme.background}1a 45%, ${theme.background}80 58%, ${theme.background}e6 72%, ` +
                    `${theme.background}f2 100%)`,
      }} />
    </AbsoluteFill>
  );
};
