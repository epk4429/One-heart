import React from "react";
import { AbsoluteFill, Img, staticFile, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT, ease, clamp, shot } from "./design";
import { BrowserFrame, CueLabel, Keyword, NamePill, Outline, Reveal, Ring, FadeMask, mapBox, Box } from "./common";
import { LENGTHS } from "./timeline";
import s2 from "../public/shots2/s2.json";

/* ===== 오프닝 (60프레임): 로고만 ===== */
export const Opening: React.FC = () => {
  const f = useCurrentFrame();
  const s = interpolate(f, [0, 12], [0.92, 1], { ...clamp, easing: ease }) * interpolate(f, [12, 60], [1, 1.02], clamp);
  const o = interpolate(f, [0, 12], [0, 1], clamp);
  const out = interpolate(f, [48, 60], [0, -140], { ...clamp, easing: ease });
  return (
    <AbsoluteFill style={{ background: C.DESK, alignItems: "center", justifyContent: "center" }}>
      <Img src={staticFile("logo.png")} style={{ height: 130, opacity: o, transform: `translateX(${out}px) scale(${s})` }} />
    </AbsoluteFill>
  );
};

/* ===== 첫째 · 가족방 만들기 (240프레임) ===== */
const FW = 820;
const FA = 1.4; // 화면 가로:세로 비율(표시줄이 없어져 세로를 더 쓴다)
const FY = 310;
const LX = 100;
const RX = 1000;

const LinkChip: React.FC = () => {
  const f = useCurrentFrame();
  const p = interpolate(f, [90, 150], [0, 1], { ...clamp, easing: ease });
  const op = interpolate(f, [90, 100, 142, 152], [0, 1, 1, 0], clamp);
  const pos = (q: number) => ({ x: 800 + q * 470, y: 575 - Math.sin(q * Math.PI) * 90 });
  const c = pos(p);
  return (
    <>
      {Array.from({ length: 9 }).map((_, i) => {
        const q = p - (i + 1) * 0.06;
        if (q <= 0) return null;
        const d = pos(q);
        return <div key={i} style={{ position: "absolute", left: d.x - 5, top: d.y - 5, width: 10, height: 10, borderRadius: 5, background: C.GREEN, opacity: op * (0.5 - i * 0.05) }} />;
      })}
      <div style={{ position: "absolute", left: c.x, top: c.y, transform: "translate(-50%,-50%)", opacity: op, background: C.GREEN, color: "#fff", fontFamily: FONT, fontWeight: 700, fontSize: 30, padding: "12px 30px 14px", borderRadius: 50, display: "flex", alignItems: "center", gap: 12, boxShadow: "0 12px 28px rgba(0,0,0,.25)", whiteSpace: "nowrap" }}>
        <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" />
          <path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />
        </svg>
        초대 링크
      </div>
    </>
  );
};

export const S1: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const left = spring({ frame: f - 20, fps, config: { damping: 18, stiffness: 90 } });
  const right = spring({ frame: f - 150, fps, config: { damping: 16, stiffness: 100 } });
  const badge = spring({ frame: f - 168, fps, config: { damping: 11, stiffness: 130 } });
  return (
    <AbsoluteFill style={{ background: C.DESK }}>
      <CueLabel text="첫째" tx={960} ty={78} />
      <Keyword lines={["가족방 만들기"]} x={960} y={112} size={84} />
      <NamePill name="민준" color={C.MINJUN} x={LX + FW / 2} y={FY - 82} appear={24} pulseAt={176} />
      <NamePill name="서연" color={C.SEOYEON} x={RX + FW / 2} y={FY - 82} appear={154} pulseAt={176} />
      <BrowserFrame src={shot("a01b-family-members")} x={LX} y={FY} width={FW} aspect={FA} crop={{ y0: 0.14 }} dy={(1 - left) * 90} opacity={Math.min(1, left * 1.3)}
        zoom={{ from: 1, to: 1.1, start: 40, end: 110, ox: 30, oy: 62 }} />
      <LinkChip />
      <BrowserFrame src={shot("a01b-family-members")} x={RX} y={FY} width={FW} aspect={FA} crop={{ y0: 0.14 }} scale={0.9 + 0.1 * right} opacity={Math.min(1, right * 1.3)}
        zoom={{ from: 1, to: 1.1, start: 160, end: 230, ox: 30, oy: 62 }}>
        <div style={{ position: "absolute", right: 22, top: 22, transform: `scale(${badge})`, opacity: Math.min(1, badge * 1.4), background: C.GREEN, color: "#fff", fontFamily: FONT, fontWeight: 800, fontSize: 34, padding: "10px 28px 12px", borderRadius: 40, boxShadow: "0 10px 24px rgba(0,0,0,.25)" }}>참여 ✓</div>
      </BrowserFrame>
    </AbsoluteFill>
  );
};

