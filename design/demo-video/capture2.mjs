// 영상용 화면 전체 캡처 + 강조할 요소의 좌표(shots.json). 재생 모드 서버(AI 비용 0원)
// 사용: node capture2.mjs  → public/shots2/*.png, public/shots2/shots.json
import fs from "node:fs";
import { launch, mk, toAgree } from "./flow.mjs";

const OUT = "public/shots2";
fs.mkdirSync(OUT, { recursive: true });
const { browser, page } = await launch();
const h = mk(page, OUT);
const { w, act, has, clickText, hideDock, setViewer } = h;
const meta = {};

// 화면 속 요소의 위치(뷰포트 기준 CSS px). spec: {act,text,nth} | {text} | {css}
const boxOf = (spec) =>
  page.evaluate((s) => {
    let el = null;
    if (s.css) el = document.querySelectorAll(s.css)[s.nth || 0];
    else if (s.act) {
      const l = [...document.querySelectorAll(`[data-act="${s.act}"]`)].filter((e) => e.offsetParent);
      el = s.text ? l.find((e) => e.textContent.includes(s.text)) : l[s.nth || 0];
    } else if (s.text) {
      const c = [...document.querySelectorAll("body *")].filter(
        (e) => e.offsetParent && ((e.textContent.includes(s.text) && ![...e.children].some((c) => c.textContent.includes(s.text))) || (e.tagName === "INPUT" && String(e.value).includes(s.text)))
      );
      el = c[s.nth || 0];
      if (el && s.up) for (let i = 0; i < s.up && el.parentElement; i++) el = el.parentElement;
    }
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
  }, spec);

const scrollToSpec = async (spec, offset = 140) => {
  await page.evaluate(
    ([s, off]) => {
      let el = null;
      if (s.text) {
        const c = [...document.querySelectorAll("body *")].filter(
          (e) => e.offsetParent && ((e.textContent.includes(s.text) && ![...e.children].some((c) => c.textContent.includes(s.text))) || (e.tagName === "INPUT" && String(e.value).includes(s.text)))
        );
        el = c[0];
      } else if (s.act) el = [...document.querySelectorAll(`[data-act="${s.act}"]`)].filter((e) => e.offsetParent)[s.nth || 0];
      else if (s.css) el = document.querySelector(s.css);
      if (el) window.scrollTo(0, window.scrollY + el.getBoundingClientRect().top - off);
    },
    [spec, offset]
  );
  await w(400);
};

const snap = async (name, boxes = {}, scrollSpec = null, offset = 140) => {
  if (scrollSpec) await scrollToSpec(scrollSpec, offset);
  else await page.evaluate(() => window.scrollTo(0, 0));
  await w(500);
  const b = {};
  for (const [k, s] of Object.entries(boxes)) b[k] = await boxOf(s);
  await page.screenshot({ path: `${OUT}/${name}.png` });
  meta[name] = { boxes: b };
  console.log("shot", name, JSON.stringify(b).slice(0, 160));
};

await toAgree(page, h, {
  afterFamilyRoom: async () => {
    await snap("a01-family-room");
  },
  storyTop: async () => {
    await snap("a02-story-top", { cat: { act: "gi-cat", text: "내 집 마련" }, catAll: { act: "gi-cat", nth: 0 }, goalAmt: { text: "집 마련에 필요한 돈" } });
    await snap("a02b-story-fin", { r1: { text: "가온은행 예금", up: 2 }, r2: { text: "가온은행 전세대출", up: 2 }, r3: { text: "둘이 버는 돈", up: 2 } }, { text: "가온은행 예금" }, 220);
    await snap("a02c-story-goal", { goalAmt: { text: "집 마련에 필요한 돈" } }, { text: "집 마련에 필요한 돈" }, 300);
  },
  chat: async (first) => {
    await snap(first ? "a03-chat-seoyeon" : "a03-chat-minjun", {});
  },
  summary: async (first) => {
    await snap(first ? "a03s-summary-seoyeon" : "a03s-summary-minjun", {});
  },
  goalThink: async () => {
    await snap("a04-goal-think", { same: { text: "이미 같은 생각인 부분", up: 2 }, diff: { text: "생각이 갈리는 부분", up: 2 } });
    await snap("a04b-goal-diff", { mj: { text: "우리 집에서 아이랑 사는 거요", nth: 0, up: 2 }, sy: { text: "아이가 있고, 제가 육아휴직을", nth: 0, up: 2 } }, { text: "생각이 갈리는 부분" }, 140);
    await snap("a04c-goal-propose", { cover: { text: "모두의 지키고 싶은 것을 담았어요" } }, { text: "모두의 지키고 싶은 것을 담았어요" }, 420);
  },
  calc: async () => {
    await snap("a05-calc-top", { A: { act: "pick", nth: 0 }, B: { act: "pick", nth: 1 }, C: { act: "pick", nth: 2 } });
    await snap("a05b-calc-chart", {}, { css: ".chart, svg" }, 160);
  },
});

// ===== 6단계: 합의안 고르기(지금 화면) =====
await snap("a06-agree-top", { period: { text: "각자 꼭 지키고 싶은 것으로" } });
await snap("a06b-agree-pick", { okA: { act: "okpick", nth: 0 }, okB: { act: "okpick", nth: 1 }, okC: { act: "okpick", nth: 2 }, sub: { act: "sub" } }, { text: "각자 괜찮은 방법 고르기" }, 120);

