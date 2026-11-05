import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Capture } from "./Capture";
import { Captions } from "./Captions";
import { Echo } from "./Echo";
import { Photo } from "./Photo";
import { Presenter } from "./Presenter";
import { TextPop } from "./TextPop";
import { ChatBubble } from "./scenes/ChatBubble";
import { Checklist } from "./scenes/Checklist";
import { Comparison } from "./scenes/Comparison";
import { DefinitionCard } from "./scenes/DefinitionCard";
import { EndCard } from "./scenes/EndCard";
import { Flow } from "./scenes/Flow";
import { TitleCard } from "./scenes/TitleCard";
import { split, theme } from "./theme";
import type { Scene, Shot, ShortProps } from "./types";

// visual_type (src/app/nodes/storyboarding.py) -> card; anything else gets the title card.
const templates: Record<string, React.FC<{ scene: Scene; title: string }>> = {
  definition_card: DefinitionCard,
  quote_card: DefinitionCard,
  comparison: Comparison,
  chat_bubble: ChatBubble,
  flow: Flow,
  checklist: Checklist,
  end_card: EndCard,
};

// The split-layout Short (v2 §8, D-48): shots alternate SPLIT (content top ~60%, presenter zone
// bottom ~40%) and FULL (presenter, text pop, end card); two caption layers ride on top.
export const Short: React.FC<ShortProps> = ({ title, audio, presenter, scenes, cues, echoes }) => {
  const { fps } = useVideoConfig();
  const t = useCurrentFrame() / fps;
  const now = scenes.flatMap((s) => s.shots ?? []).find((s) => s.start <= t && t < s.end);
  return (
    <AbsoluteFill style={{ backgroundColor: theme.background, fontFamily: theme.bodyFont }}>
      {audio ? <Audio src={staticFile(audio)} /> : null}
      {scenes.map((scene) => {
        const shots: Shot[] = scene.shots ?? [{ start: scene.start, end: scene.end, layout: "split",
          kind: "card", card: true }];
        return shots.map((shot, n) => {
          const from = Math.round(shot.start * fps);
          const frames = Math.max(1, Math.round(shot.end * fps) - from);
          return (
            <Sequence key={`${scene.id}-${n}`} from={from} durationInFrames={frames}>
              <ShotView shot={shot} scene={scene} frames={frames} title={title} wordmark={presenter.wordmark} />
            </Sequence>
          );
        });
      })}
      <Captions cues={cues} hidden={now?.kind === "end"} />
      <Echo echoes={echoes} />
    </AbsoluteFill>
  );
};

const ShotView: React.FC<{ shot: Shot; scene: Scene; frames: number; title: string; wordmark: string }> = (
  { shot, scene, frames, title, wordmark }) => {
  if (shot.layout === "full") {
    switch (shot.kind) {
      case "pop":
        return <TextPop text={scene.pop?.text ?? ""} punch={scene.pop?.punch ?? []} />;
      case "end":
        return <EndCard scene={scene} title={title} />;
      default:
        return <Presenter wordmark={wordmark} frames={frames} alt={shot.kind === "presenter_alt"} full />;
    }
  }
  const Card = templates[scene.visual_type] ?? TitleCard;
  const scale = shot.kind === "card_alt" ? split.cardScale * 1.08 : split.cardScale;
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: split.divider, overflow: "hidden",
        backgroundColor: theme.background }}>
        {shot.kind === "photo" && scene.photo ? <Photo file={scene.photo} frames={frames} /> : null}
        {shot.kind === "capture" && scene.capture
          ? <Capture file={scene.capture} frames={frames} source={String(scene.props.source ?? "")} /> : null}
        {shot.card ? (
          <div style={{ position: "absolute", top: split.contentTop, left: 0,
            width: 1080 / scale, height: (split.contentBottom - split.contentTop) / scale,
            transform: `scale(${scale})`, transformOrigin: "top left" }}>
            <Card scene={scene} title={title} />
          </div>
        ) : null}
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, top: split.divider, bottom: 0, overflow: "hidden" }}>
        <Presenter wordmark={wordmark} frames={frames} full={false} />
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, top: split.divider - 3, height: 6,
        backgroundColor: theme.primary }} />
    </AbsoluteFill>
  );
};
