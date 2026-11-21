// 가족방 화면 중 '가족방 이름 + 함께할 가족' 부분만 다시 캡처 (안내 문구가 안 보이게)
import { launch, mk, BASE } from "./flow.mjs";
const OUT = "public/shots2";
const { browser, page } = await launch();
const h = mk(page, OUT);
await page.goto(BASE, { waitUntil: "networkidle" });
await h.hideDock();
await page.evaluate(() => [...document.querySelectorAll("button")].find((e) => e.textContent.includes("이 예시로 체험하기")).click());
await h.w(1500);
await h.hideDock();
// 방장(가족방을 만든 사람)을 민준으로: 초대 링크를 보내는 쪽이 민준이라서
await page.evaluate(() => {
  const sel = [...document.querySelectorAll("select")].find((s) => [...s.options].some((o) => o.text.includes("민준")) && [...s.options].some((o) => o.text.includes("서연")));
  if (!sel) throw new Error("방장 선택칸 없음");
  const opt = [...sel.options].find((o) => o.text.includes("민준"));
  sel.value = opt.value;
  sel.dispatchEvent(new Event("change", { bubbles: true }));
});
await h.w(600);
await page.evaluate(() => {
  const el = [...document.querySelectorAll("body *")].find((e) => e.offsetParent && e.children.length === 0 && e.textContent.trim() === "가족방");
  window.scrollTo(0, window.scrollY + el.getBoundingClientRect().top - 130);
});
await h.w(600);
await page.screenshot({ path: `${OUT}/a01b-family-members.png` });
console.log("ok");
await browser.close();
