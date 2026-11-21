import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig, Easing } from "remotion";
import { C, FONT, ease, clamp, shot } from "./design";
import { BrowserFrame, CueLabel, Keyword, Marker, mapBox, Box } from "./common";
import meta from "../public/shots2/s4.json";

/* ===== 넷째 ① · 생각을 정리하고 중재해요 (240프레임) =====
 * 0~4초: 같은 생각(초록 면) → 갈리는 생각(베이지 면) 강조, 두 사람 문장 확대
 * 4~8초: 화면이 녹아서 AI의 제안으로 바뀌고 "모두의 지키고 싶은 것을 담았어요" 강조 */
const W = 1100;
const ASPECT = 1.56; // 보이는 세로 약 530 CSS px
const X = (1920 - W) / 2;
const Y = 300;
const CROP_A = { y0: 75 / 900 };
const CROP_B = { y0: 82 / 900 }; // 'AI의 제안' 제목 위에 여백이 생기게
const m = meta as unknown as Record<string, Record<string, Box>>;
const tm = meta as unknown as Record<string, Box[]>; // 글자 폭에 맞춘 영역(t_*)
const mA = (b: Box) => mapBox(b, W, CROP_A);
const mB = (b: Box) => mapBox(b, W, CROP_B);

/* 서비스 화면의 단계 이름(제목)을 프레임 위에 크게 한 번 더 보여 준다 */
export const StageLabel: React.FC<{ text: string; at: number; opacity: number; blur: number }> = ({ text, at, opacity, blur }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: f - at, fps, config: { damping: 14, stiffness: 110 } });
  return (
    <div style={{ position: "absolute", left: 960, top: 232, transform: `translate(-50%,0) scale(${0.9 + 0.1 * s})`, opacity: Math.min(1, s * 1.4) * opacity, filter: blur > 0.3 ? `blur(${blur}px)` : undefined, background: C.GREEN, color: "#fff", fontFamily: FONT, fontWeight: 800, fontSize: 38, padding: "8px 36px 10px", borderRadius: 50, boxShadow: "0 10px 24px rgba(0,0,0,.18)", whiteSpace: "nowrap" }}>{text}</div>
  );
};

export const S4a: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: f - 14, fps, config: { damping: 18, stiffness: 90 } });
  const p = interpolate(f, [120, 146], [0, 1], { ...clamp, easing: Easing.inOut(Easing.ease) }); // 녹는 전환
  const contentH = W / ASPECT;
  const stm = mA(m.mj.up3);
  return (
    <AbsoluteFill style={{ background: C.DESK }}>
      <CueLabel text="넷째" tx={960} ty={78} />
      <Keyword lines={["생각을 정리하고 중재해요"]} x={960} y={112} size={84} />
      <StageLabel text="생각 확인" at={14} opacity={(1 - p) * 1} blur={p * 14} />
      <StageLabel text="AI의 제안" at={0} opacity={p} blur={(1 - p) * 14} />
      <BrowserFrame src={shot("a04y-think")} x={X} y={Y} width={W} aspect={ASPECT} crop={CROP_A} dy={(1 - enter) * 90}
        opacity={Math.min(1, enter * 1.3) * (1 - p)} blur={p * 18} scale={1 + p * 0.04}
        zoom={{ from: 1, to: 1.12, start: 84, end: 116, ox: 0, oy: 0 }}
        zoomed={<>
          <Marker box={mA(tm.t_same[0])} at={26} />
          <Marker box={mA(tm.t_diff[0])} at={60} />
          <Marker box={mA(m.mj.up0)} at={100} />
          <Marker box={mA(m.sy.up0)} at={112} />
        </>} />
      <BrowserFrame src={shot("a04y-propose")} x={X} y={Y} width={W} aspect={ASPECT} crop={CROP_B}
        opacity={p} blur={(1 - p) * 18} scale={0.97 + 0.03 * p}
        zoomed={<>
          <Marker box={mB(tm.t_cover[0])} at={172} />
          <Marker box={mB({ x: 552, y: 495, w: 376, h: 22 })} at={192} />
          <Marker box={mB({ x: 552, y: 529, w: 430, h: 22 })} at={204} />
        </>} />
    </AbsoluteFill>
  );
};
