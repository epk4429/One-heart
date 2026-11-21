import React from "react";
import { Img, staticFile, interpolate, spring, useCurrentFrame, useVideoConfig, Easing } from "remotion";
import { C, FONT, ease, clamp } from "./design";

/* ---------- 브라우저 창 프레임 ----------
 * 서비스 화면은 왼쪽 목차·위쪽 헤더를 잘라내고 '종이' 영역만 보여 준다(디자인규칙.md).
 * crop: 원본(1440×900 캡처) 가로 x0~x1 비율, 세로 시작 y0 비율. 보이는 세로 길이는 프레임 비율로 정해진다. */
export const PAPER_X0 = 0.299;
export const PAPER_X1 = 0.873;
export const frameHeight = (width: number, aspect = 1.6) => 44 + width / aspect;

export type Box = { x: number; y: number; w: number; h: number };
// 캡처 화면(1440×900 CSS px)의 좌표를 프레임 안 화면 좌표로 바꾼다(shots.json·s2.json의 좌표용)
export const mapBox = (b: Box, width: number, crop: { x0?: number; x1?: number; y0: number }): Box => {
  const x0 = crop.x0 ?? PAPER_X0;
  const x1 = crop.x1 ?? PAPER_X1;
  const k = width / (x1 - x0) / 1440;
  return { x: (b.x - x0 * 1440) * k, y: (b.y - crop.y0 * 900) * k, w: b.w * k, h: b.h * k };
};

/* 강조 링: 좌표 중심에서 한 번 퍼진다 */
export const Ring: React.FC<{ cx: number; cy: number; at: number }> = ({ cx, cy, at }) => {
  const f = useCurrentFrame();
  const t = f - at;
  if (t < 0 || t > 26) return null;
  const grow = interpolate(t, [0, 26], [0.4, 1.7], { ...clamp, easing: ease });
  const op = interpolate(t, [0, 4, 26], [0, 0.9, 0], clamp);
  return (
    <>
      <div style={{ position: "absolute", left: cx - 40, top: cy - 40, width: 80, height: 80, borderRadius: 40, background: "rgba(255,255,255,.5)", border: "4px solid rgba(47,93,74,.95)", transform: `scale(${grow})`, opacity: op }} />
      <div style={{ position: "absolute", left: cx - 10, top: cy - 10, width: 20, height: 20, borderRadius: 10, background: C.GREEN, opacity: op }} />
    </>
  );
};

/* 강조 테두리: 상자 둘레에 숲색 선이 나타난다 */
export const Outline: React.FC<{ box: Box; at: number; pad?: number; until?: number }> = ({ box, at, pad = 8, until }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [at, at + 12], [0, 1], { ...clamp, easing: ease }) * (until === undefined ? 1 : 1 - interpolate(f, [until, until + 10], [0, 1], clamp));
  return <div style={{ position: "absolute", left: box.x - pad, top: box.y - pad, width: box.w + pad * 2, height: box.h + pad * 2, border: `4px solid ${C.GREEN}`, borderRadius: 10, opacity: o, boxShadow: "0 0 0 6px rgba(47,93,74,.15)" }} />;
};

/* 형광펜 표시: 글자 폭에 맞춰 왼쪽에서 오른쪽으로 그어지고 밑줄이 따라온다. 강조 없이 시작해서 생기는 방식 */
export const Marker: React.FC<{ box: Box; at: number; dur?: number; until?: number; padX?: number; padY?: number; fill?: string; line?: string }> = ({ box, at, dur = 16, until, padX = 6, padY = 3, fill = "rgba(47,93,74,.24)", line = C.GREEN }) => {
  const f = useCurrentFrame();
  const p = interpolate(f, [at, at + dur], [0, 1], { ...clamp, easing: ease });
  const fade = until === undefined ? 1 : 1 - interpolate(f, [until, until + 10], [0, 1], clamp);
  if (p <= 0 || fade <= 0) return null;
  const x = box.x - padX;
  const y = box.y - padY;
  const w = (box.w + padX * 2) * p;
  const h = box.h + padY * 2;
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, height: h, borderRadius: 5, background: fill, borderBottom: `4px solid ${line}`, opacity: fade, overflow: "hidden" }} />
  );
};

/* 가림막(서서히 사라짐): 말풍선 같은 덩어리가 차례로 나타나게 한다 */
export const FadeMask: React.FC<{ box: Box; at: number; color?: string }> = ({ box, at, color = "#FFFFFF" }) => {
  const f = useCurrentFrame();
  const o = 1 - interpolate(f, [at, at + 12], [0, 1], { ...clamp, easing: ease });
  if (o <= 0) return null;
  return <div style={{ position: "absolute", left: box.x, top: box.y, width: box.w, height: box.h, background: color, opacity: o }} />;
};

