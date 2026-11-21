import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig, Easing } from "remotion";
import { C, ease, clamp, shot } from "./design";
import { BrowserFrame, CueLabel, Keyword, Marker, Outline, Ring, ScrollFrame, Box } from "./common";
import meta from "../public/shots2/s9.json";
import { StageLabel } from "./s4";
import { CUE_TEXT } from "./s8";

/* ===== 이후 (450프레임) =====
 * 0~5초: 가족 홈 '이번 달 약속'(실행계획) → '지난 3개월 돈의 흐름'(진행상황) 형광펜
 * 5~8초: 재점검 결과 화면(지난 합의와의 차이)
 * 8~15초: Ver.2 합의안(서명 완료) → 기존 대시보드가 옆으로 밀리고 Ver.2 대시보드가 새로 나타남(마지막 약 2.5초 머묾) */
const W = 1100;
const X = (1920 - W) / 2;
const Y = 300;
const X0 = 300 / 1440;
const X1 = 1380 / 1440;
const K = W / 1080; // 캡처 CSS px → 프레임 px
const mp = (b: Box, y0: number): Box => ({ x: (b.x - 300) * K, y: (b.y - y0) * K, w: b.w * K, h: b.h * K });

// 가족 홈(1440×1100 캡처) 보여 줄 세로 시작 위치(CSS px)
const Y_PROMISE = 420;
const Y_HOME = 330;
// 캡처 좌표(CSS px)
const PROMISE: Box[] = [
  { x: 365, y: 704, w: 86, h: 21 },
  { x: 405, y: 751, w: 282, h: 19 },
  { x: 405, y: 801, w: 330, h: 19 },
  { x: 405, y: 852, w: 402, h: 19 },
];
const FLOW_HEAD: Box = { x: 367, y: 168, w: 124, h: 18 };
const FLOW_SUMS: Box[] = [
  { x: 816, y: 224, w: 114, h: 22 },
  { x: 816, y: 304, w: 114, h: 22 },
  { x: 816, y: 385, w: 114, h: 22 },
];
const REVIEW_RESULT: Box = { x: 395, y: 197, w: 535, h: 122 };
const REVIEW_BTN: Box = { x: 536, y: 330, w: 225, h: 36 };
const AGREE_RESULT: Box = { x: 668, y: 150, w: 305, h: 17 };
const AGREE_SEALED: Box = { x: 668, y: 437, w: 480, h: 51 };
const HOMEV2: Box[] = [
  { x: 382, y: 480, w: 190, h: 17 },
  { x: 573, y: 556, w: 82, h: 24 },
  { x: 751, y: 556, w: 98, h: 24 },
];
const IMG_H = 1440 / 1100;
const TALL = (meta as unknown as { tall: { w: number; h: number; head: Box } }).tall;

