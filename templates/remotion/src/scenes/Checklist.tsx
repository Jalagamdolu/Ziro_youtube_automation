import React from "react";
import { AbsoluteFill } from "remotion";
import { useEnter } from "../motion";
import { content, theme } from "../theme";
import type { Scene } from "../types";

// Items from the beat; "condition: verdict" items show the verdict in the accent colour.
const Item: React.FC<{ text: string; delay: number }> = ({ text, delay }) => {
  const [condition, verdict] = text.includes(":") ? text.split(/:\s*(.*)/s) : [text, ""];
  return (
    <div style={{
      ...useEnter(delay), display: "flex", gap: 36, alignItems: "flex-start", backgroundColor: theme.surface,
      borderRadius: 32, padding: "44px 48px", boxShadow: "0 24px 60px rgba(0,0,0,0.35)",
    }}>
      <div style={{ flexShrink: 0, width: 72, height: 72, borderRadius: 18, backgroundColor: theme.primary,
        color: theme.ink, fontSize: 52, fontWeight: 800, display: "flex", alignItems: "center",
        justifyContent: "center" }}>✓</div>
      <div style={{ color: theme.ink, fontSize: 50, lineHeight: 1.3 }}>
        {condition}
        {verdict ? <div style={{ color: theme.accent, fontFamily: theme.displayFont, fontSize: 68,
          fontWeight: 700, marginTop: 8 }}>{verdict}</div> : null}
      </div>
    </div>
  );
};

export const Checklist: React.FC<{ scene: Scene; title: string }> = ({ scene }) => {
  const items = (scene.props.items ?? []) as string[];
  return (
    <AbsoluteFill style={{ paddingTop: content.top, paddingLeft: content.left, paddingRight: content.right,
      gap: 40 }}>
      {items.map((item, i) => <Item key={i} text={item} delay={i * 0.8} />)}
    </AbsoluteFill>
  );
};
