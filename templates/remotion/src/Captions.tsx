import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { safe, split, theme } from "./theme";
import type { Cue } from "./types";

// Layer (a) of the two-layer captions (D-48): a small transcription box, two short lines, white on
// black, in the upper content area; the spoken word in Ziro orange. Word timings from WhisperX.
export const Captions: React.FC<{ cues: Cue[]; hidden: boolean }> = ({ cues, hidden }) => {
  const t = useCurrentFrame() / useVideoConfig().fps;
  const cue = cues.find((c) => c.start <= t && t < c.end);
  if (!cue || hidden) return null;
  return (
    <div style={{ position: "absolute", top: split.transcriptTop, left: safe.left, right: safe.left,
      display: "flex", justifyContent: "center" }}>
      <div style={{
        maxWidth: 900, backgroundColor: "rgba(0,0,0,0.86)", borderRadius: 14, padding: "12px 24px",
        fontFamily: theme.bodyFont, fontSize: 42, fontWeight: 700, lineHeight: 1.3, color: "#FFFFFF",
        textAlign: "center",
      }}>
        {cue.words.map((w, i) => (
          <span key={i} style={{ color: w.start <= t && t < w.end ? theme.accent : "#FFFFFF" }}>
            {w.text}{i < cue.words.length - 1 ? " " : ""}
          </span>
        ))}
      </div>
    </div>
  );
};
