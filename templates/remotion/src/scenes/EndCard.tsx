import React from "react";
import { AbsoluteFill } from "remotion";
import { useEnter } from "../motion";
import { safe, theme } from "../theme";
import type { Scene } from "../types";

// Text wordmark "Ziro" + the site address from the beat. The logo PNG is not used: it carries an
// unapproved ranking tagline (D-26).
export const EndCard: React.FC<{ scene: Scene; title: string }> = ({ scene }) => {
  const { url } = scene.props as Record<string, string>;
  const mark = useEnter(0);
  const link = useEnter(0.4);
  return (
    <AbsoluteFill style={{ paddingTop: safe.top + 200, paddingLeft: safe.left, paddingRight: safe.right,
      alignItems: "center" }}>
      <div style={{ ...mark, color: theme.ink, fontFamily: theme.displayFont, fontSize: 220, fontWeight: 700,
        letterSpacing: -4, lineHeight: 1 }}>
        Ziro<span style={{ color: theme.accent }}>.</span>
      </div>
      <div style={{ ...mark, width: 220, height: 12, borderRadius: 6, backgroundColor: theme.primary,
        marginTop: 36 }} />
      {url ? (
        <div style={{ ...link, color: theme.ink, fontSize: 64, fontWeight: 700, marginTop: 64,
          backgroundColor: theme.surface, borderRadius: 999, padding: "24px 56px" }}>{url}</div>
      ) : null}
    </AbsoluteFill>
  );
};
