import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { safe, split, theme } from "./theme";
import type { Cue } from "./types";

// Layer (a) of the two-layer captions (D-48): a small transcription box, two short lines, white on
// black, in the upper content area; the spoken word pops (orange, 1.06x over 120 ms, D-58). Word
// timings from WhisperX.
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
        {cue.words.map((w, i) => {
          const on = w.start <= t && t < w.end;
          const pop = on ? interpolate(t - w.start, [0, 0.12], [1, 1.06], { extrapolateRight: "clamp" }) : 1;
          // a real space between words, plus room for the 1.06x pop so it never touches them
          return (
            <React.Fragment key={i}>
              {i ? " " : null}
              <span style={{ display: "inline-block", color: on ? theme.accent : "#FFFFFF",
                transform: `scale(${pop})`, margin: on ? "0 0.18em" : 0 }}>{w.text}</span>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};
