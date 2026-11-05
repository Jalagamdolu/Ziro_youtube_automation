import React from "react";
import { AbsoluteFill } from "remotion";
import { useEnter } from "../motion";
import { content, theme } from "../theme";
import type { Scene } from "../types";

// A user's message (from the beat) and one reply bubble. The reply is drawn as typing dots, so the
// scene never shows an answer the script does not contain. A generic illustration, not a product UI.
// The dots are still: a card enters once and then holds (D-58).
export const ChatBubble: React.FC<{ scene: Scene; title: string }> = ({ scene }) => {
  const { message } = scene.props as Record<string, string>;
  const asked = useEnter(0);
  const reply = useEnter(0.6);
  return (
    <AbsoluteFill style={{ paddingTop: content.top, paddingLeft: content.left, paddingRight: content.right,
      gap: 40 }}>
      <div style={{
        ...asked, alignSelf: "flex-end", maxWidth: "80%", backgroundColor: theme.primary, color: theme.ink,
        borderRadius: "48px 48px 12px 48px", padding: "40px 52px", fontSize: 60, fontWeight: 700,
      }}>{message}</div>
      <div style={{
        ...reply, alignSelf: "flex-start", display: "flex", gap: 22, backgroundColor: theme.surface,
        borderRadius: "48px 48px 48px 12px", padding: "52px 60px",
      }}>
        {[0, 1, 2].map((i) => (
          <div key={i} style={{ width: 30, height: 30, borderRadius: 15, backgroundColor: theme.muted,
            opacity: 1 - i * 0.25 }} />
        ))}
      </div>
    </AbsoluteFill>
  );
};
