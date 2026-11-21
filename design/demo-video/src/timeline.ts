// 장면 시간표(30fps 프레임). 제작명세.md와 같아야 한다. 장면 길이는 여기서만 바꾼다.
export type SceneId = "opening" | "s1" | "s2" | "s3" | "s4a" | "s4b" | "s5" | "s6" | "s7" | "s8";
export const LENGTHS: Record<SceneId, number> = {
  opening: 60,
  s1: 240,
  s2: 360,
  s3: 240,
  s4a: 240,
  s4b: 300,
  s5: 270,
  s6: 240,
  s7: 270,
  s8: 450,
};
export const ORDER: SceneId[] = ["opening", "s1", "s2", "s3", "s4a", "s4b", "s5", "s6", "s7", "s8"];
export const START = Object.fromEntries(
  ORDER.map((id, i) => [id, ORDER.slice(0, i).reduce((a, k) => a + LENGTHS[k], 0)])
) as Record<SceneId, number>;
export const TOTAL = ORDER.reduce((a, k) => a + LENGTHS[k], 0);
