// 확인용: 서로 다른 선택 → 돌아가기, 재점검 → Ver.2 흐름이 재생 모드에서 도는지
import fs from "node:fs";
import { launch, mk, toAgree } from "./flow.mjs";

const OUT = "probe";
fs.mkdirSync(OUT, { recursive: true });
const which = process.argv[2] || "A";

const { browser, page } = await launch();
const h = mk(page, OUT);
const { w, act, shot, list, setViewer } = h;

await toAgree(page, h);

if (which === "A") {
  // 민준 A, 서연 C
  await act("okpick", 0);
  await w(500);
  await act("sub");
  await w(1800);
  await act("viewer").catch(() => setViewer("m1"));
  await w(1000);
  await act("okpick", 2);
  await w(500);
  await act("sub");
  await w(4000);
  console.log("A-고른 뒤:", await list());
  await shot("A1-diverge");
  await act("back-goal");
  await w(4000);
  console.log("A-돌아간 뒤:", await list());
  await shot("A2-back-goal");
} else {
  for (let i = 0; i < 2; i++) {
    await act("okpick", 1);
    await w(500);
    await act("sub");
    await w(1800);
    if (i === 0) {
      await act("viewer").catch(() => setViewer("m1"));
      await w(1000);
    }
  }
  await w(3500);
  const signNow = () => page.evaluate(() => document.querySelector(".sig:not(.on):not([disabled])")?.click());
  await signNow();
  await w(1500);
  const other = await page.evaluate(() => {
    const sel = document.querySelector("#viewer");
    return [...sel.options].map((o) => o.value).find((v) => v !== sel.value);
  });
  await setViewer(other);
  await w(1200);
  await signNow();
  await w(2000);
  await act("next");
  await w(5000);
  await act("next");
  await w(5000);
  console.log("B-가족 홈:", await list());
  await shot("B1-home");
  // 재점검 접기 열기
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
  console.log("B-재점검 결과:", await list());
  await shot("B2-review");
  await act("renegotiate");
  await w(1000);
  await page.evaluate(() => [...document.querySelectorAll("button")].find((e) => e.textContent.trim() === "다시 정하기")?.click());
  await w(9000);
  console.log("B-다시 정하기 뒤:", await list());
  await shot("B3-calc-v2");
  await act("next");
  await w(5000);
  console.log("B-합의안 Ver.2 고르기:", await list());
  for (let i = 0; i < 2; i++) {
    await act("okpick", 1);
    await w(500);
    await act("sub");
    await w(1800);
    if (i === 0) {
      await act("viewer").catch(() => setViewer("m1"));
      await w(1000);
    }
  }
  await w(3500);
  await shot("B4-agree-v2");
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
  await shot("B5-signed-v2");
  await act("next");
  await w(5000);
  await act("next");
  await w(5000);
  console.log("B-가족 홈 Ver.2:", await list());
  await shot("B6-home-v2");
}
await browser.close();
