import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig, Easing } from "remotion";
import { C, FONT, ease, clamp, shot } from "./design";
import { BrowserFrame, CueLabel, Keyword, Marker, mapBox, Box } from "./common";
import { StageLabel } from "./s4";
import meta from "../public/shots2/s5.json";

/* ===== 넷째 ② · 세 가지 시나리오를 계산해요 (300프레임) =====
 * 0~3초: 자산·소득·목표 → 계산엔진 → 시나리오 A·B·C (도식)
 * 3~7초: 미래 계산 화면에서 A·B·C가 차례로 강조되고 목표 달성 기간이 올라가듯 나타남
 * 7~10초: 그래프 화면(가만히) */
const W = 1100;
const ASPECT = 1.56;
const X = (1920 - W) / 2;
const Y = 300;
const CROP_T = { y0: 75 / 900 };
const CROP_G = { y0: 333 / 900 };
const K = W / (0.574 * 1440);
const mT = (b: Box) => mapBox(b, W, CROP_T);
const md = meta as unknown as { names: Box[][]; years: Box[][] };
const YEARS = [3.4, 4.0, 4.9];
const ROW_BG = ["#FCFBF7", "#E6EFE8", "#FCFBF7"];

/* ---------- 도식 ---------- */
const INPUTS = ["자산", "소득", "목표"];
const OUTS = ["A", "B", "C"];
const IY = [400, 540, 680];

const Diagram: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const out = interpolate(f, [88, 108], [1, 0], { ...clamp, easing: ease });
  const eng = spring({ frame: f - 12, fps, config: { damping: 13, stiffness: 110 } });
  const pulse = (at: number) => Math.max(0, Math.sin(interpolate(f, [at, at + 12], [0, Math.PI], clamp)));
  const pulses = pulse(36) + pulse(42) + pulse(48);
  const chip = (label: string, i: number) => {
    const t0 = 6 + i * 6;
    const s = spring({ frame: f - t0, fps, config: { damping: 14, stiffness: 120 } });
    return (
      <div key={label} style={{ position: "absolute", left: 250, top: IY[i] - 36, opacity: Math.min(1, s * 1.4), transform: `scale(${s})`, transformOrigin: "left center", background: "#fff", border: "2px solid #B9C2BC", borderRadius: 60, padding: "8px 44px 10px", fontFamily: FONT, fontWeight: 800, fontSize: 46, color: C.INK, boxShadow: "0 10px 24px rgba(0,0,0,.10)" }}>{label}</div>
    );
  };
  const card = (label: string, i: number) => {
    const t0 = 50 + i * 6;
    const s = spring({ frame: f - t0, fps, config: { damping: 15, stiffness: 100 } });
    const x = interpolate(s, [0, 1], [1100, 1330]);
    return (
      <div key={label} style={{ position: "absolute", left: x, top: IY[i] - 40, opacity: Math.min(1, s * 1.4), display: "flex", alignItems: "center", gap: 16, background: "#fff", border: `2px solid ${C.GREEN}`, borderRadius: 24, padding: "10px 34px 12px 14px", boxShadow: "0 12px 28px rgba(0,0,0,.14)" }}>
        <div style={{ width: 56, height: 56, borderRadius: 28, background: C.GREEN, color: "#fff", fontFamily: FONT, fontWeight: 800, fontSize: 36, display: "flex", alignItems: "center", justifyContent: "center" }}>{label}</div>
        <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: 40, color: C.INK, whiteSpace: "nowrap" }}>시나리오 {label}</div>
      </div>
    );
  };
  const linePath = (i: number) => `M 1140 540 C 1230 540, 1240 ${IY[i]}, 1325 ${IY[i]}`;
  const inPath = (i: number) => `M 470 ${IY[i]} C 620 ${IY[i]}, 650 540, 765 540`;
  return (
    <AbsoluteFill style={{ opacity: out, transform: `scale(${0.96 + 0.04 * out})` }}>
      <svg width="1920" height="1080" style={{ position: "absolute", left: 0, top: 0 }}>
        {INPUTS.map((_, i) => {
          const p = interpolate(f, [14 + i * 6, 34 + i * 6], [0, 1], { ...clamp, easing: ease });
          return <path key={"i" + i} d={inPath(i)} fill="none" stroke={C.GREEN} strokeWidth="5" strokeLinecap="round" strokeDasharray="420" strokeDashoffset={420 * (1 - p)} opacity={0.6} />;
        })}
        {OUTS.map((_, i) => {
          const p = interpolate(f, [46 + i * 6, 66 + i * 6], [0, 1], { ...clamp, easing: ease });
          return <path key={i} d={linePath(i)} fill="none" stroke={C.GREEN} strokeWidth="5" strokeLinecap="round" strokeDasharray="420" strokeDashoffset={420 * (1 - p)} opacity={0.6} />;
        })}
      </svg>
      {INPUTS.map(chip)}
      {/* 이 밖에도 여러 조건이 있다는 표시(세로 점) */}
      {[0, 1, 2].map((k) => {
        const s = spring({ frame: f - (26 + k * 4), fps, config: { damping: 12, stiffness: 140 } });
        return <div key={"d" + k} style={{ position: "absolute", left: 340 - 7, top: 752 + k * 26 - 7, width: 14, height: 14, borderRadius: 7, background: C.GREEN, opacity: 0.6 * Math.min(1, s * 1.4), transform: `scale(${s})` }} />;
      })}
      <div style={{ position: "absolute", left: 960 - 190, top: 540 - 120, width: 380, height: 240, transform: `scale(${(0.8 + 0.2 * eng) * (1 + pulses * 0.04)})`, opacity: Math.min(1, eng * 1.4), background: C.GREEN, borderRadius: 36, boxShadow: "0 24px 60px rgba(0,0,0,.28)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 6 }}>
        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ transform: `rotate(${f * 3}deg)` }}>
          <circle cx="12" cy="12" r="3.2" />
          <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1" />
        </svg>
        <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: 60, color: "#fff", letterSpacing: -1 }}>계산엔진</div>
      </div>
      {OUTS.map(card)}
    </AbsoluteFill>
  );
};

