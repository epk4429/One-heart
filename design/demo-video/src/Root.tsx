import React from "react";
import { AbsoluteFill, Composition, Sequence, interpolate, useCurrentFrame } from "remotion";
import { C, useFont } from "./design";
import { Wipe } from "./common";
import { Opening, S1, S2 } from "./scenes";
import { S3 } from "./s3";
import { S4a } from "./s4";
import { S4b } from "./s5";
import { S5 } from "./s6";
import { S6 } from "./s7";
import { S7 } from "./s8";
import { S8 } from "./s9";
import { LENGTHS, ORDER, START, TOTAL } from "./timeline";
import type { SceneId } from "./timeline";

const W = 1920, H = 1080, FPS = 30;

const WithFont: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  useFont();
  return <AbsoluteFill style={{ background: C.DESK }}>{children}</AbsoluteFill>;
};

const OpeningComp = () => <WithFont><Opening /></WithFont>;
const S1Comp = () => <WithFont><S1 /></WithFont>;
const S2Comp = () => <WithFont><S2 /></WithFont>;
const S3Comp = () => <WithFont><S3 /></WithFont>;
const S4aComp = () => <WithFont><S4a /></WithFont>;
const S4bComp = () => <WithFont><S4b /></WithFont>;
const S5Comp = () => <WithFont><S5 /></WithFont>;
const S6Comp = () => <WithFont><S6 /></WithFont>;
const S7Comp = () => <WithFont><S7 /></WithFont>;
const S8Comp = () => <WithFont><S8 /></WithFont>;
// ===== 전체 영상(1분 29초): 장면 10개를 시간표(timeline.ts) 순서대로 이어 붙인다 =====
const SCENES: Record<SceneId, React.FC> = { opening: Opening, s1: S1, s2: S2, s3: S3, s4a: S4a, s4b: S4b, s5: S5, s6: S6, s7: S7, s8: S8 };
// 장면 사이는 부드러운 페이드(배경색을 통과해 자연스럽게 넘어감, ✅ 2026-11-22 형님 지시로 숲색 전환 폐지).
// 이어지는 장면(넷째 ①→②, 다섯째→이어지는 장면, 합의 후→이후)은 페이드 없이 이어 붙임
const FADE_IN: SceneId[] = ["s1", "s2", "s3", "s4a", "s5", "s7"];
const FADE_OUT: SceneId[] = ["opening", "s1", "s2", "s3", "s4b", "s6"];
const FADE = 10;
const FadeScene: React.FC<{ id: SceneId; children: React.ReactNode }> = ({ id, children }) => {
  const f = useCurrentFrame();
  const a = FADE_IN.includes(id) ? interpolate(f, [0, FADE], [0, 1], { extrapolateRight: "clamp" }) : 1;
  const b = FADE_OUT.includes(id) ? interpolate(f, [LENGTHS[id] - FADE, LENGTHS[id]], [1, 0], { extrapolateLeft: "clamp" }) : 1;
  return <AbsoluteFill style={{ opacity: a * b }}>{children}</AbsoluteFill>;
};
const Demo = () => (
  <WithFont>
    {ORDER.map((id) => {
      const Scene = SCENES[id];
      return <Sequence key={id} from={START[id]} durationInFrames={LENGTHS[id]}><FadeScene id={id}><Scene /></FadeScene></Sequence>;
    })}
  </WithFont>
);

// 확인용: 오프닝 → 전환 → 첫째
const Preview01 = () => (
  <WithFont>
    <Sequence from={0} durationInFrames={LENGTHS.opening}><Opening /></Sequence>
    <Sequence from={LENGTHS.opening} durationInFrames={LENGTHS.s1}><S1 /></Sequence>
    <Wipe at={LENGTHS.opening} />
  </WithFont>
);

export const Root: React.FC = () => (
  <>
    <Composition id="Demo" component={Demo} durationInFrames={TOTAL} fps={FPS} width={W} height={H} />
    <Composition id="Opening" component={OpeningComp} durationInFrames={LENGTHS.opening} fps={FPS} width={W} height={H} />
    <Composition id="S1" component={S1Comp} durationInFrames={LENGTHS.s1} fps={FPS} width={W} height={H} />
    <Composition id="S2" component={S2Comp} durationInFrames={LENGTHS.s2} fps={FPS} width={W} height={H} />
    <Composition id="S3" component={S3Comp} durationInFrames={LENGTHS.s3} fps={FPS} width={W} height={H} />
    <Composition id="S4a" component={S4aComp} durationInFrames={LENGTHS.s4a} fps={FPS} width={W} height={H} />
    <Composition id="S4b" component={S4bComp} durationInFrames={LENGTHS.s4b} fps={FPS} width={W} height={H} />
    <Composition id="S5" component={S5Comp} durationInFrames={LENGTHS.s5} fps={FPS} width={W} height={H} />
    <Composition id="S6" component={S6Comp} durationInFrames={LENGTHS.s6} fps={FPS} width={W} height={H} />
    <Composition id="S7" component={S7Comp} durationInFrames={LENGTHS.s7} fps={FPS} width={W} height={H} />
    <Composition id="S8" component={S8Comp} durationInFrames={LENGTHS.s8} fps={FPS} width={W} height={H} />
    <Composition id="Preview01" component={Preview01} durationInFrames={LENGTHS.opening + LENGTHS.s1} fps={FPS} width={W} height={H} />
  </>
);
