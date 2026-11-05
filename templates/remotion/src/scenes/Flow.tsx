import React from "react";
import { AbsoluteFill } from "remotion";
import { useEnter } from "../motion";
import { content, theme } from "../theme";
import type { Scene } from "../types";

const Step: React.FC<{ text: string; n: number; last: boolean; delay: number }> = ({ text, n, last, delay }) => (
  <div style={{ ...useEnter(delay), display: "flex", flexDirection: "column", alignItems: "center" }}>
    <div style={{
      display: "flex", alignItems: "center", gap: 28, width: 640, backgroundColor: theme.surface,
      borderRadius: 28, padding: "26px 36px", borderLeft: `12px solid ${theme.primary}`,
    }}>
      <div style={{ color: theme.primary, fontFamily: theme.displayFont, fontSize: 44, fontWeight: 700 }}>{n}</div>
      <div style={{ color: theme.ink, fontSize: 54, fontWeight: 700 }}>
        {text.charAt(0).toUpperCase() + text.slice(1)}
      </div>
    </div>
    {last ? null : <div style={{ color: theme.accent, fontSize: 48, lineHeight: 1.1 }}>↓</div>}
  </div>
);

// Steps from the beat, top to bottom; `label` (e.g. "example") marks it as illustrative.
export const Flow: React.FC<{ scene: Scene; title: string }> = ({ scene }) => {
  const steps = (scene.props.steps ?? []) as string[];
  const label = scene.props.label as string;
  const tag = useEnter(0);
  return (
    <AbsoluteFill style={{ paddingTop: content.top, paddingLeft: content.left, paddingRight: content.right,
      alignItems: "center" }}>
      {label ? (
        <div style={{ ...tag, alignSelf: "flex-start", color: theme.accent, fontFamily: theme.displayFont,
          fontSize: 34, fontWeight: 700, letterSpacing: 6, border: `3px solid ${theme.accent}`,
          borderRadius: 999, padding: "8px 28px", marginBottom: 28 }}>{label.toUpperCase()}</div>
      ) : null}
      {steps.map((s, i) => (
        <Step key={i} text={s} n={i + 1} last={i === steps.length - 1} delay={0.3 + i * 0.35} />
      ))}
    </AbsoluteFill>
  );
};
