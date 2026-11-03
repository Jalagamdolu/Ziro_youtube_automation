// Props the pipeline's rendering stage passes in (written by src/app/nodes/rendering.py).

export type Scene = {
  id: string;
  visual_type: string;
  start: number; // seconds
  end: number;
  props: Record<string, string | string[]>; // lists: flow steps, checklist items
  photo?: string; // stock photo in the public dir (D-34); absent = solid background
  layout?: "presenter" | "split" | "photo"; // presenter videos only (D-36)
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
  presenter?: string | null; // the presenter's recording in the public dir (D-36)
  scenes: Scene[];
  cues: Cue[];
};
