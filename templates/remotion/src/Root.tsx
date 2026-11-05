import React from "react";
import { Composition } from "remotion";
import { Short } from "./Short";
import type { ShortProps } from "./types";

const FPS = 30;

const preview: ShortProps = {
  title: "What makes an AI agent different from a chatbot?",
  audio: "",
  duration: 6,
  presenter: { clip: null, wordmark: "" },
  scenes: [{
    id: "S1", visual_type: "definition_card", start: 0, end: 6,
    shots: [{ start: 0, end: 6, layout: "split", kind: "card", card: true }],
    props: {
      headline: "What is a chatbot?",
      definition: "A chatbot is a software application that communicates with people through text or voice.",
      source: "IBM",
      source_title: "What is a chatbot? (IBM Think)",
    },
  }],
  // One narration cue so a still shows caption placement; real cues come from WhisperX.
  cues: [{
    start: 0, end: 6,
    words: ["A", "chatbot", "is", "a", "software"].map((text, i) => ({ text, start: i * 0.4, end: i * 0.4 + 0.4 })),
  }],
  echoes: [{ start: 0, end: 6, text: "chatbot software", brand: false }],
};

export const Root: React.FC = () => (
  <Composition
    id="Short"
    component={Short}
    width={1080}
    height={1920}
    fps={FPS}
    durationInFrames={Math.round(preview.duration * FPS)}
    defaultProps={preview}
    calculateMetadata={({ props }) => ({ durationInFrames: Math.ceil(props.duration * FPS) })}
  />
);
