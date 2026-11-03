import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import { useEnter } from "../motion";
import { safe, theme } from "../theme";
import type { Scene } from "../types";

// The official Ziro logo, unaltered, on a white panel (its wordmark is black), + the site address.
// Its "#1 AI Career Intelligence Platform" tagline is an approved fact (D-35). Without the logo
// file (e.g. the Studio preview) the card falls back to the text wordmark.
export const EndCard: React.FC<{ scene: Scene; title: string }> = ({ scene }) => {
  const { url, logo } = scene.props as Record<string, string>;
  const mark = useEnter(0);
  const link = useEnter(0.4);
  return (
    <AbsoluteFill style={{ paddingTop: safe.top + 200, paddingLeft: safe.left, paddingRight: safe.right,
      alignItems: "center" }}>
      {logo ? (
        <div style={{ ...mark, backgroundColor: "#FFFFFF", borderRadius: 36, padding: "48px 44px",
          boxShadow: "0 24px 60px rgba(0,0,0,0.35)" }}>
          <Img src={staticFile(logo)} style={{ width: 760, display: "block" }} />
        </div>
      ) : (
        <div style={{ ...mark, color: theme.ink, fontFamily: theme.displayFont, fontSize: 220,
          fontWeight: 700, letterSpacing: -4, lineHeight: 1 }}>
          Ziro<span style={{ color: theme.accent }}>.</span>
        </div>
      )}
      {url ? (
        <div style={{ ...link, color: theme.ink, fontSize: 64, fontWeight: 700, marginTop: 64,
          backgroundColor: theme.surface, borderRadius: 999, padding: "24px 56px" }}>{url}</div>
      ) : null}
    </AbsoluteFill>
  );
};
