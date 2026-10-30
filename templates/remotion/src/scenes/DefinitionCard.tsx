import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { safe, theme } from "../theme";
import type { Scene } from "../types";

// A sourced definition: headline from the [ON SCREEN] beat, body = the approved claim's wording,
// attribution = the claim's source (never text the claim ledger does not contain).
export const DefinitionCard: React.FC<{ scene: Scene; title: string }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200 } });
  const { headline, definition, source, source_title } = scene.props;
  return (
    <AbsoluteFill style={{ paddingTop: safe.top + 40, paddingLeft: safe.left, paddingRight: safe.right }}>
      <div style={{
        opacity: enter, transform: `translateY(${interpolate(enter, [0, 1], [40, 0])}px)`,
        backgroundColor: theme.surface, borderRadius: 32, padding: "56px 56px 48px",
        borderLeft: `14px solid ${theme.primary}`, boxShadow: "0 24px 60px rgba(0,0,0,0.35)",
      }}>
        <div style={{ color: theme.primary, fontFamily: theme.displayFont, fontSize: 34, fontWeight: 700,
          letterSpacing: 6 }}>
          DEFINITION
        </div>
        <div style={{ color: theme.ink, fontFamily: theme.displayFont, fontSize: 72, fontWeight: 700,
          lineHeight: 1.1, marginTop: 20 }}>
          {headline}
        </div>
        <div style={{ color: theme.ink, fontSize: 46, lineHeight: 1.35, marginTop: 32 }}>
          {definition}
        </div>
        <div style={{ color: theme.muted, fontSize: 32, marginTop: 40 }}>
          Source: {source}{source_title ? ` · ${source_title}` : ""}
        </div>
      </div>
    </AbsoluteFill>
  );
};
