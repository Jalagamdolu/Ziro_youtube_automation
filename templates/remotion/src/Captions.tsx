import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { captionsTop, safe, theme } from "./theme";
import type { Cue } from "./types";

// Word-timed captions (WhisperX alignment), Shorts style (D-37): 2-3 words at a time, uppercase,
// heavy and outlined in the middle of the frame, the spoken word in Ziro orange.
export const Captions: React.FC<{ cues: Cue[] }> = ({ cues }) => {
  const t = useCurrentFrame() / useVideoConfig().fps;
  const cue = cues.find((c) => c.start <= t && t < c.end);
  if (!cue) return null;
  return (
    <div style={{
      position: "absolute", top: captionsTop, left: safe.left, right: safe.right,
      textAlign: "center", fontFamily: theme.bodyFont, fontSize: 96, fontWeight: 800, lineHeight: 1.1,
      color: theme.ink, textTransform: "uppercase", letterSpacing: 1,
      WebkitTextStroke: "3px #000000", paintOrder: "stroke fill",
      textShadow: "0 6px 18px rgba(0,0,0,0.9)",
    }}>
      {cue.words.map((w, i) => (
        <span key={i} style={{ color: w.start <= t && t < w.end ? theme.accent : theme.ink }}>
          {w.text}{i < cue.words.length - 1 ? " " : ""}
        </span>
      ))}
    </div>
  );
};
