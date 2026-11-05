import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { safe, theme } from "./theme";

// A full-screen statement (D-48), words the narration says; the punch words in serif italics,
// the way "80 becomes 79" lands. The statement scales in slightly; words rise one after another.
export const TextPop: React.FC<{ text: string; punch: string[] }> = ({ text, punch }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const marked = new Set(punch.map((p) => p.toLowerCase()));
  const words = text.split(/\s+/);
  return (
    <AbsoluteFill style={{ background: `radial-gradient(circle at 50% 45%, ${theme.surface} 0%, ${theme.background} 70%)`,
      alignItems: "center", justifyContent: "center", paddingLeft: safe.left + 20, paddingRight: safe.left + 20 }}>
      <div style={{ textAlign: "center", lineHeight: 1.15, color: theme.ink, fontFamily: theme.bodyFont,
        fontSize: 108, fontWeight: 800, letterSpacing: -1,
        transform: `scale(${interpolate(spring({ frame, fps, config: { damping: 200 } }), [0, 1], [0.94, 1])})` }}>
        {words.map((word, i) => {
          const t = spring({ frame: frame - i * 3, fps, config: { damping: 200 } });
          const bare = word.replace(/[^\p{L}\p{N}'-]/gu, "").toLowerCase();
          const hit = marked.has(bare);
          return (
            <span key={i} style={{ display: "inline-block", opacity: t, marginRight: 28,
              transform: `translateY(${interpolate(t, [0, 1], [30, 0])}px)`,
              ...(hit ? { fontFamily: theme.punchFont, fontStyle: "italic", fontWeight: 700,
                          color: theme.accent, fontSize: 124 } : {}) }}>{word}</span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