/* 가림막: 입력 줄을 종이색으로 덮었다가 왼쪽에서 오른쪽으로 걷어 내 '입력되는' 모습을 만든다 */
export const Reveal: React.FC<{ box: Box; start: number; end: number; pad?: number }> = ({ box, start, end, pad = 6 }) => {
  const f = useCurrentFrame();
  const p = interpolate(f, [start, end], [0, 1], { ...clamp, easing: ease });
  if (p >= 1) return null;
  const x = box.x - pad;
  const w = box.w + pad * 2;
  return <div style={{ position: "absolute", left: x + w * p, top: box.y - pad, width: w * (1 - p), height: box.h + pad * 2, background: "#FFFFFF" }} />;
};

export const BrowserFrame: React.FC<{
  src: string; x: number; y: number; width: number; aspect?: number; imgAspect?: number;
  crop?: { x0?: number; x1?: number; y0: number };
  opacity?: number; scale?: number; dy?: number; blur?: number; shadow?: boolean;
  zoom?: { from: number; to: number; start: number; end: number; ox: number; oy: number };
  children?: React.ReactNode; // 프레임 안쪽에 얹는 요소(확대되지 않음). 좌표는 보이는 화면 기준
  zoomed?: React.ReactNode; // 화면과 같이 확대되는 요소(강조 링·가림막 등). 좌표는 mapBox로 계산
}> = ({ src, x, y, width, aspect = 1.6, imgAspect = 1.6, crop = { y0: 0.1 }, opacity = 1, scale = 1, dy = 0, blur = 0, shadow = true, zoom, children, zoomed }) => {
  const f = useCurrentFrame();
  const h = frameHeight(width, aspect);
  const ch = h - 44;
  const z = zoom ? interpolate(f, [zoom.start, zoom.end], [zoom.from, zoom.to], { ...clamp, easing: ease }) : 1;
  const x0 = crop.x0 ?? PAPER_X0;
  const x1 = crop.x1 ?? PAPER_X1;
  const imgW = width / (x1 - x0);
  const imgH = imgW / imgAspect;
  return (
    <div style={{
      position: "absolute", left: x, top: y + dy, width, height: h, borderRadius: 20, background: "#fff", overflow: "hidden",
      boxShadow: shadow ? "0 40px 90px rgba(0,0,0,.28), 0 6px 18px rgba(0,0,0,.12)" : undefined, opacity, transform: `scale(${scale})`, transformOrigin: "50% 50%", filter: blur > 0 ? `blur(${blur}px)` : undefined,
    }}>
      <div style={{ height: 44, background: "#E9E8E1", display: "flex", alignItems: "center", gap: 9, paddingLeft: 18 }}>
        {["#E0705F", "#E5B84B", "#6FB36B"].map((c) => <span key={c} style={{ width: 13, height: 13, borderRadius: 7, background: c }} />)}
        <span style={{ marginLeft: 18, fontFamily: FONT, fontSize: 15, color: "#848E88" }}>one-heart</span>
      </div>
      <div style={{ position: "relative", width, height: ch, overflow: "hidden", background: C.PAPER }}>
        <div style={{ position: "absolute", inset: 0, transform: `scale(${z})`, transformOrigin: zoom ? `${zoom.ox}% ${zoom.oy}%` : "50% 50%" }}>
          <Img src={staticFile(src)} style={{ position: "absolute", left: -x0 * imgW, top: -crop.y0 * imgH, width: imgW, height: imgH }} />
          {zoomed}
        </div>
        {children}
      </div>
    </div>
  );
};

/* ---------- 스크롤 프레임: 긴 화면(채팅창 전체 등)을 브라우저 창 안에서 위에서 아래로 스크롤한다 ----------
 * imgCssW/imgCssH: 캡처한 긴 이미지의 CSS 크기(2배 해상도 이미지라면 픽셀의 절반).
 * scroll: 프레임 f 구간에서 0 → 끝까지 부드럽게 내려간다. children은 스크롤되는 화면 위에 얹는다(좌표 = CSS px × k, k = width / imgCssW). */
