// Props the pipeline's rendering stage passes in (written by src/app/nodes/rendering.py).

export type Scene = {
  id: string;
  visual_type: string;
  start: number; // seconds
  end: number;
  props: Record<string, string | string[]>; // lists: flow steps, checklist items
  photo?: string; // stock photo in the public dir (D-34); absent = solid background
  capture?: string; // screenshot of the cited source page (D-37)
  shots?: Shot[]; // cuts within the scene (D-37); absent = one shot
};

export type Shot = {
  start: number; // seconds, absolute
  end: number;
  kind: "photo" | "photo_alt" | "capture" | "card" | "end";
  card: boolean; // show the scene's card/template during this shot
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
