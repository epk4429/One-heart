import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT, ease, clamp, shot } from "./design";
import { BrowserFrame, CueLabel, Keyword, Marker, Ring, ScrollFrame, mapBox, Box } from "./common";
import { StageLabel } from "./s4";
import meta from "../public/shots2/s6.json";
import docMeta from "../public/shots2/s6b.json";

/* ===== 다섯째 · 시나리오를 검토하고 선택해요 (270프레임) =====
 * 0~3.5초: 각자 괜찮은 방법 고르기 화면(강조 없이)에서 B를 고르고, "✓ 민준" → "✓ 서연" 라벨이 쌓임
 * 3.5~9초: 합의안 문서를 위에서 아래로 스크롤해 보여 주고, 실행 계획 세 줄에 형광펜
 * (✅ 2026-11-22 형님 지시: 방법별 년도 강조를 빼고 합의안을 스크롤로 보여 줌, 실행 계획 3줄) */
const W = 1100;
const ASPECT = 1.56;
const X = (1920 - W) / 2;
const Y = 300;
const CROP_P = { y0: 75 / 900 };
const mP = (b: Box) => mapBox(b, W, CROP_P);
const md = meta as unknown as { cards: Box[] };
const dm = docMeta as unknown as { w: number; h: number; title: Box; plans: Box[] };
const CONTENT_H = W / ASPECT;

const NamePillSmall: React.FC<{ name: string; color: string; x: number; y: number; at: number }> = ({ name, color, x, y, at }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: f - at, fps, config: { damping: 11, stiffness: 140 } });
  return (
    <div style={{ position: "absolute", left: x, top: y, transform: `scale(${s})`, transformOrigin: "left center", opacity: Math.min(1, s * 1.4), background: color, color: "#fff", fontFamily: FONT, fontWeight: 800, fontSize: 22, padding: "3px 20px 5px", borderRadius: 40, boxShadow: "0 6px 14px rgba(0,0,0,.20)", whiteSpace: "nowrap" }}>✓ {name}</div>
  );
};

export const S5: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: f - 14, fps, config: { damping: 18, stiffness: 90 } });
  const pickB = interpolate(f, [26, 38], [0, 1], clamp);
  const toDoc = interpolate(f, [98, 118], [0, 1], { ...clamp, easing: ease });
  const cardB = mP(md.cards[1]);
  // 라벨은 카드 B 아래, 박스 안쪽 빈 줄에 나란히(가로로) 쌓는다
  const pillX = cardB.x + 8;
  const pillX2 = pillX + 108;
  const pillY = cardB.y + cardB.h + 10;
  return (
    <AbsoluteFill style={{ background: C.DESK }}>
      <CueLabel text="다섯째" tx={960} ty={78} />
      <Keyword lines={["시나리오를 검토하고 선택해요"]} x={960} y={112} size={84} />
      <StageLabel text="합의안" at={14} opacity={1} blur={0} />
      <BrowserFrame src={shot("a06y-pick")} x={X} y={Y} width={W} aspect={ASPECT} crop={CROP_P} dy={(1 - enter) * 90}
        opacity={Math.min(1, enter * 1.3) * (1 - toDoc)} />
      <BrowserFrame src={shot("a06y-pick-B")} x={X} y={Y} width={W} aspect={ASPECT} crop={CROP_P} shadow={false}
        opacity={pickB * (1 - toDoc)}
        zoomed={<>
          <Ring cx={cardB.x + cardB.w / 2} cy={cardB.y + cardB.h / 2} at={30} />
          <NamePillSmall name="민준" color={C.MINJUN} x={pillX} y={pillY} at={36} />
          <NamePillSmall name="서연" color={C.SEOYEON} x={pillX2} y={pillY} at={62} />
        </>} />
      <ScrollFrame src={shot("a06z-doc")} x={X} y={Y} width={W} contentH={CONTENT_H} imgCssW={dm.w} imgCssH={dm.h}
        scroll={{ start: 118, end: 196 }} endY={dm.title.y - 130} opacity={toDoc}>
        {(k) => {
          const b = (r: Box): Box => ({ x: r.x * k, y: r.y * k, w: r.w * k, h: r.h * k });
          return (
            <>
              <Marker box={b(dm.title)} at={198} />
              {dm.plans.map((p, i) => <Marker key={i} box={b(p)} at={210 + i * 12} />)}
            </>
          );
        }}
      </ScrollFrame>
    </AbsoluteFill>
  );
};
