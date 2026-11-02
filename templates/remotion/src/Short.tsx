import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile, useVideoConfig } from "remotion";
import { Background } from "./Background";
import { Captions } from "./Captions";
import { ChatBubble } from "./scenes/ChatBubble";
import { Checklist } from "./scenes/Checklist";
import { Comparison } from "./scenes/Comparison";
import { DefinitionCard } from "./scenes/DefinitionCard";
import { EndCard } from "./scenes/EndCard";
import { Flow } from "./scenes/Flow";
import { TitleCard } from "./scenes/TitleCard";
import { theme } from "./theme";
import type { Scene, ShortProps } from "./types";

// visual_type (src/app/nodes/storyboarding.py) -> template; anything else gets the title card.
const templates: Record<string, React.FC<{ scene: Scene; title: string }>> = {
  definition_card: DefinitionCard,
  quote_card: DefinitionCard,
  comparison: Comparison,
  chat_bubble: ChatBubble,
  flow: Flow,
  checklist: Checklist,
  end_card: EndCard,
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
            {scene.background ? (
              <Background file={scene.background} seconds={scene.background_seconds ?? scene.end - scene.start} />
            ) : null}
            <Template scene={scene} title={title} />
          </Sequence>
        );
      })}
      <Captions cues={cues} />
    </AbsoluteFill>
  );
};
