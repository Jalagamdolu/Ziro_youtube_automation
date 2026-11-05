import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { split, theme } from "./theme";
import type { Echo as EchoCue } from "./types";

// Layer (b) of the two-layer captions (D-48): the key words of the sentence being spoken, large,
// in a dark pill straddling the split's divider; every third one in the brand colour.
export const Echo: React.FC<{ echoes: EchoCue[] }> = ({ echoes }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const echo = echoes.find((e) => e.start <= t && t < e.end);
  if (!echo) return null;
  const pop = spring({ frame: frame - Math.round(echo.start * fps), fps, config: { damping: 14 } });
  return (
    <div style={{ position: "absolute", top: split.divider, left: 0, right: 0, display: "flex",
      justifyContent: "center", transform: `translateY(-50%) scale(${interpolate(pop, [0, 1], [0.8, 1])})`,
      opacity: pop }}>
      <div style={{
        maxWidth: 960, backgroundColor: echo.brand ? theme.primary : "rgba(10,12,18,0.94)",
        color: theme.ink, borderRadius: 999, padding: "18px 48px", fontFamily: theme.displayFont,
        fontSize: 76, fontWeight: 700, lineHeight: 1.1, textAlign: "center", textTransform: "uppercase",
        boxShadow: "0 18px 50px rgba(0,0,0,0.45)",
      }}>{echo.text}</div>
    </div>
  );
};
