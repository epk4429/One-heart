import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT, ease, clamp, shot } from "./design";
import { BrowserFrame, CueLabel, Keyword, Marker, Outline, Ring, mapBox, Box } from "./common";
import { StageLabel } from "./s4";
import meta from "../public/shots2/s7.json";

/* ===== 다섯째에서 이어지는 장면: 합의될 때까지 다시 조율 (240프레임) =====
 * 새 큐 라벨·키워드 없이 다섯째 것을 그대로 쓴다(넷째 ①②와 같은 방식, ✅ 2026-11-22 형님 지시)
 * 0~3.5초: 서로 다른 선택(민준 A, 서연 C) 화면 → '공동 목표 설정으로 돌아가기' 버튼을 누르는 표현까지
 * 3.5~8초: 순환 화살표 3칸(합의안 선택 → 공동 목표 수정 → 미래 재계산 → 합의안 선택), 한 바퀴만 천천히 → "합의안 채택 ✓"
 * (✅ 2026-11-22 형님 지시: 첫 화면에서 서로 다른 선택 강조, 순환 한 바퀴·느리게, 가운데 문구 '합의안 채택')
 * (수정 제안·미래 계산 화면은 뺌) */
const W = 1100;
const ASPECT = 1.56;
const X = (1920 - W) / 2;
const Y = 300;
const CROP_A = { y0: 80 / 900 };
const mA = (b: Box) => mapBox(b, W, CROP_A);
const m = meta as unknown as { diverge: { none: Box[]; back: Box } };

// 표에서 '괜찮아요'를 고른 두 칸(캡처 화면 CSS px): 민준 → A, 서연 → C
const OK_MINJUN: Box = { x: 645, y: 132, w: 61, h: 17 };
const OK_SEOYEON: Box = { x: 915, y: 225, w: 61, h: 17 };

const DifferBadge: React.FC<{ at: number }> = ({ at }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: f - at, fps, config: { damping: 12, stiffness: 120 } });
  return (
    <div style={{ position: "absolute", left: 1186, top: 465, transform: `scale(${s})`, transformOrigin: "left center", opacity: Math.min(1, s * 1.4), background: C.GREEN, color: "#fff", fontFamily: FONT, fontWeight: 800, fontSize: 26, padding: "6px 20px 8px", borderRadius: 40, boxShadow: "0 8px 18px rgba(0,0,0,.22)", whiteSpace: "nowrap" }}>≠ 서로 다른 선택</div>
  );
};

/* ---------- 순환 화살표 도식(3칸) ---------- */
const CX = 960;
const CY = 640;
const R = 290;
const NODES = ["합의안 선택", "공동 목표 수정", "미래 재계산"];
const ang = (i: number) => (-90 + i * 120) * (Math.PI / 180);

