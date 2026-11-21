// 디자인 규칙(디자인규칙.md)과 1:1
import { useEffect, useState } from "react";
import { delayRender, continueRender, Easing } from "remotion";

export const C = {
  GREEN: "#2F5D4A",
  GREEN_D: "#234838",
  DESK: "#EFEEE7",
  PAPER: "#FCFBF7",
  INK: "#1F2A24",
  MINJUN: "#4F7A93",
  SEOYEON: "#B0674A",
};
export const FONT = `"Pretendard", "Malgun Gothic", sans-serif`;
export const ease = Easing.bezier(0.22, 1, 0.36, 1);
export const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
export const SPRING = { damping: 18, stiffness: 90 };
export const shot = (name: string) => `shots2/${name}.png`;

export const useFont = () => {
  const [h] = useState(() => delayRender("font"));
  useEffect(() => {
    const l = document.createElement("link");
    l.rel = "stylesheet";
    l.href = "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css";
    l.onload = () => Promise.all([400, 700, 800].map((w) => document.fonts.load(`${w} 40px Pretendard`))).then(() => continueRender(h));
    l.onerror = () => continueRender(h);
    document.head.appendChild(l);
  }, [h]);
};
