import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile, useVideoConfig } from "remotion";
import { Captions } from "./Captions";
import { Photo } from "./Photo";
import { ChatBubble } from "./scenes/ChatBubble";
import { Checklist } from "./scenes/Checklist";
import { Comparison } from "./scenes/Comparison";
import { DefinitionCard } from "./scenes/DefinitionCard";
import { EndCard } from "./scenes/EndCard";
import { Flow } from "./scenes/Flow";
import { TitleCard } from "./scenes/TitleCard";
import { theme } from "./theme";
import { Capture } from "./Capture";
import type { Scene, Shot, ShortProps } from "./types";

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
        const shots: Shot[] = scene.shots ?? [{ start: scene.start, end: scene.end, card: true,
          kind: scene.photo ? "photo" : "card" }];
        return (
          <Sequence key={scene.id} from={from} durationInFrames={frames}>
            {shots.map((shot, n) => {
              const shotFrom = Math.round(shot.start * fps);
              const shotFrames = Math.max(1, Math.round(shot.end * fps) - shotFrom);
              return (
                <Sequence key={n} from={shotFrom - from} durationInFrames={shotFrames}>
                  <ShotLayer shot={shot} scene={scene} frames={shotFrames} />
                  {shot.card ? <Template scene={scene} title={title} /> : null}
                </Sequence>
              );
            })}
          </Sequence>
        );
      })}
      <Captions cues={cues} />
    </AbsoluteFill>
  );
};

// One shot's background (D-37): the scene's photo (two camera moves) or the cited source page.
// Cards and captions draw on top.
const ShotLayer: React.FC<{ shot: Shot; scene: Scene; frames: number }> = ({ shot, scene, frames }) => {
  const source = String(scene.props.source ?? "");
  switch (shot.kind) {
    case "capture":
      return scene.capture ? <Capture file={scene.capture} frames={frames} source={source} /> : null;
    case "photo":
    case "photo_alt":
      return scene.photo ? <Photo file={scene.photo} frames={frames} alt={shot.kind === "photo_alt"} /> : null;
    default:
      return null;
  }
};