/* ===== 둘째 · 자산과 목표 입력 (360프레임) ===== */
const S2W = 1000;
const S2A = 1.4;
const S2X = 460;
const S2Y = 300;
const CROP_A = { y0: 100 / 900 }; // 금융정보 줄 화면
const CROP_B = { y0: 80 / 900 }; // 카테고리 + 목표 금액 화면
const bA = s2["a02d-fin"] as Record<string, Box>;
const bB = s2["a02e-cat-goal"] as Record<string, Box>;

const MethodChips: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: f - 8, fps, config: { damping: 13, stiffness: 110 } });
  const out = interpolate(f, [142, 156], [1, 0], clamp);
  const base: React.CSSProperties = { fontFamily: FONT, fontWeight: 700, fontSize: 24, padding: "7px 24px 9px", borderRadius: 40, whiteSpace: "nowrap", background: "transparent", color: "#4D5953", border: "2px solid #B9C2BC" };
  return (
    <div style={{ position: "absolute", left: 960, top: 240, transform: `translate(-50%,0) scale(${0.9 + 0.1 * s})`, opacity: Math.min(1, s * 1.4) * out, display: "flex", gap: 14 }}>
      <div style={base}>직접 기입</div>
      <div style={base}>마이데이터 연동</div>
    </div>
  );
};

export const S2: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: f - 14, fps, config: { damping: 18, stiffness: 90 } });
  const fadeB = interpolate(f, [150, 168], [0, 1], { ...clamp, easing: ease });
  const mA = (b: Box) => mapBox(b, S2W, CROP_A);
  const mB = (b: Box) => mapBox(b, S2W, CROP_B);
  const cat = mB(bB.cat);
  const amt = mB(bB.amt0);
  const contentH = S2W / S2A;
  return (
    <AbsoluteFill style={{ background: C.DESK }}>
      <CueLabel text="둘째" tx={960} ty={78} />
      <Keyword lines={["자산과 목표 입력"]} x={960} y={112} size={84} />
      <MethodChips />
      <BrowserFrame src={shot("a02d-fin")} x={S2X} y={S2Y} width={S2W} aspect={S2A} crop={CROP_A} dy={(1 - enter) * 90} opacity={Math.min(1, enter * 1.3)}
        zoomed={<>
          <Reveal box={mA(bA.income1)} start={40} end={72} />
          <Reveal box={mA(bA.dep1)} start={72} end={104} />
          <Reveal box={mA(bA.loan1)} start={104} end={136} />
        </>} />
      <BrowserFrame src={shot("a02e-cat-goal")} x={S2X} y={S2Y} width={S2W} aspect={S2A} crop={CROP_B} dy={(1 - enter) * 90} opacity={Math.min(1, enter * 1.3) * fadeB}
        zoom={{ from: 1, to: 1.3, start: 255, end: 292, ox: 0, oy: ((amt.y + amt.h / 2) / contentH) * 100 }}
        zoomed={<>
          <Outline box={cat} at={172} />
          <Ring cx={cat.x + cat.w / 2} cy={cat.y + cat.h / 2} at={176} />
          <Reveal box={mB(bB.amt0)} start={292} end={330} />
          <Outline box={amt} at={290} />
        </>} />
    </AbsoluteFill>
  );
};

export const LEN = LENGTHS;
