import React, { useEffect, useState } from "react";
import {
  AbsoluteFill, Img, Sequence, interpolate, spring, staticFile,
  useCurrentFrame, useVideoConfig, delayRender, continueRender, Easing,
} from "remotion";

/* ---------- 디자인 토큰 (서비스 oneheart.css와 같은 값) ---------- */
const GREEN = "#2F5D4A", GREEN_D = "#234838", PAPER = "#FCFBF7", DESK = "#EFEEE7", INK = "#1F2A24";
const BLUE = "#4F7A98", TERRA = "#B5694A";
const FONT = `"Pretendard", "Malgun Gothic", sans-serif`;

/* ---------- 장면 정의 (프레임, 30fps) ---------- */
type Scene = {
  from: number; dur: number; bg: string; dark: boolean; kicker: string;
  title: string[]; sub?: string; shots: string[]; taps?: { x: number; y: number; at: number }[];
};
const S: Scene[] = [
  { from: 90, dur: 120, bg: GREEN, dark: true, kicker: "01 입력", title: ["우리 가족의 상황과", "목표를 입력해요"], sub: "공개할 정보는 직접 골라요", shots: ["03-story-top", "04-story-done"], taps: [{ x: 0.4, y: 0.6, at: 40 }] },
  { from: 210, dur: 90, bg: DESK, dark: false, kicker: "02 각자의 생각", title: ["각자 AI와", "편하게 이야기해요"], sub: "내가 확인한 요약만 가족에게 공유돼요", shots: ["05-interview-chat", "06-interview-summary"], taps: [{ x: 0.78, y: 0.82, at: 38 }] },
  { from: 300, dur: 150, bg: GREEN, dark: true, kicker: "03 공동 목표", title: ["서로 다른 생각을", "정리하고"], sub: "결정은 가족이 해요", shots: ["07-goal-think", "08-goal-propose"], taps: [{ x: 0.5, y: 0.45, at: 118 }] },
  { from: 450, dur: 150, bg: DESK, dark: false, kicker: "04 미래 계산", title: ["세 가지 방법을", "숫자로 비교해요"], sub: "계산은 계산엔진이 해요", shots: ["12-calc-top", "13-calc-chart"], taps: [{ x: 0.7, y: 0.4, at: 40 }] },
  { from: 600, dur: 120, bg: GREEN, dark: true, kicker: "05 합의", title: ["모두 괜찮은 방법을 고르고", "함께 서명해요"], sub: "투표가 아니라 합의예요", shots: ["15-agree-picked", "18-agree-signed"], taps: [{ x: 0.55, y: 0.5, at: 25 }, { x: 0.5, y: 0.45, at: 80 }] },
  { from: 720, dur: 60, bg: DESK, dark: false, kicker: "06 상품 비교", title: ["목표에 맞는 상품을", "비교해 봐요"], sub: "선택과 가입은 가족이 해요", shots: ["19-products"] },
  { from: 780, dur: 70, bg: GREEN, dark: true, kicker: "07 가족 홈", title: ["함께", "지켜 가요"], sub: "상황이 바뀌면 다시 점검해요", shots: ["20-home"] },
];
export const TOTAL = 900;

/* ---------- 글꼴 ---------- */
const useFont = () => {
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

const ease = Easing.bezier(0.22, 1, 0.36, 1);
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/* ---------- 브라우저 창 프레임 ---------- */
const FW = 1060, FH = 44 + 1060 / 1.6;
const Browser: React.FC<{ shots: string[]; dur: number; taps?: Scene["taps"]; melt?: number }> = ({ shots, dur, taps, melt }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: f, fps, config: { damping: 18, stiffness: 90 } });
  const exit = interpolate(f, [dur - 12, dur], [0, 1], { ...clamp, easing: ease });
  const x = interpolate(enter, [0, 1], [260, 0]) + exit * -120;
  const float = Math.sin(f / 22) * 6;
  // 장면 안의 화면 전환: 마지막 절반에서 두 번째 화면으로 (melt가 있으면 녹아내리듯)
  const t0 = melt ?? Math.floor(dur * 0.45);
  const mixLen = melt ? 26 : 14;
  const p = interpolate(f, [t0, t0 + mixLen], [0, 1], { ...clamp, easing: Easing.inOut(Easing.ease) });
  const imgStyle = (opacity: number, blur: number, scale: number): React.CSSProperties => ({
    position: "absolute", top: 0, left: 0, width: "100%", height: "100%", objectFit: "cover",
    opacity, filter: `blur(${blur}px)`, transform: `scale(${scale})`,
  });
  return (
    <div style={{
      position: "absolute", left: 810, top: (1080 - FH) / 2 + float, width: FW, height: FH, borderRadius: 20,
      background: "#fff", boxShadow: "0 40px 90px rgba(0,0,0,.28), 0 6px 18px rgba(0,0,0,.12)", overflow: "hidden",
      transform: `translateX(${x}px)`, opacity: 1 - exit * 0.6,
    }}>
      <div style={{ height: 44, background: "#E9E8E1", display: "flex", alignItems: "center", gap: 9, paddingLeft: 18 }}>
        {["#E0705F", "#E5B84B", "#6FB36B"].map((c) => <span key={c} style={{ width: 13, height: 13, borderRadius: 7, background: c }} />)}
        <span style={{ marginLeft: 18, fontFamily: FONT, fontSize: 15, color: "#848E88" }}>one-heart</span>
      </div>
      <div style={{ position: "relative", width: FW, height: FH - 44, overflow: "hidden" }}>
        <Img src={staticFile(`shots/${shots[0]}.png`)} style={imgStyle(shots[1] ? 1 - p : 1, melt ? p * 16 : 0, melt ? 1 + p * 0.05 : 1)} />
        {shots[1] && <Img src={staticFile(`shots/${shots[1]}.png`)} style={imgStyle(p, melt ? (1 - p) * 16 : 0, melt ? 0.97 + p * 0.03 : 1)} />}
        {taps?.map((t, i) => <Tap key={i} x={t.x * FW} y={t.y * (FH - 44)} at={t.at} />)}
      </div>
    </div>
  );
};

