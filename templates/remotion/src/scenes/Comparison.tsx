import React from "react";
import { AbsoluteFill } from "remotion";
import { useEnter } from "../motion";
import { content, theme } from "../theme";
import type { Scene } from "../types";

const Side: React.FC<{ text: string; color: string; delay: number }> = ({ text, color, delay }) => (
  <div style={{
    ...useEnter(delay), backgroundColor: theme.surface, borderRadius: 32, borderTop: `14px solid ${color}`,
    padding: "64px 32px", textAlign: "center", color: theme.ink, fontFamily: theme.displayFont,
    fontSize: 76, fontWeight: 700, boxShadow: "0 24px 60px rgba(0,0,0,0.35)",
  }}>{text}</div>
);

// Two things side by side (both names come from the [ON SCREEN] beat) with a marker between.
export const Comparison: React.FC<{ scene: Scene; title: string }> = ({ scene }) => {
  const { left, right, between } = scene.props as Record<string, string>;
  const mark = useEnter(0.5);
  return (
    <AbsoluteFill style={{ paddingTop: content.top, paddingLeft: content.left, paddingRight: content.right,
      gap: 36 }}>
      <Side text={left} color={theme.primary} delay={0} />
      <div style={{ ...mark, alignSelf: "center", color: theme.accent, fontFamily: theme.displayFont,
        fontSize: 140, fontWeight: 700, lineHeight: 1 }}>{between}</div>
      <Side text={right} color={theme.accent} delay={0.25} />
    </AbsoluteFill>
  );
};
