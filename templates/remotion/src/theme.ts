// Ziro brand values, taken from ziro.digital on 2026-10-30 (sources per value in decisions.md D-26).
// Fonts are bundled from @fontsource (OFL-1.1), so rendering never fetches anything.
import "@fontsource/inter/400.css";
import "@fontsource/inter/700.css";
import "@fontsource/inter/800.css";
import "@fontsource/playfair-display/700-italic.css";
import "@fontsource/space-grotesk/600.css";
import "@fontsource/space-grotesk/700.css";

export const theme = {
  background: "#0F131A", // site dark theme --background, hsl(215 28% 8%)
  surface: "#171D26", // site dark theme --card, hsl(215 25% 12%)
  ink: "#F8FAFC", // site dark theme --foreground, hsl(210 40% 98%)
  muted: "#A694B8", // site dark theme --muted-foreground, hsl(270 20% 65%)
  primary: "#9952E0", // site dark theme --primary, hsl(270 70% 60%); readable on dark
  logoPurple: "#5101D4", // dominant colour of the official logo PNG (too dark for text on dark)
  accent: "#FF7700", // site --ws-brand, hsl(28 100% 50%)
  bodyFont: "Inter, DejaVu Sans, sans-serif", // site body font
  displayFont: "Space Grotesk, Inter, sans-serif", // site display font
  punchFont: "Playfair Display, DejaVu Serif, serif", // text-pop punch words, italic (D-48)
};

// YouTube Shorts safe area on a 1080x1920 frame: keep clear of the top bar, the bottom
// title/caption UI and the right-hand action buttons.
export const safe = { top: 220, bottom: 480, left: 60, right: 160 };

// Split layout (v2 §8, D-48): content in the top ~60%, presenter zone below the divider.
export const split = {
  divider: 1152, // 60% of 1920
  transcriptTop: 236, // the small two-line transcription box, under the top bar
  contentTop: 392, // cards start under the transcription box...
  contentBottom: 1074, // ...and end above the echo pill on the divider
  cardScale: 0.85, // cards drawn at 85% so a four-step flow fits the content box
};
// Inside the content box, cards keep this padding (they never draw full-frame any more).
export const content = { top: 0, left: 60, right: 100 };