export const S8: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: f - 14, fps, config: { damping: 18, stiffness: 90 } });

  // 화면 전환 구간
  const toReview = interpolate(f, [150, 168], [0, 1], { ...clamp, easing: Easing.inOut(Easing.ease) });
  const toAgree = interpolate(f, [236, 254], [0, 1], { ...clamp, easing: Easing.inOut(Easing.ease) });
  const push = interpolate(f, [332, 376], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const agreeOut = interpolate(f, [326, 336], [0, 1], clamp);

  const reviewOp = toReview * (1 - toAgree);
  const agreeOp = toAgree * (1 - agreeOut);

  const imgSrc = { aspect: 1.56, imgAspect: IMG_H };
  const lab = (a: number, b: number) => interpolate(f, [a, a + 8, b - 8, b], [0, 1, 1, 0], clamp);

  return (
    <AbsoluteFill style={{ background: C.DESK }}>
      {/* 위쪽 작은 큐 라벨만 '합의 후'로 이어진다. 키워드는 이 장면 것 그대로(✅ 2026-11-22 형님 지시) */}
      <CueLabel text={CUE_TEXT} tx={960} ty={78} pop={false} />
      <Keyword lines={["함께 점검하고, 달라지면 다시 합의해요"]} x={960} y={112} size={78} delay={0} />
      <StageLabel text="가족 홈 대시보드" at={14} opacity={interpolate(f, [150, 160], [1, 0], clamp)} blur={0} />
      <StageLabel text="재점검" at={150} opacity={lab(150, 244)} blur={0} />
      <StageLabel text="합의안 Ver.2" at={240} opacity={lab(240, 336)} blur={0} />
      <StageLabel text="대시보드 Ver.2" at={332} opacity={interpolate(f, [332, 344], [0, 1], clamp)} blur={0} />

      {/* 가족 홈(Ver.1): 이번 달 약속 → 같은 화면을 아래로 스크롤해 지난 3개월 돈의 흐름 (화면 전환 없이, 형님 지시 2026-11-22) */}
      <ScrollFrame src={shot("a09-tall")} x={X} y={Y} width={W} contentH={W / 1.56} imgCssW={TALL.w} imgCssH={TALL.h}
        startY={Y_PROMISE} endY={TALL.head.y - 150} scroll={{ start: 70, end: 122 }}
        dy={(1 - enter) * 90} opacity={Math.min(1, enter * 1.3) * (1 - toReview)}>
        {(k) => {
          const b = (r: Box): Box => ({ x: (r.x - 300) * k, y: r.y * k, w: r.w * k, h: r.h * k });
          return (
            <>
              {PROMISE.map((r, i) => <Marker key={i} box={b(r)} at={20 + i * 12} />)}
              <Marker box={b(TALL.head)} at={126} />
              {FLOW_SUMS.map((r, i) => <Marker key={"s" + i} box={b({ x: r.x, y: TALL.head.y + (r.y - 168), w: r.w, h: r.h })} at={134 + i * 6} dur={12} />)}
            </>
          );
        }}
      </ScrollFrame>
      {/* 재점검 결과 */}
      <BrowserFrame src={shot("a09-review")} x={X} y={Y} width={W} aspect={3.0} crop={{ x0: X0, x1: X1, y0: 90 / 900 }} shadow={false}
        opacity={reviewOp}
        zoomed={<>
          <Outline box={mp(REVIEW_RESULT, 90)} at={176} pad={8} />
          <Ring cx={mp(REVIEW_BTN, 90).x + mp(REVIEW_BTN, 90).w / 2} cy={mp(REVIEW_BTN, 90).y + mp(REVIEW_BTN, 90).h / 2} at={206} />
        </>} />
      {/* Ver.2 합의안(서명 완료) */}
      <BrowserFrame src={shot("a09-agree-v2")} x={X} y={Y} width={W} aspect={1.56} crop={{ x0: X0, x1: X1, y0: 20 / 900 }} shadow={false}
        opacity={agreeOp}
        zoomed={<>
          <Marker box={mp(AGREE_RESULT, 20)} at={258} />
          <Outline box={mp(AGREE_SEALED, 20)} at={284} pad={6} />
        </>} />
      {/* 기존 대시보드가 밀려나고 Ver.2 대시보드가 새로 나타남 */}
      <BrowserFrame src={shot("a09-home")} x={X - push * 1300} y={Y} width={W} aspect={1.56} imgAspect={IMG_H} crop={{ x0: X0, x1: X1, y0: Y_HOME / 1100 }}
        opacity={f >= 332 && push < 1 ? 1 - push * 0.6 : 0} scale={1 - push * 0.08} />
      <BrowserFrame src={shot("a09-home-v2")} x={X + (1 - push) * 1300} y={Y} width={W} aspect={1.56} imgAspect={IMG_H} crop={{ x0: X0, x1: X1, y0: Y_HOME / 1100 }}
        opacity={f >= 332 ? 1 : 0}
        zoomed={<>
          {HOMEV2.map((b, i) => <Marker key={i} box={mp(b, Y_HOME)} at={392 + i * 10} />)}
        </>} />
      {/* 밀려나는 구간 동안 "Ver.1" 표시 */}
      {f >= 332 && f < 382 && (
        <div style={{ position: "absolute", left: X - push * 1300 + 24, top: Y + 56, fontFamily: "Pretendard, sans-serif", fontWeight: 800, fontSize: 34, color: "#fff", background: "#848E88", padding: "4px 22px 6px", borderRadius: 30, opacity: 1 - push }}>Ver.1</div>
      )}
    </AbsoluteFill>
  );
};
