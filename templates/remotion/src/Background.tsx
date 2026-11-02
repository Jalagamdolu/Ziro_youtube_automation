import React from "react";
import { AbsoluteFill, Loop, OffthreadVideo, staticFile, useVideoConfig } from "remotion";
import { theme } from "./theme";

// Stock clip behind a scene (D-33): muted, looped, softened and tinted to the brand colours so
// cards and captions stay readable. Scenes without a clip keep the solid background.
export const Background: React.FC<{ file: string; seconds: number }> = ({ file, seconds }) => {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill>
      <Loop durationInFrames={Math.max(1, Math.floor(seconds * fps))}>
        <OffthreadVideo src={staticFile(file)} muted
          style={{ width: "100%", height: "100%", objectFit: "cover", filter: "blur(3px) saturate(0.8)" }} />
      </Loop>
      <AbsoluteFill style={{ backgroundColor: theme.logoPurple, opacity: 0.18 }} />
      <AbsoluteFill style={{
        background: `linear-gradient(180deg, ${theme.background}cc 0%, ${theme.background}e0 55%, ${theme.background}f2 100%)`,
      }} />
    </AbsoluteFill>
  );
};
