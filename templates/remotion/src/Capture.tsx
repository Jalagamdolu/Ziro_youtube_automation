import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { theme } from "./theme";

// The cited source page itself (D-37): a genuine full-width screenshot scrolled slowly, credited.
export const Capture: React.FC<{ file: string; frames: number; source: string }> = (
  { file, frames, source }) => {
  const t = Math.min(1, useCurrentFrame() / Math.max(1, frames));
  const height = 1920;
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: 0, right: 0, top: 0, height, overflow: "hidden",
        backgroundColor: "#FFFFFF" }}>
        <Img src={staticFile(file)} style={{ width: "100%", display: "block",
          transform: `translateY(${interpolate(t, [0, 1], [0, -Math.round(height * 0.45)])}px)` }} />
      </div>
      <div style={{ position: "absolute", left: 60, top: 1720, backgroundColor: theme.background,
        color: theme.ink, fontFamily: theme.bodyFont, fontSize: 34, fontWeight: 700, padding: "10px 24px",
        borderRadius: 999 }}>Source: {source}</div>
    </AbsoluteFill>
  );
};