/* ---------- 숫자가 올라가는 표시 ---------- */
const CountUp: React.FC<{ box: Box; value: number; start: number; bg: string; color: string }> = ({ box, value, start, bg, color }) => {
  const f = useCurrentFrame();
  const p = interpolate(f, [start, start + 28], [0, 1], { ...clamp, easing: ease });
  const padX = 8;
  const padY = 5;
  return (
    <div style={{ position: "absolute", left: box.x - padX, top: box.y - padY, width: box.w + padX * 2, height: box.h + padY * 2, background: bg, display: "flex", alignItems: "center", justifyContent: "flex-end", paddingRight: padX }}>
      {f >= start && (
        <span style={{ fontFamily: FONT, fontWeight: 800, fontSize: box.h * 0.86, color, fontVariantNumeric: "tabular-nums", letterSpacing: -0.5, whiteSpace: "nowrap" }}>약 {(value * p).toFixed(1)}년</span>
      )}
    </div>
  );
};

/* 그래프 구간: 방법 A·B·C를 차례로 눌러 보며 시나리오마다 다른 그래프가 나온다는 것을 보여 주는 선택 칩 */
const TABS = ["A  목표 먼저", "B  함께 챙기기", "C  지금 여유 먼저"];
const SWITCH = [214, 244, 274];
const ScenarioTabs: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const show = spring({ frame: f - 204, fps, config: { damping: 14, stiffness: 110 } });
  const idx = f < SWITCH[1] ? 0 : f < SWITCH[2] ? 1 : 2;
  return (
    <div style={{ position: "absolute", left: 960, top: 238, transform: `translate(-50%,0) scale(${0.92 + 0.08 * show})`, opacity: Math.min(1, show * 1.4), display: "flex", gap: 14 }}>
      {TABS.map((t, i) => {
        const on = i === idx;
        const pop = on ? 1 + 0.08 * Math.max(0, Math.sin(interpolate(f, [SWITCH[i], SWITCH[i] + 14], [0, Math.PI], clamp))) : 1;
        return (
          <div key={t} style={{ fontFamily: FONT, fontWeight: 800, fontSize: 30, whiteSpace: "pre", padding: "8px 30px 10px", borderRadius: 44, transform: `scale(${pop})`, background: on ? C.GREEN : "transparent", color: on ? "#fff" : "#4D5953", border: `2px solid ${on ? C.GREEN : "#B9C2BC"}`, boxShadow: on ? "0 8px 20px rgba(0,0,0,.18)" : undefined }}>{t}</div>
        );
      })}
    </div>
  );
};

export const S4b: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const inn = interpolate(f, [92, 114], [0, 1], { ...clamp, easing: ease });
  const toChart = interpolate(f, [210, 232], [0, 1], { ...clamp, easing: Easing.inOut(Easing.ease) });
  const pill = spring({ frame: f - 100, fps, config: { damping: 14, stiffness: 110 } });
  const starts = [116, 140, 164];
  return (
    <AbsoluteFill style={{ background: C.DESK }}>
      <CueLabel text="넷째" tx={960} ty={78} pop={false} />
      <Keyword lines={["세 가지 시나리오를 계산해요"]} x={960} y={112} size={84} delay={0} />
      <Diagram />
      <StageLabel text="미래 계산" at={100} opacity={1 - interpolate(f, [198, 212], [0, 1], clamp)} blur={0} />
      <ScenarioTabs />
      <BrowserFrame src={shot("a05y-calc")} x={X} y={Y} width={W} aspect={ASPECT} crop={CROP_T}
        opacity={inn} scale={0.96 + 0.04 * inn} dy={(1 - inn) * 40}
        zoomed={<>
          {[0, 1, 2].map((i) => {
            const n = md.names[i][0];
            const y = md.years[i][0];
            return (
              <React.Fragment key={i}>
                <CountUp box={mT(y)} value={YEARS[i]} start={starts[i]} bg={ROW_BG[i]} color={i === 1 ? C.GREEN : C.INK} />
                <Marker box={mT({ x: n.x - 24, y: n.y, w: n.w + 24, h: n.h })} at={starts[i] - 4} />
              </React.Fragment>
            );
          })}
        </>} />
      <BrowserFrame src={shot("a05y-chart-A")} x={X} y={Y} width={W} aspect={ASPECT} crop={CROP_G}
        opacity={toChart} scale={0.98 + 0.02 * toChart} />
      <BrowserFrame src={shot("a05y-chart-B")} x={X} y={Y} width={W} aspect={ASPECT} crop={CROP_G} shadow={false}
        opacity={interpolate(f, [SWITCH[1], SWITCH[1] + 12], [0, 1], clamp)} />
      <BrowserFrame src={shot("a05y-chart-C")} x={X} y={Y} width={W} aspect={ASPECT} crop={CROP_G} shadow={false}
        opacity={interpolate(f, [SWITCH[2], SWITCH[2] + 12], [0, 1], clamp)} />
    </AbsoluteFill>
  );
};
