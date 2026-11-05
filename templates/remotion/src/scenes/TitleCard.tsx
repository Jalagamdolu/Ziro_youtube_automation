import React from "react";
import { AbsoluteFill } from "remotion";
import { useEnter } from "../motion";
import { content, theme } from "../theme";
import type { Scene } from "../types";

// Beats with no matching template: the beat's quoted text, else the video's topic. Nothing invented.
export const TitleCard: React.FC<{ scene: Scene; title: string }> = ({ scene, title }) => (
  <AbsoluteFill style={{ paddingTop: content.top, paddingLeft: content.left, paddingRight: content.right }}>
    <div style={{ ...useEnter(), color: theme.ink, fontFamily: theme.displayFont, fontSize: 88, fontWeight: 700,
      lineHeight: 1.12, borderLeft: `14px solid ${theme.accent}`, paddingLeft: 40 }}>
      {(scene.props.headline as string) || title}
    </div>
  </AbsoluteFill>
);
