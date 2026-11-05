import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { split, theme } from "./theme";

// Source proof (D-37, D-48): the cited page itself, a genuine screenshot scrolled slowly in the
// content area, credited. One per video. It starts low so the highlighted quote clears the
// transcription box, then scrolls up.
export const Capture: React.FC<{ file: string; frames: number; source: string }> = (
  { file, frames, source }) => {
  const t = Math.min(1, useCurrentFrame() / Math.max(1, frames));
  return (
    <AbsoluteFill style={{ backgroundColor: "#FFFFFF", overflow: "hidden" }}>
      <Img src={staticFile(file)} style={{ width: "100%", display: "block",
        transform: `translateY(${interpolate(t, [0, 1], [split.contentTop - 90, 140])}px)` }} />
      <div style={{ position: "absolute", left: 60, top: split.contentBottom - 150, backgroundColor: theme.background,
        color: theme.ink, fontFamily: theme.bodyFont, fontSize: 34, fontWeight: 700, padding: "10px 24px",
        borderRadius: 999 }}>Source: {source}</div>
    </AbsoluteFill>
  );
};
