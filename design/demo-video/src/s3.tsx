import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT, ease, clamp, shot } from "./design";
import { BrowserFrame, CueLabel, Keyword, Outline, Ring, ScrollFrame, Box } from "./common";
import meta from "../public/shots2/s3b.json";

/* ===== 셋째 · 각자 AI와 이야기해요 (240프레임) =====
 * 0~5.5초: 대화 기록이 다 쌓인 채팅창(민준·서연)을 위에서 아래로 스크롤 → 공유하기 버튼
 * 5.5~8초: 버튼을 누르면 "요약 내용은 가족에게 공유돼요", 두 사람 요약이 한 화면에 */
const W = 760;
const CH = 666; // 화면 높이
const X = [150, 1010];
const Y = 330;
const PANEL_W = 1100;
const PANEL_ASPECT = 1720 / 1034;

const LockIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
    <rect x="4" y="11" width="16" height="10" rx="2.5" />
    <path d="M8 11V8a4 4 0 0 1 8 0v3" />
  </svg>
);

const PersonTag: React.FC<{ name: string; color: string; cx: number; appear: number }> = ({ name, color, cx, appear }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: f - appear, fps, config: { damping: 12, stiffness: 120 } });
  const b = spring({ frame: f - appear - 18, fps, config: { damping: 14, stiffness: 120 } });
  const out = interpolate(f, [156, 178], [1, 0], clamp);
  return (
    <div style={{ position: "absolute", left: cx, top: Y - 84, transform: "translate(-50%,0)", display: "flex", alignItems: "center", gap: 16, opacity: out, whiteSpace: "nowrap" }}>
      <div style={{ background: color, color: "#fff", fontFamily: FONT, fontWeight: 800, fontSize: 44, padding: "8px 36px 10px", borderRadius: 60, boxShadow: "0 10px 24px rgba(0,0,0,.16)", transform: `scale(${s})`, opacity: Math.min(1, s * 1.4) }}>{name}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: FONT, fontWeight: 700, fontSize: 24, color: C.GREEN, border: `2px solid ${C.GREEN}`, padding: "6px 20px 8px", borderRadius: 40, background: "rgba(47,93,74,.07)", transform: `scale(${b})`, opacity: Math.min(1, b * 1.4) }}>
        <LockIcon /> 본인만 볼 수 있어요
      </div>
    </div>
  );
};

export const S3: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: f - 14, fps, config: { damping: 18, stiffness: 90 } });
  const go = interpolate(f, [164, 188], [0, 1], { ...clamp, easing: ease }); // 채팅창이 안쪽으로 모이며 사라짐
  const wide = spring({ frame: f - 172, fps, config: { damping: 16, stiffness: 100 } });
  const pill = spring({ frame: f - 160, fps, config: { damping: 14, stiffness: 110 } });

  const chat = (i: number) => {
    const m = (i === 0 ? meta["chat-minjun"] : meta["chat-seoyeon"]) as { w: number; h: number; btn: Box };
    const ringAt = 148 + i * 8;
    return (
      <ScrollFrame key={i} src={shot(i === 0 ? "a03y-chat-minjun" : "a03y-chat-seoyeon")} x={X[i] + (i === 0 ? 1 : -1) * go * 140} y={Y} width={W} contentH={CH}
        imgCssW={m.w} imgCssH={m.h} scroll={{ start: 40 + i * 8, end: 138 + i * 8 }}
        dy={(1 - enter) * 90} scale={1 - go * 0.1} opacity={Math.min(1, enter * 1.3) * (1 - go)}>
        {(k) => {
          const b = { x: m.btn.x * k, y: m.btn.y * k, w: m.btn.w * k, h: m.btn.h * k };
          return (
            <>
              <Outline box={b} at={ringAt} />
              <Ring cx={b.x + b.w / 2} cy={b.y + b.h / 2} at={ringAt + 4} />
            </>
          );
        }}
      </ScrollFrame>
    );
  };

  return (
    <AbsoluteFill style={{ background: C.DESK }}>
      <CueLabel text="셋째" tx={960} ty={78} />
      <Keyword lines={["각자 AI와 이야기해요"]} x={960} y={112} size={84} />
      <PersonTag name="민준" color={C.MINJUN} cx={X[0] + W / 2} appear={24} />
      <PersonTag name="서연" color={C.SEOYEON} cx={X[1] + W / 2} appear={36} />
      {chat(0)}
      {chat(1)}
      <BrowserFrame src={shot("a03y-panel")} x={(1920 - PANEL_W) / 2} y={320} width={PANEL_W} aspect={PANEL_ASPECT} imgAspect={PANEL_ASPECT} crop={{ x0: 0, x1: 1, y0: 0.012 }}
        scale={0.94 + 0.06 * wide} opacity={Math.min(1, wide * 1.4)} />
      <div style={{ position: "absolute", left: 960, top: 244, transform: `translate(-50%,0) scale(${0.9 + 0.1 * pill})`, opacity: Math.min(1, pill * 1.4), background: C.GREEN, color: "#fff", fontFamily: FONT, fontWeight: 800, fontSize: 36, padding: "8px 34px 10px", borderRadius: 50, boxShadow: "0 10px 24px rgba(0,0,0,.18)", whiteSpace: "nowrap" }}>요약 내용은 가족에게 공유돼요</div>
    </AbsoluteFill>
  );
};
