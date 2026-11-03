import React from "react";
import { AbsoluteFill, OffthreadVideo, staticFile } from "remotion";
import { theme } from "./theme";

// The real presenter's recording (D-36), muted here because its audio is the narration track.
// `from` keeps it in sync across scene cuts. Full: fills the frame. Split: the card owns the top
// half on a solid background and the presenter fills the bottom half.
export const Presenter: React.FC<{ file: string; from: number; split?: boolean }> = (
  { file, from, split }) => (
  <AbsoluteFill style={{ backgroundColor: theme.background }}>
    <div style={{ position: "absolute", left: 0, right: 0, top: split ? 960 : 0, bottom: 0,
      overflow: "hidden" }}>
      <OffthreadVideo src={staticFile(file)} startFrom={from} muted
        style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "50% 25%" }} />
    </div>
    <AbsoluteFill style={{
      background: `linear-gradient(180deg, ${theme.background}00 55%, ${theme.background}b3 75%, ` +
                  `${theme.background}e6 100%)`,
    }} />
  </AbsoluteFill>
);
