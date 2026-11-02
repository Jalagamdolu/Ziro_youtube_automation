// Props the pipeline's rendering stage passes in (written by src/app/nodes/rendering.py).

export type Scene = {
  id: string;
  visual_type: string;
  start: number; // seconds
  end: number;
  props: Record<string, string | string[]>; // lists: flow steps, checklist items
};

export type Cue = {
  start: number;
  end: number;
  words: { text: string; start: number; end: number }[];
};

export type ShortProps = {
  title: string;
  audio: string; // file name inside the render's public dir
  duration: number; // seconds
  scenes: Scene[];
  cues: Cue[];
};
