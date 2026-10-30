import React from "react";
import { AbsoluteFill } from "remotion";
import { safe, theme } from "../theme";
import type { Scene } from "../types";

// Fallback for scene types whose template is not built yet: the video's topic, nothing invented.
export const TitleCard: React.FC<{ scene: Scene; title: string }> = ({ title }) => (
  <AbsoluteFill style={{ paddingTop: safe.top, paddingLeft: safe.left, paddingRight: safe.right }}>
    <div style={{ color: theme.ink, fontFamily: theme.displayFont, fontSize: 72, fontWeight: 700,
      lineHeight: 1.12 }}>{title}</div>
  </AbsoluteFill>
);