/* ---------- 탭 효과 ---------- */
const Tap: React.FC<{ x: number; y: number; at: number }> = ({ x, y, at }) => {
  const f = useCurrentFrame();
  const t = f - at;
  if (t < 0 || t > 22) return null;
  const grow = interpolate(t, [0, 22], [0.4, 1.6], { ...clamp, easing: ease });
  const op = interpolate(t, [0, 4, 22], [0, 0.85, 0], clamp);
  return (
    <>
      <div style={{ position: "absolute", left: x - 34, top: y - 34, width: 68, height: 68, borderRadius: 40, background: "rgba(255,255,255,.55)", border: "3px solid rgba(47,93,74,.9)", transform: `scale(${grow})`, opacity: op }} />
      <div style={{ position: "absolute", left: x - 9, top: y - 9, width: 18, height: 18, borderRadius: 9, background: GREEN, opacity: op }} />
    </>
  );
};

/* ---------- 큰 자막(키워드) ---------- */
const Words: React.FC<{ lines: string[]; sub?: string; kicker: string; dark: boolean; dur: number; swap?: { at: number; lines: string[] } }> = ({ lines, sub, kicker, dark, dur, swap }) => {
  const f = useCurrentFrame();
  const col = dark ? "#fff" : INK;
  const accent = dark ? "#BFE0CE" : GREEN;
  const exit = interpolate(f, [dur - 10, dur], [0, 1], { ...clamp, easing: ease });
  const block = (ls: string[], key: string, opacity: number, blur: number, dy: number) => (
    <div key={key} style={{ position: "absolute", left: 0, top: 0, opacity, filter: `blur(${blur}px)`, transform: `translateY(${dy}px)` }}>
      {ls.map((l, i) => {
        const o = interpolate(f, [4 + i * 5, 20 + i * 5], [0, 1], { ...clamp, easing: ease });
        const y = interpolate(f, [4 + i * 5, 20 + i * 5], [40, 0], { ...clamp, easing: ease });
        return <div key={i} style={{ fontFamily: FONT, fontWeight: 800, fontSize: 84, lineHeight: 1.18, letterSpacing: -2.5, color: col, opacity: key === "a" ? o : 1, transform: key === "a" ? `translateY(${y}px)` : undefined, whiteSpace: "nowrap" }}>{l}</div>;
      })}
    </div>
  );
  let a = 1, b = 0;
  if (swap) { b = interpolate(f, [swap.at, swap.at + 22], [0, 1], { ...clamp, easing: Easing.inOut(Easing.ease) }); a = 1 - b; }
  const subO = interpolate(f, [22, 38], [0, 1], { ...clamp, easing: ease });
  return (
    <div style={{ position: "absolute", left: 100, top: 330, width: 700, opacity: 1 - exit, transform: `translateX(${-exit * 60}px)` }}>
      <div style={{ fontFamily: FONT, fontWeight: 700, fontSize: 28, color: accent, letterSpacing: 1, marginBottom: 26, opacity: interpolate(f, [0, 14], [0, 1], clamp) }}>{kicker}</div>
      <div style={{ position: "relative", height: 84 * 1.18 * 2 + 10 }}>
        {block(lines, "a", a, swap ? b * 14 : 0, swap ? -b * 14 : 0)}
        {swap && block(swap.lines, "b", b, (1 - b) * 14, (1 - b) * 14)}
      </div>
      {sub && <div style={{ marginTop: 34, fontFamily: FONT, fontWeight: 400, fontSize: 34, color: dark ? "rgba(255,255,255,.82)" : "#4D5953", opacity: subO }}>{sub}</div>}
    </div>
  );
};

