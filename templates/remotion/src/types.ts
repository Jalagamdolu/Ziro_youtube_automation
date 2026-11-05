// Props the pipeline's rendering stage passes in (written by src/app/nodes/rendering.py).

export type Scene = {
  id: string;
  visual_type: string;
  start: number; // seconds
  end: number;
  props: Record<string, string | string[]>; // lists: flow steps, checklist items
  photo?: string; // stock photo in the public dir (D-34); absent = solid background
  capture?: string; // screenshot of the cited source page (D-37), one per video (D-48)
  shots?: Shot[]; // the timeline within the scene (D-48); absent = one card shot
  pop?: { sentence: number; text: string; punch: string[] }; // full-screen text pop
};

export type Shot = {
  start: number; // seconds, absolute
  end: number;
  layout: "split" | "full";
  kind: "card" | "card_alt" | "photo" | "capture" | "presenter" | "presenter_alt" | "pop" | "end";
  card: boolean; // show the scene's card template
};

export type Cue = {
  start: number;
  end: number;
  words: { text: string; start: number; end: number }[];
};

export type Echo = { start: number; end: number; text: string; brand: boolean };

export type ShortProps = {
  title: string;
  audio: string; // file name inside the render's public dir
  duration: number; // seconds
  presenter: { clip: string | null; wordmark: string }; // clip: sir's video, when it exists
  scenes: Scene[];
  cues: Cue[]; // small transcription box
  echoes: Echo[]; // large phrase on the divider
};
