import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile, useVideoConfig } from "remotion";
import { Captions } from "./Captions";
import { DefinitionCard } from "./scenes/DefinitionCard";
import { TitleCard } from "./scenes/TitleCard";
import { theme } from "./theme";
import type { Scene, ShortProps } from "./types";

// visual_type -> template. Types without a template yet fall back to the title card.
const templates: Record<string, React.FC<{ scene: Scene; title: string }>> = {
  definition_card: DefinitionCard,
};

export const Short: React.FC<ShortProps> = ({ title, audio, scenes, cues }) => {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: theme.background, fontFamily: theme.bodyFont }}>
      {audio ? <Audio src={staticFile(audio)} /> : null}
      {scenes.map((scene) => {
        const Template = templates[scene.visual_type] ?? TitleCard;
        const from = Math.round(scene.start * fps);
        const frames = Math.max(1, Math.round(scene.end * fps) - from);
        return (
          <Sequence key={scene.id} from={from} durationInFrames={frames}>
            <Template scene={scene} title={title} />
          </Sequence>
        );
      })}
      <Captions cues={cues} />
    </AbsoluteFill>
  );
};
