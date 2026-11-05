import React from "react";
import { AbsoluteFill, OffthreadVideo, staticFile } from "remotion";
import { safe, theme } from "./theme";

// The presenter zone is sir's place (D-57). His lip-synced clip drops in here once it exists
// (`clip`); until then a still placeholder: a deep purple gradient, a plain person silhouette and
// a small "presenter — sir" label. No logo here: the official logo appears only on the end card
// (D-35). Never a drawn face or a generated person.
export const Presenter: React.FC<{ clip: string | null; full: boolean }> = ({ clip, full }) => {
  if (clip) {
    return (
      <AbsoluteFill>
        <OffthreadVideo src={staticFile(clip)} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      </AbsoluteFill>
    );
  }
  const size = full ? 760 : 470; // silhouette height
  return (
    <AbsoluteFill style={{
      background: `radial-gradient(ellipse 90% 70% at 50% 35%, #6A2BC9 0%, #3D1478 55%, #1E0942 100%)`,
      alignItems: "center", justifyContent: "flex-end",
    }}>
      <svg viewBox="0 0 200 220" width={size * 200 / 220} height={size} style={{ marginBottom: full ? 360 : 0 }}
        aria-label="presenter placeholder">
        <circle cx="100" cy="62" r="42" fill="rgba(255,255,255,0.16)" />
        <path d="M18 220 C18 150 52 118 100 118 C148 118 182 150 182 220 Z" fill="rgba(255,255,255,0.16)" />
      </svg>
      <div style={{
        // above YouTube's bottom overlay (title, captions), so the label stays readable
        position: "absolute", bottom: safe.bottom + 24, left: 0, right: 0, textAlign: "center",
      }}>
        <span style={{
          fontFamily: theme.bodyFont, fontSize: 30, fontWeight: 700, letterSpacing: 2,
          color: "rgba(255,255,255,0.72)", backgroundColor: "rgba(0,0,0,0.22)",
          borderRadius: 999, padding: "8px 26px",
        }}>presenter — sir</span>
      </div>
    </AbsoluteFill>
  );
};