// --- 갈라지는 선택(민준 A, 서연 C) → 돌아가기 ---
await act("okpick", 0);
await w(400);
await act("sub");
await w(1800);
await act("viewer");
await w(1000);
await act("okpick", 2);
await w(400);
await act("sub");
await w(4000);
await snap("b01-diverge", { back: { act: "back-goal" }, none: { text: "모두가 고른 방법이 없어요" } }, { text: "모두가 고른 방법이 없어요" }, 200);
await act("back-goal");
await w(4000);
await snap("b02-back-goal", { reply: { act: "reply-pick", nth: 0 } }, { text: "AI의 제안" }, 120);
// 수정 제안 → 다시 좋아요 → 숫자 → 동의 → 다시 계산
for (let p = 0; p < 2; p++) {
  await clickText("reply-pick", "좋아요");
  await w(500);
  await act("reply-send");
  await w(3000);
  if (p === 0) {
    await act("viewer");
    await w(1000);
  }
}
await act("approve");
await w(800);
await act("viewer");
await w(800);
await act("approve");
await w(1500);
await act("next");
await w(7000);
await snap("b03-recalc", { A: { act: "pick", nth: 0 }, B: { act: "pick", nth: 1 }, C: { act: "pick", nth: 2 } });
await act("next");
await w(5000);

// ===== 합의안: 모두 B 선택 → 문서 → 서명 =====
for (let i = 0; i < 2; i++) {
  await act("okpick", 1);
  await w(500);
  if (i === 0) await snap("c01-pick-minjun", { okB: { act: "okpick", nth: 1 } }, { text: "각자 괜찮은 방법 고르기" }, 120);
  await act("sub");
  await w(1800);
  if (i === 0) {
    const cur = await page.evaluate(() => document.querySelector("#viewer").value);
    await act("viewer").catch(() => {});
    await w(1000);
    if ((await page.evaluate(() => document.querySelector("#viewer").value)) === cur) await setViewer("m1");
    await w(800);
  }
}
await w(3500);
await snap("c02-agree-doc", { rep: { text: "합의 리포트" } }, { text: "함께 이룰 목표" }, 160);
await snap("c02b-actionplan", { ap: { text: "실행 계획" } }, { text: "실행 계획" }, 240);
const signNow = () => page.evaluate(() => document.querySelector(".sig:not(.on):not([disabled])")?.click());
await signNow();
await w(1500);
await snap("c03-sign-one", { sigs: { css: ".sigs" } }, { css: ".sigs" }, 300);
const other = await page.evaluate(() => {
  const sel = document.querySelector("#viewer");
  return [...sel.options].map((o) => o.value).find((v) => v !== sel.value);
});
await setViewer(other);
await w(1200);
await signNow();
await w(2000);
await snap("c04-signed", { sigs: { css: ".sigs" }, sealed: { css: ".sealed" } }, { css: ".sigs" }, 300);
await act("next");
await w(5000);
await snap("c05-products-top", { c1: { css: "[data-act='fold']", nth: 0 }, c4: { css: "[data-act='fold']", nth: 3 } });
await act("next");
await w(5000);

// ===== 8단계: 가족 홈 =====
await snap("d01-home", { goal: { text: "내 집 마련" }, promise: { text: "이번 달 약속" } });
await snap("d01b-home-promise", { promise: { text: "이번 달 약속" } }, { text: "이번 달 약속" }, 200);
await page.evaluate(() => [...document.querySelectorAll('[data-act="fold"]')].find((e) => e.textContent.includes("지난 3개월 돈의 흐름"))?.click());
await w(800);
await snap("d02-home-flow", { flow: { text: "지난 3개월 돈의 흐름" } }, { text: "지난 3개월 돈의 흐름" }, 160);
await page.evaluate(() => [...document.querySelectorAll('[data-act="fold"]')].find((e) => e.textContent.includes("재점검"))?.click());
await w(800);
await page.evaluate(() => {
  const i = document.querySelector('[data-rv="income_delta"]');
  i.value = "-50";
  i.dispatchEvent(new Event("input", { bubbles: true }));
  i.dispatchEvent(new Event("change", { bubbles: true }));
});
await w(500);
await act("review");
await w(2500);
await snap("d03-review-result", { renego: { act: "renegotiate" }, result: { text: "→" } }, { act: "renegotiate" }, 520);
await act("renegotiate");
await w(1000);
await snap("d03b-renego-confirm", {});
await page.evaluate(() => [...document.querySelectorAll("button")].find((e) => e.textContent.trim() === "다시 정하기")?.click());
await w(9000);
await act("next");
await w(5000);
for (let i = 0; i < 2; i++) {
  await act("okpick", 1);
  await w(500);
  await act("sub");
  await w(1800);
  if (i === 0) {
    const cur = await page.evaluate(() => document.querySelector("#viewer").value);
    await act("viewer").catch(() => {});
    await w(1000);
    if ((await page.evaluate(() => document.querySelector("#viewer").value)) === cur) await setViewer("m1");
    await w(800);
  }
}
await w(3500);
await snap("e01-agree-v2", {}, { text: "Ver.2" }, 200);
await signNow();
await w(1500);
const other2 = await page.evaluate(() => {
  const sel = document.querySelector("#viewer");
  return [...sel.options].map((o) => o.value).find((v) => v !== sel.value);
});
await setViewer(other2);
await w(1200);
await signNow();
await w(2000);
await act("next");
await w(5000);
await act("next");
await w(5000);
await snap("e02-home-v2", { goal: { text: "내 집 마련" } });

fs.writeFileSync(`${OUT}/shots.json`, JSON.stringify(meta, null, 1));
await browser.close();
console.log("완료", Object.keys(meta).length);
