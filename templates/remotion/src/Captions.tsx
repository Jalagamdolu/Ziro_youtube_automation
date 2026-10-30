import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { captionsTop, safe, theme } from "./theme";
import type { Cue } from "./types";

// Word-timed captions (WhisperX alignment): the current cue, with the spoken word highlighted.
export const Captions: React.FC<{ cues: Cue[] }> = ({ cues }) => {
  const t = useCurrentFrame() / useVideoConfig().fps;
  const cue = cues.find((c) => c.start <= t && t < c.end);
  if (!cue) return null;
  return (
    <div style={{
      position: "absolute", top: captionsTop, left: safe.left, right: safe.right,
      textAlign: "center", fontFamily: theme.bodyFont, fontSize: 64, fontWeight: 800, lineHeight: 1.2, color: theme.ink,
      textShadow: "0 4px 12px rgba(0,0,0,0.85)",
    }}>
      {cue.words.map((w, i) => (
        <span key={i} style={{ color: w.start <= t && t < w.end ? theme.accent : theme.ink }}>
          {w.text}{i < cue.words.length - 1 ? " " : ""}
        </span>
      ))}
    </div>
  );
};