/* ---------- 장면 하나 ---------- */
const SceneView: React.FC<{ s: Scene; idx: number }> = ({ s, idx }) => {
  const f = useCurrentFrame();
  const isMelt = idx === 2;
  return (
    <AbsoluteFill style={{ background: s.bg }}>
      {/* 배경 장식: 큰 원 */}
      <div style={{ position: "absolute", right: -260, top: -260, width: 760, height: 760, borderRadius: 400, background: s.dark ? "rgba(255,255,255,.05)" : "rgba(47,93,74,.06)", transform: `scale(${1 + f / 600})` }} />
      <Words
        lines={s.title} sub={s.sub} kicker={s.kicker} dark={s.dark} dur={s.dur}
        swap={isMelt ? { at: 68, lines: ["모두의 바람을 담은", "제안을 만들어요"] } : undefined}
      />
      <Browser shots={s.shots} dur={s.dur} taps={s.taps} melt={isMelt ? 66 : undefined} />
    </AbsoluteFill>
  );
};

/* ---------- 0~3초: 문제 제기 ---------- */
const Hook: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const apart = spring({ frame: f, fps, config: { damping: 14, stiffness: 60 } });
  const together = interpolate(f, [50, 82], [0, 1], { ...clamp, easing: Easing.inOut(Easing.ease) });
  const gap = interpolate(apart, [0, 1], [30, 330]) * (1 - together) + 40 * together;
  const textO = interpolate(f, [8, 24], [0, 1], { ...clamp, easing: ease });
  const exit = interpolate(f, [80, 90], [0, 1], clamp);
  const av = (c: string, ch: string, dx: number) => (
    <div style={{ position: "absolute", left: 960 - 80 + dx, top: 250, width: 160, height: 160, borderRadius: 80, background: c, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: FONT, fontWeight: 800, fontSize: 72, boxShadow: "0 18px 40px rgba(0,0,0,.18)" }}>{ch}</div>
  );
  return (
    <AbsoluteFill style={{ background: DESK, opacity: 1 - exit * 0.2 }}>
      {av(BLUE, "민", -gap)}
      {av(TERRA, "서", gap)}
      <div style={{ position: "absolute", top: 560, width: "100%", textAlign: "center", fontFamily: FONT, fontWeight: 800, fontSize: 92, letterSpacing: -3, color: INK, opacity: textO, transform: `translateY(${(1 - textO) * 30}px)` }}>
        돈 이야기, <span style={{ color: GREEN }}>가족마다</span> 생각이 달라요
      </div>
    </AbsoluteFill>
  );
};

/* ---------- 마지막: 엔딩 ---------- */
const Ending: React.FC = () => {
  const f = useCurrentFrame();
  const o = interpolate(f, [0, 16], [0, 1], { ...clamp, easing: ease });
  const o2 = interpolate(f, [14, 32], [0, 1], { ...clamp, easing: ease });
  return (
    <AbsoluteFill style={{ background: GREEN, alignItems: "center", justifyContent: "center" }}>
      <div style={{ opacity: o, transform: `scale(${0.94 + o * 0.06})`, display: "flex", alignItems: "center", gap: 26 }}>
        <Img src={staticFile("mark.png")} style={{ height: 120 }} />
        <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: 120, color: "#fff", letterSpacing: -3 }}>ONE-Heart</div>
      </div>
      <div style={{ marginTop: 40, fontFamily: FONT, fontWeight: 400, fontSize: 40, color: "rgba(255,255,255,.9)", opacity: o2 }}>서로 다른 생각을, 같은 미래를 향한 하나의 계획으로</div>
    </AbsoluteFill>
  );
};

/* ---------- 장면 사이 초록 와이프 ---------- */
const Wipe: React.FC<{ at: number }> = ({ at }) => {
  const f = useCurrentFrame();
  const t = f - at;
  if (t < -6 || t > 8) return null;
  const x = interpolate(t, [-6, 2, 8], [-110, 0, 110], { ...clamp, easing: Easing.inOut(Easing.ease) });
  return <div style={{ position: "absolute", top: 0, left: `${x}%`, width: "100%", height: "100%", background: GREEN_D, opacity: 0.0 }} />;
};

export const Demo: React.FC = () => {
  useFont();
  return (
    <AbsoluteFill style={{ background: DESK }}>
      <Sequence from={0} durationInFrames={90}><Hook /></Sequence>
      {S.map((s, i) => (
        <Sequence key={i} from={s.from} durationInFrames={s.dur}><SceneView s={s} idx={i} /></Sequence>
      ))}
      <Sequence from={850} durationInFrames={50}><Ending /></Sequence>
      {S.map((s) => <Wipe key={"w" + s.from} at={s.from} />)}
    </AbsoluteFill>
  );
};
