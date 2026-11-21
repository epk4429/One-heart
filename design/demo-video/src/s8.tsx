import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig, Easing } from "remotion";
import { C, FONT, ease, clamp, shot } from "./design";
import { BrowserFrame, CueLabel, Keyword, Outline, Ring, ScrollFrame, mapBox, Box } from "./common";
import { StageLabel } from "./s4";
import meta from "../public/shots2/s8.json";

/* ===== 합의 후 (270프레임) — 큐 라벨은 임시로 "합의 후"(마지막으로 → 형님 요청으로 바꿈, 2026-11-22) =====
 * 0~3초: 처음부터 두 사람 모두 서명된 화면에서 서명 칸 강조 링 → "합의안이 확정됐어요" 테두리
 * 3~6초: 상품 목록(위쪽 4장)이 위에서 아래로 천천히 스크롤. 단계 이름 라벨 "목표에 맞는 상품 추천"
 * 6~9초: 가족 홈이 펼쳐지고 처음부터 라벨은 "대시보드 생성"만(체크·'가족 홈' 라벨 없음, 2026-11-22 형님 지시) */
export const CUE_TEXT = "합의 후";
const W = 1100;
const ASPECT = 1.56;
const X = (1920 - W) / 2;
const Y = 300;
const CONTENT_H = W / ASPECT;
const CROP_S = { y0: 60 / 900 };
const mS = (b: Box) => mapBox(b, W, CROP_S);
const CROP_H = { x0: 300 / 1440, x1: 1380 / 1440, y0: 330 / 1100 }; // 가족 홈 캡처는 1440×1100(길게 찍음)
const m = meta as unknown as {
  sig1: { sigEls: Box[] };
  sig2: { sealed: Box };
  products: { clipW: number; clipH: number };
};

export const S7: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: f - 14, fps, config: { damping: 18, stiffness: 90 } });
  const signOut = interpolate(f, [84, 100], [1, 0], clamp);
  const prodIn = interpolate(f, [90, 108], [0, 1], { ...clamp, easing: ease });
  const prodOut = interpolate(f, [170, 186], [1, 0], clamp);
  const homeIn = interpolate(f, [176, 194], [0, 1], { ...clamp, easing: Easing.inOut(Easing.ease) });
  const prodOp = prodIn * prodOut;
  const signOp = Math.min(1, enter * 1.3) * signOut;
  // 서명 칸 좌표는 서명 전 화면(sig1) 기준이라 서명 후(sig2)에는 y가 3px 아래. 칸 가운데에 링을 둔다.
  const [mj, sy] = m.sig1.sigEls.map((b) => ({ ...b, y: b.y + 3, h: b.h + 8 }));
  const rMj = mS(mj);
  const rSy = mS(sy);
  const sealed = mS(m.sig2.sealed);
  return (
    <AbsoluteFill style={{ background: C.DESK }}>
      <CueLabel text={CUE_TEXT} tx={960} ty={78} />
      <Keyword lines={["합의하고 상품을 추천받아요"]} x={960} y={112} size={84} />
      <StageLabel text="합의안" at={14} opacity={signOut} blur={(1 - signOut) * 10} />
      <StageLabel text="목표에 맞는 상품 추천" at={0} opacity={prodOp} blur={(1 - prodOp) * 10} />
      <StageLabel text="대시보드 생성" at={176} opacity={homeIn} blur={(1 - homeIn) * 10} />
      {/* 처음부터 두 사람 모두 서명된 화면에서 서명 칸에 강조 링 */}
      <BrowserFrame src={shot("a08-sign2")} x={X} y={Y} width={W} aspect={ASPECT} crop={CROP_S} dy={(1 - enter) * 90}
        opacity={signOp}
        zoomed={<>
          <Ring cx={rMj.x + rMj.w / 2} cy={rMj.y + rMj.h / 2} at={24} />
          <Ring cx={rSy.x + rSy.w / 2} cy={rSy.y + rSy.h / 2} at={40} />
          <Outline box={sealed} at={62} pad={6} />
        </>} />
      <ScrollFrame src={shot("a08-products")} x={X} y={Y} width={W} contentH={CONTENT_H} imgCssW={m.products.clipW} imgCssH={m.products.clipH}
        scroll={{ start: 108, end: 172 }} opacity={prodOp} />
      <BrowserFrame src={shot("a08-home")} x={X} y={Y} width={W} aspect={ASPECT} imgAspect={1440 / 1100} crop={CROP_H} opacity={homeIn} />
    </AbsoluteFill>
  );
};