const Cycle: React.FC<{ t0: number }> = ({ t0 }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const inn = interpolate(f, [t0, t0 + 14], [0, 1], { ...clamp, easing: ease });
  // 한 바퀴만, 천천히: 원이 그려지는 동안 칸이 20프레임 간격으로 차례로 켜지고 계속 켜진 채 남는다
  const draw = interpolate(f, [t0 + 4, t0 + 60], [0, 1], { ...clamp, easing: ease });
  const done = spring({ frame: f - (t0 + 88), fps, config: { damping: 11, stiffness: 120 } });
  const circ = 2 * Math.PI * R;
  const lit0 = t0 + 22;
  const centerOut = interpolate(f, [t0 + 80, t0 + 90], [1, 0], clamp);
  return (
    <AbsoluteFill style={{ opacity: inn }}>
      <svg width="1920" height="1080" style={{ position: "absolute", left: 0, top: 0 }}>
        <circle cx={CX} cy={CY} r={R} fill="none" stroke={C.GREEN} strokeWidth="6" strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={circ * (1 - draw)} opacity={0.55}
          transform={`rotate(-90 ${CX} ${CY})`} />
      </svg>
      {[0, 1, 2].map((i) => {
        const a = ang(i) + Math.PI / 3;
        const px = CX + R * Math.cos(a);
        const py = CY + R * Math.sin(a);
        const show = interpolate(draw, [(i + 0.5) / 3 - 0.05, (i + 0.5) / 3 + 0.05], [0, 1], clamp);
        return <div key={"h" + i} style={{ position: "absolute", left: px - 11, top: py - 14, width: 0, height: 0, borderTop: "14px solid transparent", borderBottom: "14px solid transparent", borderLeft: `22px solid ${C.GREEN}`, opacity: 0.8 * show, transform: `rotate(${(a * 180) / Math.PI + 90}deg)` }} />;
      })}
      {NODES.map((n, i) => {
        const a = ang(i);
        const x = CX + R * Math.cos(a);
        const y = CY + R * Math.sin(a);
        const on = f >= lit0 + i * 20;
        const s = spring({ frame: f - (t0 + 6 + i * 5), fps, config: { damping: 13, stiffness: 120 } });
        return (
          <div key={n} style={{ position: "absolute", left: x, top: y, transform: `translate(-50%,-50%) scale(${s * (on ? 1.08 : 1)})`, opacity: Math.min(1, s * 1.4), background: on ? C.GREEN : "#fff", color: on ? "#fff" : C.INK, border: `3px solid ${on ? C.GREEN : "#B9C2BC"}`, borderRadius: 60, padding: "10px 40px 12px", fontFamily: FONT, fontWeight: 800, fontSize: 40, whiteSpace: "nowrap", boxShadow: on ? "0 12px 28px rgba(0,0,0,.22)" : "0 8px 20px rgba(0,0,0,.10)" }}>{n}</div>
        );
      })}
      <div style={{ position: "absolute", left: CX, top: CY, transform: "translate(-50%,-50%)", opacity: centerOut, fontFamily: FONT, fontWeight: 800, fontSize: 44, color: C.GREEN, textAlign: "center", lineHeight: 1.25 }}>합의될 때까지<br />반복해요</div>
      <div style={{ position: "absolute", left: CX, top: CY, transform: `translate(-50%,-50%) scale(${done})`, opacity: Math.min(1, done * 1.4), background: C.GREEN, color: "#fff", fontFamily: FONT, fontWeight: 800, fontSize: 52, padding: "14px 44px 18px", borderRadius: 70, boxShadow: "0 20px 50px rgba(0,0,0,.30)", whiteSpace: "nowrap" }}>합의안 채택 ✓</div>
    </AbsoluteFill>
  );
};

export const S6: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: f - 14, fps, config: { damping: 18, stiffness: 90 } });
  const out = interpolate(f, [100, 116], [1, 0], clamp);
  const none = mA(m.diverge.none[0]);
  const back = mA(m.diverge.back);
  return (
    <AbsoluteFill style={{ background: C.DESK }}>
      <CueLabel text="다섯째" tx={960} ty={78} pop={false} />
      <Keyword lines={["시나리오를 검토하고 선택해요"]} x={960} y={112} size={84} delay={-40} />
      <div style={{ opacity: out }}>
        <StageLabel text="합의안" at={14} opacity={1} blur={0} />
        <BrowserFrame src={shot("a07-diverge")} x={X} y={Y} width={W} aspect={ASPECT} crop={CROP_A} dy={(1 - enter) * 90}
          opacity={Math.min(1, enter * 1.3) * out}
          zoomed={<>
            <Marker box={mA(OK_MINJUN)} at={22} dur={12} fill="rgba(79,122,147,.28)" line={C.MINJUN} />
            <Marker box={mA(OK_SEOYEON)} at={34} dur={12} fill="rgba(176,103,74,.28)" line={C.SEOYEON} />
            <Marker box={none} at={62} />
            <Outline box={back} at={78} pad={6} />
            <Ring cx={back.x + back.w / 2} cy={back.y + back.h / 2} at={86} />
          </>} />
        <DifferBadge at={46} />
      </div>
      <Cycle t0={108} />
    </AbsoluteFill>
  );
};
