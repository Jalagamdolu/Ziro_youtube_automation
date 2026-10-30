// Ziro brand values, taken from ziro.digital on 2026-10-30 (sources per value in decisions.md D-26).
// Fonts are bundled from @fontsource (OFL-1.1), so rendering never fetches anything.
import "@fontsource/inter/400.css";
import "@fontsource/inter/700.css";
import "@fontsource/inter/800.css";
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
};

// YouTube Shorts safe area on a 1080x1920 frame: keep clear of the top bar, the bottom
// title/caption UI and the right-hand action buttons.
export const safe = { top: 220, bottom: 480, left: 60, right: 160 };
export const captionsTop = 1200; // captions sit above the bottom UI band, below scene content