export const ScrollFrame: React.FC<{
  src: string; x: number; y: number; width: number; contentH: number; imgCssW: number; imgCssH: number;
  scroll: { start: number; end: number };
  endY?: number; // 스크롤이 멈출 위치(캡처 이미지의 CSS px). 없으면 맨 아래까지
  startY?: number; // 스크롤이 시작하는 위치(CSS px). 없으면 맨 위
  opacity?: number; scale?: number; dy?: number;
  children?: (k: number) => React.ReactNode;
}> = ({ src, x, y, width, contentH, imgCssW, imgCssH, scroll, endY, startY = 0, opacity = 1, scale = 1, dy = 0, children }) => {
  const f = useCurrentFrame();
  const k = width / imgCssW;
  const dispH = imgCssH * k;
  const maxScroll = Math.max(0, dispH - contentH);
  const target = endY === undefined ? maxScroll : Math.min(maxScroll, endY * k);
  const sy = interpolate(f, [scroll.start, scroll.end], [startY * k, target], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  return (
    <div style={{
      position: "absolute", left: x, top: y + dy, width, height: contentH + 44, borderRadius: 20, background: "#fff", overflow: "hidden",
      boxShadow: "0 40px 90px rgba(0,0,0,.28), 0 6px 18px rgba(0,0,0,.12)", opacity, transform: `scale(${scale})`, transformOrigin: "50% 50%",
    }}>
      <div style={{ height: 44, background: "#E9E8E1", display: "flex", alignItems: "center", gap: 9, paddingLeft: 18 }}>
        {["#E0705F", "#E5B84B", "#6FB36B"].map((c) => <span key={c} style={{ width: 13, height: 13, borderRadius: 7, background: c }} />)}
        <span style={{ marginLeft: 18, fontFamily: FONT, fontSize: 15, color: "#848E88" }}>one-heart</span>
      </div>
      <div style={{ position: "relative", width, height: contentH, overflow: "hidden", background: C.PAPER }}>
        <div style={{ position: "absolute", left: 0, top: 0, width, height: dispH, transform: `translateY(${-sy}px)` }}>
          <Img src={staticFile(src)} style={{ position: "absolute", left: 0, top: 0, width, height: dispH }} />
          {children?.(k)}
        </div>
      </div>
    </div>
  );
};

/* ---------- 큐 라벨: 장면 시작 때 크게 떴다가 꼬리표로 줄어든다 ---------- */
export const CueLabel: React.FC<{ text: string; dark?: boolean; tx: number; ty: number; pop?: boolean }> = ({ text, dark, tx, ty, pop = true }) => {
  const f = useCurrentFrame();
  // pop=false: 같은 단계가 이어지는 장면(넷째 ②)에서는 크게 뜨지 않고 꼬리표로 그대로 둔다
  const t = pop ? interpolate(f, [14, 36], [0, 1], { ...clamp, easing: ease }) : 1;
  const op = pop ? interpolate(f, [0, 8], [0, 1], clamp) : 1;
  const size = interpolate(t, [0, 1], [150, 28]);
  const left = interpolate(t, [0, 1], [960, tx]);
  const top = interpolate(t, [0, 1], [540, ty]);
  return (
    <div style={{ position: "absolute", left, top, transform: "translate(-50%,-50%)", fontFamily: FONT, fontWeight: 800, fontSize: size, letterSpacing: t > 0.5 ? 1 : -3, color: dark ? "#BFE0CE" : C.GREEN, opacity: op, whiteSpace: "nowrap" }}>{text}</div>
  );
};

/* ---------- 키워드(큰 자막) ---------- */
export const Keyword: React.FC<{ lines: string[]; x: number; y: number; size?: number; align?: "center" | "left"; dark?: boolean; delay?: number }> = ({ lines, x, y, size = 80, align = "center", dark, delay = 8 }) => {
  const f = useCurrentFrame();
  return (
    <div style={{ position: "absolute", left: align === "center" ? x - 900 : x, top: y, width: 1800, textAlign: align }}>
      {lines.map((l, i) => {
        const a = delay + i * 5;
        const o = interpolate(f, [a, a + 16], [0, 1], { ...clamp, easing: ease });
        const dy = interpolate(f, [a, a + 16], [36, 0], { ...clamp, easing: ease });
        return <div key={i} style={{ fontFamily: FONT, fontWeight: 800, fontSize: size, lineHeight: 1.18, letterSpacing: -2.5, color: dark ? "#fff" : C.INK, opacity: o, transform: `translateY(${dy}px)` }}>{l}</div>;
      })}
    </div>
  );
};

/* ---------- 이름 라벨(알약) ---------- */
export const NamePill: React.FC<{ name: string; color: string; x: number; y: number; appear: number; pulseAt?: number }> = ({ name, color, x, y, appear, pulseAt }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: f - appear, fps, config: { damping: 12, stiffness: 120 } });
  let pulse = 1;
  if (pulseAt !== undefined) pulse = 1 + 0.12 * Math.sin(interpolate(f, [pulseAt, pulseAt + 18], [0, Math.PI], clamp));
  return (
    <div style={{ position: "absolute", left: x, top: y, transform: `translate(-50%,0) scale(${s * pulse})`, opacity: Math.min(1, s * 1.4), background: color, color: "#fff", fontFamily: FONT, fontWeight: 800, fontSize: 48, padding: "10px 40px 12px", borderRadius: 60, boxShadow: "0 10px 24px rgba(0,0,0,.16)", whiteSpace: "nowrap" }}>{name}</div>
  );
};

/* ---------- 장면 전환: 짙은 숲색 면이 왼쪽에서 오른쪽으로 지나간다(가운데에서 완전히 덮음) ---------- */
export const Wipe: React.FC<{ at: number }> = ({ at }) => {
  const f = useCurrentFrame();
  if (f < at - 8 || f > at + 8) return null;
  const left = interpolate(f, [at - 8, at + 8], [-100, 100], { easing: ease });
  return <div style={{ position: "absolute", top: 0, left: `${left}%`, width: "100%", height: "100%", background: C.GREEN_D }} />;
};
