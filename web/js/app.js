/* ONE-Heart 체험판 화면. 디자인은 v3 프로토타입, 내용은 전부 체험자의 입력과 API(LLM·계산엔진·검증·온톨로지) 결과.
   체험판은 한 기기에서 가족이 돌아가며 입력한다(아래 '보는 사람'을 바꿔 가며). 입력과 진행 상태는 이 브라우저에만 저장한다. */

const AIMARK = '<img src="img/mark.png" alt="" aria-hidden="true">'; // 기획안 로고의 하트(AI 상담사 표시에도 같은 로고를 쓴다)
const STEPS = ["가족방 만들기", "우리 가족 이야기", "각자의 생각", "공동 목표 설정", "미래 계산", "합의안", "상품 추천", "가족 홈"];
const OC = ["var(--m0)", "var(--green)", "var(--m3)"];
const MC = ["var(--m0)", "var(--m1)", "var(--m2)", "var(--m3)", "var(--warm)", "var(--ink2)"];
const G = {
  전세: "집주인에게 큰돈(보증금)을 맡기고 사는 방식이에요. 이사 나갈 때 그 돈을 돌려받아요.",
  주택연금: "집을 담보로 맡기고, 그 집에 계속 살면서 매달 생활비를 받는 제도예요.",
  수익률: "맡긴 돈이 1년에 몇 % 불어나는지예요. 5%면 100만원이 1년 뒤 105만원이 돼요.",
  순자산: "가진 재산에서 빚을 뺀 금액이에요.",
  물가: "같은 물건값이 해마다 오르는 정도예요. 생활비는 해마다 조금씩 늘어난다고 보고 계산해요.",
};
const T = (w, k) => `<button type="button" class="term" data-def="${G[k || w]}">${w}</button>`;
const VL = { good: ["좋아요", "✓"], cond: ["괜찮아요, 단", "△"], no: ["받아들이기 어려워요", "✕"] };
const SRC = { goal_setting: "공동 목표", condition: "조건", revision: "수정안", keep: "꼭 지키고 싶은 것" };
const GT = { reach_target: "목표 금액 모으기", runway: "예금이 얼마나 버티는지", debt_free: "대출 다 갚기" };
const METRIC = { reach_target: "목표에 닿는 때", runway: "예금이 버티는 기간", debt_free: "대출을 다 갚는 때" };

const $ = s => document.querySelector(s);
const esc = t => String(t ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const won = v => { const a = Math.abs(Math.round(v)), s = v < 0 ? "-" : ""; if (a >= 10000) { const e = Math.floor(a / 10000), r = a % 10000; return s + e + "억" + (r ? " " + r.toLocaleString("ko-KR") + "만" : "") + "원"; } return s + a.toLocaleString("ko-KR") + "만원"; };
const eokS = v => { const a = Math.abs(v), s = v < 0 ? "-" : ""; return a >= 10000 ? s + (Math.round(a / 1000) / 10) + "억" : s + Math.round(a).toLocaleString("ko-KR") + "만"; };
function ask(title, body, choices) {
  return new Promise(res => {
    const el = document.createElement("div");
    el.className = "modal";
    el.innerHTML = `<div class="mbox" role="dialog" aria-modal="true"><h3>${esc(title)}</h3>${body ? `<p>${esc(body)}</p>` : ""}<div class="mrow">${choices.map((c, i) => `<button class="btn ${c.primary ? "primary" : ""}" data-i="${i}">${esc(c.label)}</button>`).join("")}<button class="btn" data-i="-1">취소</button></div></div>`;
    el.onclick = e => { const b = e.target.closest("button[data-i]"); if (!b && e.target !== el) return; el.remove(); res(b ? (+b.dataset.i >= 0 ? choices[+b.dataset.i].value : null) : null); };
    document.body.appendChild(el);
  });
}
function toast(t) { const el = $("#toast"); el.textContent = t; el.classList.add("show"); clearTimeout(toast._t); toast._t = setTimeout(() => el.classList.remove("show"), 2200); }

/* ---------- 상태 · 저장 ---------- */
let view = "landing", room = "custom", step = 0, CFG = null, HEALTH = null;
let R = {};
const S = () => R[room];
const F = () => S().fam;
const memIdx = mid => F().members.findIndex(m => m.member_id === mid);
const mem = mid => F().members.find(m => m.member_id === mid) || { name: "?", initial: "?" };
const mids = () => F().members.map(m => m.member_id);
const av = (mid, cls = "") => { const i = memIdx(mid); return `<span class="av ${cls}" style="background:${MC[(i < 0 ? 0 : i) % MC.length]}">${esc((mem(mid).name || "?").slice(0, 1))}</span>`; };
const viewer = () => S().viewer;
const ROOMS = { custom: "내 가족", newly: "예시 · 신혼부부", elder: "예시 · 부모님과 자녀" };

const DOWN = {
  goal: { goal: {}, replies: {}, criterion: {}, goalForm: null, goalChk: {}, approvals: {} },
  design: { design: {}, pick: 1, override: {}, ovIn: {} },
  consent: { check: {}, r1: {}, sub1: {}, revise: {}, r2: {}, sub2: {}, draft: {}, signed: {}, rec: {}, home: {}, review: {} },
};
function reset(from) {
  const order = ["goal", "design", "consent"];
  for (const k of order.slice(order.indexOf(from))) for (const [f, v] of Object.entries(DOWN[k])) S()[f] = JSON.parse(JSON.stringify(v));
}
function nowYm() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; }
function blankFamily() {
  return { today: nowYm(), room: { name: "", reason: "", host_member_id: "m0" },
    members: [{ member_id: "m0", name: "", role: "", age: null, easy_mode: false }, { member_id: "m1", name: "", role: "", age: null, easy_mode: false }],
    story: { author_id: "m0", text: "" }, finance: [], disclosure: {} };
}
function freshState(key, fam, scripts) {
  const s = { key, fam, scripts: scripts || null, profile: null, setupDone: false, viewer: fam.room.host_member_id || fam.members[0].member_id,
    story: {}, iv: {} };
  R[key] = s; const prev = room; room = key; reset("goal"); room = prev;
  return s;
}
function save() {
  try { localStorage.setItem("oneheart.v2", JSON.stringify({ R, room, step })); } catch (e) { }
}
function load() {
  try {
    const d = JSON.parse(localStorage.getItem("oneheart.v2") || "null");
    if (!d) return;
    const clean = o => { if (o && typeof o === "object") { if (o.status === "loading") Object.keys(o).forEach(k => delete o[k]); else Object.values(o).forEach(clean); } };
    clean(d.R); R = d.R || {};
  } catch (e) { R = {}; }
}

/* ---------- 비동기 호출 ---------- */
async function run(slot, path, body, after) {
  slot.status = "loading"; delete slot.error; render();
  try {
    const res = await api(path, body);
    Object.assign(slot, res); slot.status = "done";
    if (after) await after(res);
  } catch (e) {
    slot.status = "error"; slot.error = e;
  }
  render();
}
const started = slot => slot && (slot.status === "loading" || slot.status === "done");
function pend(slot, label, retry) {
  if (!slot) return "";
  if (slot.status === "loading") return `<div class="pending"><span class="spin"></span>${label}</div>`;
  if (slot.status === "error") return `<div class="failbox"><b>${slot.error?.code === "budget_exhausted" ? "AI 사용량을 다 썼어요" : slot.error?.code === "access_denied" ? "체험 코드가 필요해요" : "처리하지 못했어요"}</b>${esc(slot.error?.message)}<br>${retry ? `<button class="btn sm" data-act="${retry}">다시 시도</button>` : ""}</div>`;
  return "";
}
function vbadge(v, calls) {
  return ""; // 검증은 서버에서 그대로 하고 결과는 응답(verification)에 남는다. 화면에는 보이지 않는다(2026-10-06 사용자 요청).
  if (!v) return "";
  const warn = v.violations.filter(x => x.severity === "warning").length;
  const cls = v.status === "fail" ? "fail" : warn ? "warn" : "";
  const label = v.status === "fail" ? "숫자 검증에서 문제를 찾았어요" : `숫자 검증 완료 · 계산엔진 결과와 대조 ${v.checked_numbers}건`;
  const id = "v" + Math.random().toString(36).slice(2, 8);
  const callTxt = (calls || []).filter(c => c.model).map(c => `역할 ${c.role} · ${c.model} · ${c.latency_s}초${c.tool_calls ? ` · 계산 도구 ${c.tool_calls}회` : ""}${c.cost_usd ? ` · $${c.cost_usd.toFixed(3)}` : ""}`).join(" / ");
  return `<button class="vbadge ${cls}" data-act="toggle" data-target="${id}">✓ ${label}</button>
  <div class="vdetail" id="${id}" hidden><div>대조한 계산 결과: ${v.facts_used.length ? v.facts_used.map(esc).join(", ") : "없음"}</div>
  ${v.violations.length ? `<ul>${v.violations.map(x => `<li>${x.severity === "error" ? "오류" : "경고"} · ${esc(x.type)} ${esc(x.text || x.id || x.member_id || "")}</li>`).join("")}</ul>` : "<div>규칙 위반 없음</div>"}
  ${callTxt ? `<div class="calls">${esc(callTxt)}</div>` : ""}</div>`;
}
const prevBtn = () => step > 0 ? `<button class="btn" data-act="prev"><span aria-hidden="true">←</span> 이전 단계</button>` : "";
const next = (label, dis, hint) => `<div class="next">${prevBtn()}<span class="pno">— ${step + 1} —</span>${dis && hint ? `<span class="hint">${hint}</span>` : ""}${label ? `<button class="btn primary" data-act="next" ${dis ? "disabled" : ""}>${label} <span aria-hidden="true">→</span></button>` : ""}</div>`;
const turn = (list, what) => { const o = list.filter(m => m !== viewer()); return o.length ? `<div class="turn"><span>${o.map(m => esc(mem(m).name) + "님").join(", ")}의 ${what}이 남았어요.</span><button class="btn sm" data-act="viewer" data-mid="${o[0]}">${esc(mem(o[0]).name)}님 차례로 바꾸기</button></div>` : ""; };
const oneDevice = () => `<div class="onedev"><b>한 기기에서 가족이 돌아가며 입력해요</b><span>아래 검은 막대의 <b>보는 사람</b>을 바꾸면 그 사람의 화면이 돼요. 실제 서비스에서는 가족마다 자기 휴대폰에서 알림을 받고 직접 입력해요.</span></div>`;
const exampleBtn = (act, extra = "") => S().scripts ? `<button class="btn sm" data-act="${act}" ${extra}>예시 답 넣기</button>` : "";

/* ---------- 화면 0: 가족방 만들기 ---------- */
function s0() {
  const s = S(), f = F(), host = f.room.host_member_id;
  if (s.setupDone) {
    const ivStarted = Object.values(s.iv).some(x => (x.answers || []).length);
    return `<div class="head"><div class="eyebrow">가족방 만들기</div><h1 class="h1">${esc(f.room.name)}</h1><p class="lead">${esc(mem(host).name)}님이 가족방을 만들었어요. 이제 가족의 이야기를 들어볼 차례예요.</p></div>
    ${oneDevice()}
    <div class="stackv">
     ${f.room.reason ? `<div class="card"><div class="ct">가족방을 만든 이유</div><p class="quote">${esc(f.room.reason)}</p><p class="qby">${esc(mem(host).name)} · ${esc(mem(host).role)}</p></div>` : ""}
     <div class="card"><div class="ct">참여한 가족 <span class="cs">${f.members.length}명</span></div>
      <div class="plist">${f.members.map(m => `<div class="prow">${av(m.member_id)}<div class="who"><div class="nm">${esc(m.name)} <span class="rl">· ${esc(m.role)} · ${m.age}세</span></div><div class="rl">${m.member_id === host ? "가족방을 만들었어요" : m.easy_mode ? "큰 글씨·쉬운 말로 참여" : "참여"}</div></div><span class="pill ${m.member_id === host ? "brand" : m.easy_mode ? "warm" : "good"}">${m.member_id === host ? "방장" : m.easy_mode ? "간편 모드" : "참여"}</span></div>`).join("")}</div>
      ${ivStarted ? `<p class="cs" style="margin-top:12px">각자의 생각을 듣기 시작해서 구성원은 바꿀 수 없어요. 바꾸려면 아래 검은 막대의 '처음부터'를 눌러 주세요.</p>` : `<button class="btn sm" style="margin-top:12px" data-act="edit-setup">구성원 고치기</button>`}</div>
    </div>${next("우리 가족 이야기 쓰기")}`;
  }
  const rows = f.members.map((m, i) => `<tr><td>${av(m.member_id, "sm")}</td>
    <td><input data-bind="members.${i}.name" value="${esc(m.name)}" placeholder="이름" maxlength="20"></td>
    <td><input data-bind="members.${i}.role" value="${esc(m.role)}" placeholder="예: 엄마, 남편, 장남" maxlength="12"></td>
    <td><input data-bind="members.${i}.age" data-num value="${m.age ?? ""}" placeholder="나이" inputmode="numeric" style="width:76px"></td>
    <td><label class="chkl"><input type="checkbox" data-bind="members.${i}.easy_mode" ${m.easy_mode ? "checked" : ""}> 간편 모드</label></td>
    <td>${f.members.length > 2 ? `<button class="btn sm" data-act="del-member" data-i="${i}" aria-label="빼기">빼기</button>` : ""}</td></tr>`).join("");
  return `<div class="head"><div class="eyebrow">가족방 만들기</div><h1 class="h1">함께 돈 이야기를 할 가족방을 만들어요</h1><p class="lead">가족방 이름과 함께할 가족을 적어 주세요. 이름은 별명이어도 괜찮아요.</p></div>
  ${oneDevice()}
  <section class="sec"><h2 class="st">가족방</h2>
   <div class="fgrid"><label>가족방 이름<input data-bind="room.name" value="${esc(f.room.name)}" placeholder="예: 우리 둘의 5년 계획" maxlength="30"></label>
   <label>가족방을 만든 이유<textarea data-bind="room.reason" maxlength="300" placeholder="예: 집을 먼저 살지 아이를 먼저 가질지 이야기할 때마다 결론 없이 끝났어요.">${esc(f.room.reason)}</textarea></label></div></section>
  <section class="sec"><h2 class="st">함께할 가족 <span class="cs">2~6명</span></h2>
   <div class="ftab-wrap"><table class="ftab"><thead><tr><th></th><th>이름</th><th>관계</th><th>나이</th><th>참여 방식</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
   <div class="row" style="margin-top:10px">${f.members.length < 6 ? `<button class="btn sm" data-act="add-member">가족 한 명 더하기</button>` : ""}
    <label class="inl">방장(가족방을 만든 사람) <select data-bind="room.host_member_id">${f.members.map(m => `<option value="${m.member_id}" ${m.member_id === host ? "selected" : ""}>${esc(m.name || "이름 없음")}</option>`).join("")}</select></label></div>
   <p class="cs" style="margin-top:8px">간편 모드는 스마트폰이 익숙하지 않은 분을 위한 방식이에요. AI가 더 짧고 쉬운 말로 묻고, 큰 글씨로 보여 줘요.</p></section>
  <div class="next"><span class="pno">— 1 —</span><span class="hint" id="setupHint"></span><button class="btn primary" data-act="setup-done">가족방 만들기 <span aria-hidden="true">→</span></button></div>`;
}

/* ---------- 화면 1: 우리 가족 이야기 ---------- */
function finRow(it, i) {
  const s = S(), f = F(), vw = viewer(), own = it.owner_id === vw;
  const d = f.disclosure[it.item_id] || "share";
  const kinds = CFG.kinds;
  const loan = it.kind === "loan";
  return `<tr>
   <td><select data-bind="finance.${i}.owner_id">${[["joint", "공동"], ...f.members.map(m => [m.member_id, m.name])].map(([v, l]) => `<option value="${v}" ${it.owner_id === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></td>
   <td><select data-bind="finance.${i}.kind">${Object.entries(kinds).map(([k, l]) => `<option value="${k}" ${it.kind === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></td>
   <td><input data-bind="finance.${i}.label" value="${esc(it.label)}" placeholder="이름(예: 월급)" maxlength="30"></td>
   <td><div class="amt-in"><input data-bind="finance.${i}.amount" data-num value="${it.amount ?? ""}" inputmode="decimal" placeholder="0"><span>만원${CFG.monthly_kinds.includes(it.kind) ? "/월" : ""}</span></div>
    ${loan ? `<div class="loanx"><select data-bind="finance.${i}.loan_type">${Object.entries(CFG.loan_types).map(([k, l]) => `<option value="${k}" ${it.loan_type === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
      <label>금리 <input data-bind="finance.${i}.rate" data-num value="${it.rate ?? ""}" inputmode="decimal" style="width:64px">%</label>
      ${it.loan_type !== "lease" ? `<label>월 상환액 <input data-bind="finance.${i}.payment" data-num value="${it.payment ?? ""}" inputmode="decimal" style="width:72px">만원</label>` : ""}</div>` : ""}</td>
   <td>${own ? `<span class="disc">${["share", "summary_only", "hide"].map(k => `<button class="${d === k ? "on" : ""}" data-act="disc" data-item="${it.item_id}" data-v="${k}">${{ share: "공개", summary_only: "합계만", hide: "숨김" }[k]}</button>`).join("")}</span>` : `<span class="cs">${{ share: "공개", summary_only: "합계만", hide: "숨김" }[d]}${it.owner_id !== "joint" ? `<br>(${esc(mem(it.owner_id).name)}님이 정해요)` : ""}</span>`}</td>
   <td><button class="btn sm" data-act="del-fin" data-i="${i}" aria-label="빼기">빼기</button></td></tr>`;
}
function s1() {
  const s = S(), f = F(), st = s.story, u = st.result, p = s.profile;
  const author = f.room.host_member_id;
  const rows = f.finance.map(finRow).join("");
  return `<div class="head"><div class="eyebrow">우리 가족 이야기</div><h1 class="h1">지금 가족의 상황을 편하게 들려주세요</h1><p class="lead">이야기는 AI가 정리하고, 숫자는 아래 표에 넣어요. 계산은 이 숫자로 계산엔진이 해요.</p></div>
  <div class="warnbox"><b>실제 계좌 정보나 정확한 금액은 넣지 마세요.</b> 체험판이라 대략적인 값이나 가상의 값으로 충분해요. 입력한 내용은 이 브라우저에만 저장돼요. AI가 정리할 때는 서버를 거쳐 AI(Anthropic Claude)에 보내지만, 이 서비스 서버에는 저장하지 않아요.</div>
  <section class="sec"><h2 class="st">${esc(mem(author).name)}님이 쓰는 우리 가족 이야기</h2>
   <textarea data-bind="story.text" data-reset="story" maxlength="1500" style="min-height:130px" placeholder="예: 결혼 1년 차 부부예요. 전세에 살고 있고, 2년 안에 아이를 갖고 싶어요. 남편은 집을 빨리 사자는 쪽이고 저는 아이가 먼저라는 생각이에요.">${esc(f.story.text)}</textarea>
   <p class="cs" style="margin-top:6px">가족의 단계, 사는 곳, 함께 이루고 싶은 것, 생각이 다른 부분을 써 주시면 좋아요. 1,500자까지.</p></section>
  <section class="sec"><h2 class="st">금융 정보 <span class="cs">단위 만원 · 체험용 값</span></h2>
   <p class="cs" style="margin-bottom:8px">실제 서비스에서는 마이데이터(흩어진 금융 정보를 내 동의로 모아 보는 방법)로 가져오고, 체험판에서는 직접 넣어요. 내 항목은 가족에게 보일 범위를 내가 골라요(공개 / 합계만 / 숨김). 숨긴 항목도 계산에는 들어가요.</p>
   <div class="ftab-wrap"><table class="ftab fin"><thead><tr><th>누구 것</th><th>종류</th><th>이름</th><th>금액</th><th>가족에게 보이기</th><th></th></tr></thead><tbody>${rows || `<tr><td colspan="6" class="cs" style="padding:14px">아직 항목이 없어요. 아래 버튼으로 더해 주세요.</td></tr>`}</tbody></table></div>
   <div class="row" style="margin-top:10px"><button class="btn sm" data-act="add-fin" data-kind="income">+ 매달 들어오는 돈</button><button class="btn sm" data-act="add-fin" data-kind="expense">+ 생활비</button><button class="btn sm" data-act="add-fin" data-kind="deposit">+ 예금·투자</button><button class="btn sm" data-act="add-fin" data-kind="loan">+ 대출</button><button class="btn sm" data-act="add-fin" data-kind="home">+ 집·보증금</button></div></section>
  <section class="sec"><h2 class="st">AI가 이해한 내용</h2>
   ${!started(st) && st.status !== "error" ? `<button class="btn primary" data-act="understand">이야기와 금융 정보 정리 맡기기</button>` : ""}
   ${pend(st, "AI가 이야기를 읽고 있어요", "understand")}
   ${u ? `<div>${[["가족 단계", u.family_stage], ["사는 곳", u.living], ["함께 이루고 싶은 것", u.shared_goal], ["생각이 다른 부분", (u.differences || []).join(" · ")]].map(r => `<div class="urow"><span>${r[0]}</span><b>${esc(r[1])}</b></div>`).join("")}</div>${vbadge(st.verification, st.calls)}` : ""}
   ${p && u ? `<div class="urow"><span>한 달 들어오는 돈</span><b>${won(p.income_total)}</b></div><div class="urow"><span>한 달 나가는 돈</span><b>${won(p.expense_total)}${p.loan_payment_total ? ` · 대출 상환 ${won(p.loan_payment_total)}` : ""}</b></div><div class="urow"><span>예금·투자</span><b>${won(p.liquid_total)}</b></div><p class="cs">합계는 AI가 아니라 코드가 계산했어요.</p>` : ""}
  </section>${next("각자의 생각 듣기", !(u && u.family_stage), "AI 정리를 받으면 다음으로 넘어갈 수 있어요")}`;
}

/* ---------- 화면 2: 각자의 생각 ---------- */
const ivState = mid => { const s = S(); return s.iv[mid] || (s.iv[mid] = { answers: [], review: {}, resolve: {}, clar: null, review2: {}, summary: null, confirmed: false }); };
const qText = (mid, i) => { const q = CFG.questions[i]; return mem(mid).easy_mode ? q.easy : q.text; };
function qaOf(mid) { return ivState(mid).answers.map((a, i) => [qText(mid, i), a]); }
async function finishInterview(mid) {
  const st = ivState(mid);
  await run(st.review, "/api/interview/review", { family: F(), member_id: mid, qa: qaOf(mid) });
  if (st.review.status !== "done") return;
  const r = st.review.result;
  if (r.ambiguous && r.ambiguous.length) st.clar = { state: "asking" };
  else st.summary = r;
  render();
}
async function answerClar(mid, idx, text) {
  const st = ivState(mid), d = st.review.result;
  if (idx === d.choices.length - 1) { st.clar = { state: "later", choice: idx }; st.summary = null; render(); return; }
  const sc = S().scripts?.clarify;
  const answer = text || (sc && sc.member_id === mid && idx === 0 && sc.answer ? sc.answer : d.choices[idx]);
  st.clar = { state: "resolving", choice: idx, answer };
  await run(st.resolve, "/api/interview/resolve", { family: F(), member_id: mid, detect: d, answer });
  if (st.resolve.status === "done" && st.resolve.result.resolved) {
    const word = d.ambiguous[0].word, meaning = st.resolve.result.meaning;
    st.clar = { state: "done", choice: idx, answer, meaning, word };
    st.confirmed = false;
    await run(st.review2, "/api/interview/review", { family: F(), member_id: mid, qa: qaOf(mid), clarification: { word, meaning } });
    if (st.review2.status === "done") st.summary = st.review2.result;
  } else if (st.resolve.status === "done") {
    st.clarTries = (st.clarTries || 0) + 1;
    if (st.clarTries >= 2) st.clar = { state: "later", choice: idx, answer };
    else { st.clar = { state: "asking", retry: true, lastAnswer: answer }; st.resolve = {}; }
  }
  render();
}
function chatHtml(mid) {
  const m = mem(mid), st = ivState(mid);
  const ai = t => `<div class="msg ai"><span class="aimark">${AIMARK}</span><div><div class="who-l">AI 상담사</div><div class="bub">${t}</div></div></div>`;
  const me = t => `<div class="msg me">${av(mid, "sm")}<div><div class="who-l">${esc(m.name)}</div><div class="bub">${esc(t)}</div></div></div>`;
  let h = ai(`${esc(m.name)}님, 안녕하세요. 세 가지만 여쭤볼게요. 이 대화는 ${esc(m.name)}님만 볼 수 있어요.`);
  st.answers.forEach((a, i) => { h += ai(esc(qText(mid, i))) + me(a); });
  if (st.answers.length < CFG.questions.length) h += ai(esc(qText(mid, st.answers.length)));
  else if (!started(st.review) && st.review.status !== "error") h += `<div class="sysnote">세 가지 질문에 모두 답했어요</div>`;
  h += pend(st.review, "AI가 대화를 정리하고 있어요", `retry-review:${mid}`);
  const d = st.review.result;
  if (d && d.ambiguous && d.ambiguous.length && st.clar) {
    h += ai(esc(d.question));
    h += ai(esc(d.easy_question));
    const picked = st.clar.choice;
    h += `<div class="choices">${d.choices.map((t, i) => `<button class="choice ${picked === i ? "on" : ""} ${i === d.choices.length - 1 ? "muted" : ""}" data-act="clar" data-mid="${mid}" data-i="${i}" ${st.clar.state !== "asking" || mid !== viewer() ? "disabled" : ""}><span class="n">${i + 1}</span>${esc(t)}</button>`).join("")}</div>`;
    if (st.clar.retry && st.clar.state === "asking") h += me(st.clar.lastAnswer) + ai("제가 잘 알아듣지 못했어요. 아래에서 가까운 것을 골라 주시거나, 조금 더 자세히 말씀해 주세요.");
    if (st.clar.answer && st.clar.state !== "asking") h += me(st.clar.answer);
    h += pend(st.resolve, "AI가 답을 확인하고 있어요", `retry-resolve:${mid}`);
    if (st.clar.state === "done") h += ai(esc(st.resolve.result.confirm_message)) + me("네, 맞아요.");
    if (st.clar.state === "later") h += ai("괜찮아요. 편하실 때 다시 답해 주세요. 이 말의 뜻이 정해지기 전에는 AI가 짐작해서 계산하지 않아서, 요약도 그때 함께 공유해요.");
    h += pend(st.review2, "AI가 요약을 다시 만들고 있어요", `retry-review2:${mid}`);
  }
  const sm = st.summary;
  if (sm) h += ai(`가족에게 공유할 요약을 만들었어요. 확인해 주세요.<div class="sumcard"><dl><dt>꼭 지키고 싶은 것</dt><dd>${esc(sm.keep)}</dd><dt>양보할 수 있는 것</dt><dd>${esc(sm.flexible)}</dd><dt>가장 큰 걱정</dt><dd>${esc(sm.worry)}</dd></dl></div>${vbadge((st.review2.verification) || st.review.verification, st.review2.calls || st.review.calls)}`);
  return h;
}
function s2() {
  const s = S(), vw = viewer(), m = mem(vw), st = ivState(vw);
  let action = "";
  if (st.answers.length < CFG.questions.length) {
    const ex = s.scripts?.answers?.[vw]?.[st.answers.length];
    action = `<textarea id="ans" maxlength="500" placeholder="${esc(m.name)}님의 답을 적어 주세요">${esc(st.draft || "")}</textarea><div class="crow">${ex ? `<button class="btn sm" data-act="fill-ans">예시 답 넣기</button>` : ""}<button class="btn primary sm" data-act="send-ans">보내기</button></div>`;
  } else if (!started(st.review) && st.review.status !== "error") action = `<button class="btn primary" data-act="finish" data-mid="${vw}">대화 마치고 AI 요약 받기</button>`;
  else if (st.clar?.state === "asking") action = `<input id="clarTxt" placeholder="또는 직접 적어 주세요" maxlength="200"><button class="btn sm" data-act="clar-text" data-mid="${vw}">보내기</button>`;
  else if (st.clar?.state === "later") action = `<span class="cs">질문에 답해야 요약을 공유할 수 있어요. 다른 가족이 먼저 이야기해도 괜찮아요.</span><button class="btn primary sm" data-act="clar-resume" data-mid="${vw}">지금 답하기</button>`;
  else if (st.summary && !st.confirmed) action = `<button class="btn primary" data-act="confirm" data-mid="${vw}">요약 확인하고 가족에게 공유하기</button>`;
  else if (st.confirmed) action = `<span class="cs">✓ 요약을 가족에게 공유했어요</span>`;
  const fam = F().members.map(x => {
    const xs = ivState(x.member_id), sm = xs.summary;
    const pending = xs.clar && xs.clar.state !== "done";
    let body;
    if (xs.confirmed && sm) body = `<dl><dt>꼭 지키고 싶은 것</dt><dd>${esc(sm.keep)}${pending ? ` <span class="pend">· 뜻을 여쭤보는 중</span>` : ""}</dd><dt>양보할 수 있는 것</dt><dd>${esc(sm.flexible)}</dd><dt>가장 큰 걱정</dt><dd>${esc(sm.worry)}</dd></dl>
      <div class="meta"><span>✓ 본인 확인 후 공유</span>${xs.clar?.state === "done" ? "<span>AI가 한 번 더 여쭤보고 정리했어요</span>" : ""}${x.member_id !== vw ? "<span>🔒 대화 내용 비공개</span>" : ""}</div>`;
    else if (xs.review.status === "loading") body = `<div class="pending"><span class="spin"></span>AI가 정리하고 있어요</div>`;
    else body = `<div class="cs" style="margin:8px 0 0 44px">${xs.clar?.state === "later" ? "AI가 한 가지를 다시 여쭤보는 중이에요(나중에 답하기)" : xs.clar?.state === "asking" ? "AI가 한 가지를 다시 여쭤보는 중이에요" : xs.answers.length ? `대화 중이에요(${xs.answers.length}/${CFG.questions.length})` : "아직 대화하지 않았어요"}</div>`;
    return `<div class="fm"><div class="fh">${av(x.member_id)}<span class="nm">${esc(x.name)}</span><span class="rl">${esc(x.role)}</span>${x.member_id === vw ? '<span class="me">나</span>' : ""}</div>${body}</div>`;
  }).join("");
  const left = mids().filter(x => !ivState(x).confirmed);
  return `<div class="head"><div class="eyebrow">각자의 생각</div><h1 class="h1">가족 한 사람씩 AI 상담사와 따로 이야기해요</h1><p class="lead">AI 상담사가 가족 모두에게 같은 세 가지를 물어요. 뜻이 분명하지 않은 말이 있으면 AI가 그 사람에게만 다시 여쭤봐요.</p></div>
  <div class="privacy"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" stroke-width="2" style="margin-top:2px"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg><div><b>대화 내용은 본인만 볼 수 있어요</b><span>가족에게는 AI가 정리하고 본인이 확인한 요약만 공유돼요. 공유 단계의 AI에도 원문 대화는 들어가지 않아요. 체험판에서는 같은 기기를 쓰니, 다른 사람 차례에는 화면을 넘겨 주세요.</span></div></div>
  <div class="cols keep2">
   <div class="chatwin"><div class="chatbar"><span class="aimark">${AIMARK}</span><div class="cb"><b>AI 상담사</b><span>${esc(m.name)}님과의 1:1 대화 · 나만 볼 수 있어요</span></div>${m.easy_mode ? `<span class="easy">간편 모드 · 큰 글씨</span>` : ""}</div>
    <div class="chat ${m.easy_mode ? "big" : ""}" id="chat">${chatHtml(vw)}</div>
    <div class="composer ${st.answers.length < CFG.questions.length ? "col" : ""}" style="justify-content:flex-end">${action}</div></div>
   <div class="card"><div class="ct">가족 모두의 의견</div><div class="cs" style="margin-bottom:8px">AI가 정리하고 본인이 확인한 요약이에요</div><div class="fam">${fam}</div>${turn(left, "대화")}</div>
  </div>${next("가족 모두의 생각 함께 보기", left.length > 0, "가족 모두 요약을 공유하면 다음으로 넘어갈 수 있어요")}`;
}

/* ---------- 화면 3: 공동 목표 설정 ---------- */
const sideOf = x => x < .34 ? 0 : x > .66 ? 2 : 1;
function camp(is) {
  const lv = { small: [1, "작음"], medium: [2, "보통"], large: [3, "큼"] }[is.gap_level] || [2, "보통"];
  const cols = [is.left_label, "중간", is.right_label].map((lab, c) => {
    const who = Object.entries(is.positions).filter(([, x]) => sideOf(x) === c).map(([m]) => m);
    return `<div class="cp ${c === 1 ? "mid" : ""}"><div class="cl">${esc(lab)}</div><div class="cw">${who.length ? who.map(m => `<div class="nmv"><i style="background:${MC[memIdx(m) % MC.length]}"></i>${esc(mem(m).name)}</div>`).join("") : `<span class="none">—</span>`}</div></div>`;
  }).join("");
  return `<div class="camp-h"><h4>${esc(is.title)}</h4><span class="gap">생각 차이 · ${lv[1]}<span class="sq">${[1, 2, 3].map(k => `<i class="${k <= lv[0] ? "on" : ""}"></i>`).join("")}</span></span></div><div class="camps">${cols}</div><p class="ailine">${esc(is.note)}</p>`;
}
const summariesOf = () => Object.fromEntries(mids().map(m => [m, ivState(m).summary ? { keep: ivState(m).summary.keep, flexible: ivState(m).summary.flexible, worry: ivState(m).summary.worry } : null]).filter(x => x[1]));
const clarList = () => mids().filter(m => ivState(m).clar?.state === "done").map(m => ({ member_id: m, word: ivState(m).clar.word, meaning: ivState(m).clar.meaning }));
function goalForm() {
  const s = S(), g = s.goalForm, f = F(), chk = s.goalChk;
  const hasLoan = f.finance.some(x => x.kind === "loan" && x.loan_type !== "lease");
  return `<div class="gform">
   <label>무엇을 계산할까요<select data-gf="type">${Object.entries(GT).filter(([k]) => k !== "debt_free" || hasLoan).map(([k, l]) => `<option value="${k}" ${g.type === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
   <label>목표 이름<input data-gf="label" value="${esc(g.label || "")}" maxlength="40"></label>
   ${g.type === "reach_target" ? `<label>목표 금액<div class="amt-in"><input data-gf="target_amount" data-num value="${g.target_amount ?? ""}" inputmode="decimal"><span>만원</span></div></label>` : ""}
   ${g.type === "reach_target" ? `<label>언제까지(선택)<div class="amt-in"><input data-gf="within_years" data-num value="${g.within_months ? g.within_months / 12 : ""}" inputmode="decimal"><span>년 안</span></div></label>` : ""}
   ${g.type === "runway" ? `<label>누구 나이로 볼까요<select data-gf="base_member_id">${f.members.map(m => `<option value="${m.member_id}" ${g.base_member_id === m.member_id ? "selected" : ""}>${esc(m.name)}(${m.age}세)</option>`).join("")}</select></label>` : ""}
  </div>${g.target_note ? `<p class="cs" style="color:var(--warm)">${esc(g.target_note)}</p>` : ""}
  <div class="row" style="margin-top:10px">${s.scripts?.goal_form && chk.status !== "done" ? `<button class="btn sm" data-act="fill-goal">예시 값 넣기</button>` : ""}${chk.status === "done" ? `<span class="cs">✓ 계산할 수 있는 목표예요. 지금 모여 있는 돈 ${won(chk.goal.start_pool)}(${esc(chk.goal.pool_label)})에서 시작해, 앞으로 ${chk.goal.horizon_months / 12}년 동안을 달마다 계산해서 ${g.type === "reach_target" ? "목표에 닿는 때" : g.type === "runway" ? "예금이 바닥나는 때" : "대출을 다 갚는 때"}를 찾아요.</span>` : `<button class="btn sm" data-act="goal-check">이 목표로 계산할 수 있는지 확인</button>`}</div>${pend(chk, "확인하고 있어요")}`;
}
const hasBatchim = w => { const c = (w || "").trim().slice(-1).charCodeAt(0); return c >= 0xac00 && c <= 0xd7a3 ? (c - 0xac00) % 28 !== 0 : false; };
function replyChips(mid) {
  const keep = (ivState(mid).summary || {}).keep || "";
  const k = keep.replace(/[.!?。]+$/, "").trim();
  return ["좋아요. 그렇게 해 봐요.",
    ...(k && k.length <= 18 && !/[.?!…]/.test(k) ? [`좋아요. 다만 '${k}'${hasBatchim(k) ? "은" : "는"} 꼭 지켰으면 해요.`]
      : ["좋아요. 다만 제가 꼭 지키고 싶은 것도 함께 지켜졌으면 해요."]),
    "조금 더 이야기해 보고 싶어요."];
}
function s3() {
  const s = S(), g = s.goal, vw = viewer();
  const head = r => `<div class="head"><div class="eyebrow">공동 목표 설정</div>${r ? `<p class="big">${esc(r.headline)}</p>` : `<h1 class="h1">가족의 생각을 함께 읽고 있어요</h1>`}</div>`;
  if (!mids().every(m => ivState(m).confirmed)) return head() + `<div class="aibox"><p class="q">아직 모든 가족의 요약이 모이지 않았어요.</p></div>` + next("", true, "");
  const lockBy = mids().find(m => ivState(m).clar && ivState(m).clar.state !== "done");
  if (lockBy) {
    const w = ivState(lockBy).review.result.ambiguous[0].word;
    return head() + `<section class="sec"><h2 class="st">AI의 제안을 준비하고 있어요</h2><div class="aibox"><p class="q">${esc(mem(lockBy).name)}님이 말씀하신 '${esc(w)}'의 뜻을 아직 확인하지 못했어요.</p><p class="sub">AI는 짐작해서 계산하지 않아요. 다른 가족에게 묻지 않고, ${esc(mem(lockBy).name)}님께 1:1 대화로 다시 여쭤본 뒤 제안을 만들어요.</p></div><div class="actrow"><button class="btn primary" data-act="reask" data-mid="${lockBy}">${esc(mem(lockBy).name)}님께 1:1로 다시 여쭤보기</button></div></section>` + next("방법별로 미래 계산하기", true, "확인이 필요한 말이 해결되면 이어서 진행돼요");
  }
  if (s.story.status !== "done") return head() + `<div class="aibox"><p class="q">우리 가족 이야기의 AI 정리가 먼저 필요해요.</p></div><div class="actrow"><button class="btn" data-act="go" data-i="1">우리 가족 이야기로 가기</button></div>`;
  if (!started(g) && g.status !== "error") setTimeout(() => run(g, "/api/goal/analyze", { family: F(), summaries: summariesOf(), story_understanding: s.story.result, clarifications: clarList() }), 0);
  if (g.status !== "done") return head() + pend(g.status ? g : { status: "loading" }, "AI가 쟁점을 정리하고 공동 목표를 제안하고 있어요", "retry-goal");
  const r = g.result, p = r.proposal;
  const replied = mids().filter(m => s.replies[m] != null);
  const allReplied = p && p.to.every(m => s.replies[m] != null);
  const crit = s.criterion;
  if (allReplied && !started(crit) && crit.status !== "error") setTimeout(() => run(crit, "/api/goal/criterion", { family: F(), proposal: p.text, replies: s.replies, summaries: summariesOf(), story_understanding: s.story.result }, res => { s.goalForm = { ...res.result.goal }; }), 0);
  const ready = s.goalChk.status === "done";
  const allApproved = ready && mids().every(m => s.approvals[m]);
  const ex = s.scripts?.replies?.[vw];
  return head(r) + `
  <section class="sec"><h2 class="st">이미 같은 생각인 부분</h2><ul class="agree">${r.agreed_points.map(a => `<li><span class="chk">✓</span><span>${esc(a)}</span></li>`).join("")}</ul></section>
  <section class="sec"><h2 class="st">생각이 갈리는 부분</h2><p class="cs" style="margin-bottom:6px">AI가 확인된 요약을 바탕으로 각자의 생각이 어디쯤인지 정리했어요(대화 원문은 쓰지 않아요)</p>${r.issues.map(is => `<div class="issue">${camp(is)}</div>`).join("")}</section>
  <section class="sec"><h2 class="st">1단계 · AI의 제안</h2>
   ${p ? `<div class="aibox"><p class="q">${esc(p.text)}</p><div class="to">받는 사람 ${p.to.map(m => av(m, "sm")).join("")} ${p.to.map(m => esc(mem(m).name) + "님").join(", ")}</div></div>${vbadge(g.verification, g.calls)}` : `<div class="failbox"><b>제안을 만들지 못했어요</b><button class="btn sm" data-act="retry-goal">다시 시도</button></div>`}
   ${replied.length ? `<div class="replies">${replied.map(m => `<div class="reply">${av(m, "sm")}<div><b>${esc(mem(m).name)}님의 답${m === vw ? " (나)" : ""}</b>${esc(s.replies[m])}</div></div>`).join("")}</div>` : ""}
   ${p && p.to.includes(vw) && s.replies[vw] == null ? `<div class="act"><div class="rl">${av(vw, "sm")}${esc(mem(vw).name)}님의 답을 남겨 주세요</div><div class="chips">${replyChips(vw).map(t => `<button class="chip" data-act="reply-chip" data-t="${esc(t)}">${esc(t)}</button>`).join("")}</div><textarea id="myReply" maxlength="500" placeholder="추천 문구를 누르거나 직접 적어 주세요"></textarea><div class="row"><span style="flex:1"></span>${ex ? `<button class="btn sm" data-act="fill-reply">예시 답 넣기</button>` : ""}<button class="btn primary sm" data-act="reply">답 보내기</button></div></div>` : ""}
   ${p ? turn(p.to.filter(m => s.replies[m] == null), "답") : ""}
  </section>
  ${allReplied ? `<section class="sec"><h2 class="st">2단계 · 가족 모두의 동의</h2><p class="cs" style="margin-bottom:10px">답을 바탕으로 AI가 정리한 기준이에요. 계산할 목표는 가족이 직접 고칠 수 있어요. 가족 모두가 동의해야 이 기준으로 계산해요.</p>
   ${pend(crit, "AI가 기준 문장을 정리하고 있어요", "retry-criterion")}
   ${crit.result && s.goalForm ? `<div class="aibox"><p class="q">${esc(crit.result.criterion)}</p></div>${vbadge(crit.verification, crit.calls)}
   <h3 class="st3">계산할 목표</h3>${goalForm()}
   ${ready ? `<div class="agreelist">${F().members.map(m => `<div class="agr">${av(m.member_id)}<div><div class="nm">${esc(m.name)}</div><div class="cm">${s.approvals[m.member_id] ? "동의했어요" : "아직 답하지 않았어요"}</div></div>${m.member_id === vw && !s.approvals[vw] ? `<button class="btn primary sm" data-act="approve">동의해요</button>` : `<span class="agbtn ${s.approvals[m.member_id] ? "on" : ""}">${s.approvals[m.member_id] ? "✓ 동의" : "대기 중"}</span>`}</div>`).join("")}</div>
   ${allApproved ? `<p class="okline"><span class="chk">✓</span><span><b>가족 모두 이 기준에 동의했어요.</b> 이 기준으로 방법을 설계하고 계산할게요.</span></p>` : turn(mids().filter(m => !s.approvals[m]), "동의")}` : ""}` : ""}</section>` : ""}
  ${next("방법별로 미래 계산하기", !allApproved, "가족 모두 동의하면 다음으로 넘어갈 수 있어요")}`;
}

/* ---------- 화면 4: 미래 계산 ---------- */
const results = () => { const d = S().design; return d.simulation ? d.simulation.results : []; };
const resultOf = i => { const s = S(), r = results()[i]; return s.override[i] || r; };
const goalNow = () => S().goalChk.goal;
const baseYear = () => +F().today.slice(0, 4);
function chart(r, goal) {
  const W = 760, H = 340, L = 64, Rr = 96, T0 = 34, B = 44, horizon = goal.horizon_months, yrs = horizon / 12;
  const debt = goal.type === "debt_free";
  const p = debt ? [r.start_debt, ...r.yearly.map(y => y.debt_end)] : [r.yearly[0].start, ...r.yearly.map(y => y.end)];
  const target = goal.type === "reach_target" ? goal.target_amount : 0;
  let mn = Math.min(0, ...p, target), mx = Math.max(...p, target, 1);
  const nice = x => { const q = Math.pow(10, Math.floor(Math.log10(x || 1))), f = x / q; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * q; };
  const st = nice((mx - mn) / 3); mn = Math.floor(mn / st) * st; mx = Math.ceil(mx / st) * st;
  const X = t => L + (W - L - Rr) * t / yrs, Y = v => T0 + (H - T0 - B) * (1 - (v - mn) / (mx - mn));
  const ageAxis = goal.type === "runway", by = baseYear(), ba = goal.base_age;
  let g = "";
  for (let v = mn; v <= mx + 1e-6; v += st) g += `<line x1="${L}" x2="${W - Rr}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${L - 12}" y="${Y(v) + 5}" text-anchor="end" font-size="14" fill="var(--ink2)">${v === 0 ? "0원" : eokS(v) + "원"}</text>`;
  const xs = yrs <= 12 ? 2 : yrs <= 25 ? 5 : 10;
  for (let t = 0; t <= yrs; t += xs) g += `<text x="${X(t)}" y="${H - 14}" text-anchor="middle" font-size="14" fill="var(--ink2)">${t === 0 ? (ageAxis ? `지금 ${ba}세` : "지금") : ageAxis ? (ba + t) + "세" : (by + t) + "년"}</text>`;
  (r.basis || []).filter(b => b.key.startsWith("event:")).forEach(b => {
    const m = /(\d+)~(\d+)/.exec(b.detail || ""); if (!m) return;
    const x1 = X(+m[1] / 12), x2 = X(Math.min(+m[2], horizon) / 12);
    g += `<rect x="${x1}" y="${T0}" width="${Math.max(2, x2 - x1)}" height="${H - T0 - B}" fill="var(--warm)" opacity=".1"/><text x="${x1 + 8}" y="${T0 + 18}" font-size="13.5" font-weight="600" fill="var(--warm)">${esc(b.label)}</text>`;
  });
  (r.basis || []).filter(b => b.key.startsWith("lump:")).forEach(b => {
    const m = +(/\d+/.exec(b.detail) || [0])[0], x = X(m / 12);
    g += `<line x1="${x}" x2="${x}" y1="${T0 + 26}" y2="${H - B}" stroke="var(--ink2)" stroke-dasharray="2 4"/><text x="${x + 8}" y="${H - B - 14}" font-size="13.5" font-weight="600" fill="var(--ink2)">${esc(b.label)} ${esc(b.display)}</text>`;
  });
  const gy = Y(target), gc = goal.type === "runway" ? "var(--bad)" : "var(--green)";
  g += `<line x1="${L}" x2="${W - Rr}" y1="${gy}" y2="${gy}" stroke="${gc}" stroke-dasharray="6 5" stroke-width="2"/><text x="${W - Rr + 10}" y="${gy + 5}" font-size="14" font-weight="700" fill="${gc}">${goal.type === "reach_target" ? "목표 " + eokS(target) : debt ? "대출 0원" : "예금 0원"}</text>`;
  const dd = p.map((v, j) => `${j ? "L" : "M"}${X(j).toFixed(1)},${Y(v).toFixed(1)}`).join("");
  g += `<path d="${dd}" fill="none" stroke="var(--ink)" stroke-width="3.5" stroke-linejoin="round" stroke-linecap="round"/>`;
  g += `<circle cx="${X(0)}" cy="${Y(p[0])}" r="5" fill="var(--ink)"/><text x="${X(0) + 10}" y="${Y(p[0]) - 12}" font-size="14" fill="var(--ink2)">지금 ${eokS(p[0])}원</text>`;
  const lx = X(p.length - 1), ly = Y(p[p.length - 1]);
  g += `<circle cx="${lx}" cy="${ly}" r="5" fill="var(--ink)"/><text x="${lx + 10}" y="${ly + 5}" font-size="14" font-weight="700" fill="var(--ink)">${eokS(p[p.length - 1])}원</text>`;
  if (r.goal_hit_month) {
    const hx = X(r.goal_hit_month / 12), ty = gy - 22, bx = Math.min(Math.max(hx, L + 122), W - Rr - 42);
    const lab = goal.type === "reach_target" ? `${r.goal_hit_display} 뒤 목표에 닿아요` : debt ? `${r.goal_hit_display} 뒤 다 갚아요` : `${ba + Math.floor(r.goal_hit_month / 12)}세쯤 예금이 바닥나요`;
    g += `<circle cx="${hx}" cy="${gy}" r="8" fill="var(--paper)" stroke="${gc}" stroke-width="3"/><rect x="${bx - 120}" y="${ty - 22}" width="240" height="30" fill="var(--paper)" stroke="${gc}" stroke-width="1.5"/><text x="${bx}" y="${ty - 2}" text-anchor="middle" font-size="15" font-weight="700" fill="${gc}">${esc(lab)}</text>`;
  }
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="해마다 달라지는 금액">${g}</svg>`;
}
function kpiNote(r, goal) {
  if (goal.type === "reach_target") return goal.within_months ? (r.goal_hit_month && r.goal_hit_month <= goal.within_months ? `목표한 ${goal.within_months / 12}년 안이에요` : `목표한 ${goal.within_months / 12}년을 넘겨요`) : "";
  if (goal.type === "runway") { const b = mem(goal.base_member_id); return r.goal_hit_month ? `${esc(b.name)}님 ${goal.base_age + Math.floor(r.goal_hit_month / 12)}세쯤 다 써요` : `${esc(b.name)}님 ${goal.base_age + goal.horizon_months / 12}세 이후까지 남아요`; }
  return "";
}
function kpiOk(r, goal) {
  if (goal.type === "reach_target") return !!r.goal_hit_month && (!goal.within_months || r.goal_hit_month <= goal.within_months);
  if (goal.type === "runway") return !r.goal_hit_month;
  return !!r.goal_hit_month;
}
function s4() {
  const s = S(), d = s.design, goal = goalNow();
  const head = `<div class="head"><div class="eyebrow">미래 계산</div><h1 class="h1">방법별로 앞으로 어떻게 될지 계산했어요</h1><p class="lead">AI가 공동 목표와 가족의 금융 정보로 방법 세 가지를 설계하고, 계산은 별도의 계산엔진이 해요. AI가 정한 조건은 서버가 가족의 숫자와 대조해 검사하고, AI의 설명 속 숫자는 계산 결과와 대조해요.</p></div>`;
  if (!goal || !mids().every(m => s.approvals[m])) return head + `<div class="aibox"><p class="q">가족 모두 동의한 공동 목표가 먼저 필요해요.</p></div>`;
  if (!started(d) && d.status !== "error") setTimeout(() => run(d, "/api/options/design", { family: F(), goal: s.goalForm, criterion: s.criterion.result.criterion, summaries: summariesOf() }), 0);
  if (d.status !== "done") return head + pend(d.status ? d : { status: "loading" }, "AI가 방법을 설계하고 계산엔진으로 계산하고 있어요(30초쯤 걸릴 수 있어요)", "retry-design");
  const g = d.goal || goal;
  const i = Math.min(s.pick, d.specs.length - 1), sp = d.specs[i], r = resultOf(i), interp = (d.interpretation || {})[sp.option_id] || {};
  const changes = (d.views || []).find(v => v.option_id === sp.option_id)?.changes || [];
  const ok = kpiOk(r, g);
  const hasLoan = r.yearly.some(y => y.loan_payment);
  const yr = r.yearly.map(y => `<tr><td>${g.type === "runway" ? (g.base_age + y.year) + "세" : (baseYear() + y.year) + "년"}</td><td>${won(y.start)}</td><td>${(y.net_flow > 0 ? "+" : "") + won(y.net_flow)}</td><td>${y.interest > 0 ? "+" + won(y.interest) : "0원"}</td>${hasLoan ? `<td>${won(y.loan_payment)}</td><td>${won(y.debt_end)}</td>` : ""}<td><b>${won(y.end)}</b></td><td>${won(y.net_worth_end)}</td></tr>`).join("");
  const ret = r.basis.find(b => b.key === "return").value;
  return head + `
  <section class="sec"><h2 class="st">AI가 설계한 방법</h2><div class="optlist"><div class="opt-h"><span></span><span>방법</span><span>${METRIC[g.type]}</span></div>
   ${d.specs.map((x, k) => `<button class="opt" data-act="pick" data-i="${k}" style="--c:${OC[k]}" aria-pressed="${k === i}"><span class="radio"></span><span><span class="ol">${esc(x.option_id)}. ${esc(x.label)}</span><span class="od">${esc(x.description)}</span></span><span class="res num">${esc(resultOf(k).goal_hit_display)}</span></button>`).join("")}</div>
   ${(d.design_notes || []).length ? `<p class="cs" style="margin-top:8px">설계 의도: ${d.design_notes.map(n => `${esc(n.option_id)} ${esc(n.intent)}`).join(" · ")}</p>` : ""}</section>
  <section class="sec"><h2 class="st">${esc(sp.option_id)}. ${esc(sp.label)}를 고르면</h2>
   ${interp.easy ? `<div class="aibox easybox"><p><b>쉽게 말하면</b> ${esc(interp.easy)}</p></div>` : ""}${vbadge(d.verification, d.calls)}
   <div class="kpis"><div class="kpi ${ok ? "good" : "bad"}"><div class="kl">${METRIC[g.type]}</div><div class="kv">${esc(r.goal_hit_display)}</div><div class="kn">${kpiNote(r, g)}</div></div>
    <div class="kpi"><div class="kl">첫 달에 늘거나 줄어드는 돈</div><div class="kv" style="font-size:22px">${(r.monthly_flow > 0 ? "+" : "") + won(r.monthly_flow)}</div></div>
    <div class="kpi"><div class="kl">돈을 불리는 방식</div><div class="kv" style="font-size:19px;line-height:1.4;margin-top:4px">${T("수익률")} 연 ${ret}%</div></div></div>
   <div class="chg2"><b>이 방법이 바꾼 것</b><ul>${changes.map(c => `<li>${esc(c)}</li>`).join("")}</ul></div>
   <div class="chart-wrap">${chart(r, g)}</div>
   <p class="readme">${g.type === "reach_target" ? "선이 올라갈수록 모인 돈이 많아요. 선이 점선(목표)에 닿는 때가 목표를 이루는 때예요." : g.type === "runway" ? "선은 예금에 남은 돈이에요. 아래 점선(0원)에 닿으면 예금을 다 쓴 거예요." : "선은 남은 대출이에요. 아래 점선(0원)에 닿으면 대출을 다 갚은 거예요."}</p>
   ${r.range ? `<details class="tune"><summary>운이 좋을 때와 나쁠 때도 보기(보조 정보)</summary><p class="cs" style="margin-top:8px">같은 계획을 ${r.range.paths}번, 매번 다른 경기 상황을 가정해 계산했어요. ${g.type === "reach_target" ? `운이 좋으면 ${r.range.p10_hit_month ? (r.range.p10_hit_month / 12).toFixed(1) + "년" : "-"}, 보통 ${r.range.p50_hit_month ? (r.range.p50_hit_month / 12).toFixed(1) + "년" : "-"}, 운이 나쁘면 ${r.range.p90_hit_month ? (r.range.p90_hit_month / 12).toFixed(1) + "년" : "기간 안에 못 모임"}${g.within_months ? ` · ${g.within_months / 12}년 안에 모일 가능성 ${Math.round(r.range.prob_reach_within * 100)}%` : ""}` : `끝까지 예금이 남을 가능성 ${Math.round((r.range.prob_last_through ?? 0) * 100)}%`}</p></details>` : ""}
  </section>
  <section class="sec"><h2 class="st">이렇게 계산했어요</h2>
   <table class="btab"><thead><tr><th>항목</th><th>값</th><th>어디서 나왔나요</th></tr></thead><tbody>${r.basis.map(b => `<tr><td class="bk">${esc(b.label)}</td><td class="bv num">${esc(b.display)}</td><td class="bd">${esc(b.detail || "")}<span class="src">${esc({ financial_snapshot: "가족이 넣은 금융정보", option: "AI가 고른 방법", goal_setting: "공동 목표", assumption: "가정" }[b.source] || (b.source.startsWith("assumption") ? "가정(공개)" : b.source))}</span></td></tr>`).join("")}</tbody></table>
   <p class="how2"><b>계산 방법</b> 매달 ① 남아 있는 돈에 한 달 치 이자를 붙이고 ② 그달에 늘거나 줄어드는 돈(생활비에는 ${T("물가")} 오름 반영)과 대출 상환을 더하고 빼요. 이걸 ${g.horizon_months}개월 동안 반복했어요. 세금은 넣지 않았고, 수익률·물가·주택연금은 공개된 가정값이에요.</p>
   <details class="tune"><summary>해마다 계산한 표 보기</summary><div class="ytab-wrap"><table class="ytab num"><thead><tr><th>${g.type === "runway" ? esc(mem(g.base_member_id).name) + "님 나이" : "연도"}</th><th>해의 시작</th><th>늘거나 줄어든 돈</th><th>이자로 불어난 돈</th>${hasLoan ? "<th>대출 상환</th><th>남은 대출</th>" : ""}<th>해의 끝</th><th>${T("순자산")}</th></tr></thead><tbody>${yr}</tbody></table></div></details>
   <details class="tune" ${s.override[i] ? "open" : ""}><summary>숫자를 직접 바꿔서 다시 계산해 보기</summary><div class="sliders">
    <div class="sl"><label>한 달에 더 모으거나(+) 덜 모으는(−) 돈 <b>${(s.ovIn[i]?.delta ?? 0) > 0 ? "+" : ""}${s.ovIn[i]?.delta ?? 0}만원</b></label><input type="range" id="sv" min="-100" max="100" step="10" value="${s.ovIn[i]?.delta ?? 0}"></div>
    <div class="sl"><label>1년에 불어나는 비율(${T("수익률")}) <b>${(s.ovIn[i]?.ret ?? ret).toFixed(1)}%</b></label><input type="range" id="rr" min="0" max="10" step="0.5" value="${s.ovIn[i]?.ret ?? ret}"></div>
   </div>${s.override[i] ? `<p class="cs" style="margin-top:8px">직접 바꾼 값으로 계산엔진이 다시 계산했어요. <button class="btn sm" data-act="reset-ov">원래대로</button></p>` : ""}</details>
  </section>
  <section class="sec"><h2 class="st">한 사람 한 사람에게 달라지는 점</h2><div>${F().members.map(m => `<div class="irow">${av(m.member_id)}<div><div class="nm">${esc(m.name)}</div><p>${esc((interp.per_member || {})[m.member_id] || "")}</p></div></div>`).join("")}</div></section>
  ${next("가족이 함께 고르기")}`;
}

/* ---------- 화면 5: 합의안 ---------- */
const optLabel = sp => `${sp.option_id}. ${sp.label}`;
function stanceRows(rd, opts) {
  const s = S(), vw = viewer(), R1 = rd === 1 ? s.r1 : s.r2, mine = R1[vw] || {};
  return opts.map(([oid, label, res]) => { const x = mine[oid]; return `<div class="myrow"><div class="mo"><b>${esc(label)}</b>${res ? `<span>${esc(res)}</span>` : ""}</div>
    <div class="seg">${["good", "cond", "no"].map(v => `<button class="${x && x.v === v ? "on v-" + v : ""}" data-act="stance" data-rd="${rd}" data-oi="${oid}" data-v="${v}">${VL[v][1]} ${VL[v][0]}</button>`).join("")}</div>
    ${x && x.v !== "good" ? `<input class="tx" data-rd="${rd}" data-oi="${oid}" value="${esc(x.text || "")}" maxlength="200" placeholder="${x.v === "no" ? "왜 받아들이기 어려운지 적어 주세요" : "어떤 조건이면 괜찮은지 적어 주세요"}">` : ""}</div>`; }).join("");
}
function famTable(rd, opts) {
  const s = S(), R1 = rd === 1 ? s.r1 : s.r2, SB = rd === 1 ? s.sub1 : s.sub2;
  const cell = x => !x ? `<span class="rv wait-v">기다리는 중</span>` : `<span class="rv v-${x.v}"><b>${VL[x.v][1]} ${VL[x.v][0]}</b>${x.text ? `<span>${esc(x.text)}</span>` : ""}</span>`;
  return `<div class="famtab-wrap"><table class="famtab"><thead><tr><th>방법</th>${F().members.map(m => `<th>${av(m.member_id, "sm")} ${esc(m.name)}</th>`).join("")}</tr></thead><tbody>${opts.map(([oid, label]) => `<tr><td class="ol2">${esc(label)}</td>${F().members.map(m => `<td>${SB[m.member_id] ? cell((R1[m.member_id] || {})[oid]) : cell(null)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
function consentState() {
  const s = S(), d = s.design;
  if (!d.specs) return {};
  const ids = d.specs.map(l => l.option_id);
  const all1 = mids().every(m => s.sub1[m]);
  const obj = (R1, oid) => mids().filter(m => ((R1[m] || {})[oid] || {}).v === "no");
  const cand1 = all1 ? ids.filter(oid => obj(s.r1, oid).length === 0) : [];
  const needRev = all1 && cand1.length === 0;
  const all2 = needRev && mids().every(m => s.sub2[m]);
  let final = null, conds = [];
  if (all1 && cand1.length) { const sp = d.specs[ids.indexOf(cand1[0])]; final = { spec: sp, label: optLabel(sp) }; conds = mids().map(m => [m, (s.r1[m] || {})[cand1[0]]]).filter(x => x[1] && x[1].v === "cond"); }
  if (all2 && obj(s.r2, "x").length === 0 && s.revise.result) {
    const rv = s.revise.result, from = d.specs[ids.indexOf(rv.from_option_id)];
    final = { spec: rv.spec, label: optLabel(from), revised: true };
    conds = mids().map(m => [m, (s.r2[m] || {}).x]).filter(x => x[1] && x[1].v === "cond");
  }
  const rejected2 = all2 && obj(s.r2, "x").length > 0;
  return { all1, cand1, needRev, all2, final, rejected2, conds: conds.map(([m, x]) => ({ member_id: m, text: x.text })) };
}
function s5() {
  const s = S(), d = s.design, vw = viewer(), goal = d.goal || goalNow();
  const head = `<div class="head"><div class="eyebrow">합의안</div><h1 class="h1">아무도 반대하지 않는 방법을 함께 찾아요</h1><p class="lead">점수를 더하지 않아요. 방법마다 각자 "좋아요 / 괜찮아요, 단 ○○ / 받아들이기 어려워요"로 답하고, 반대가 하나도 없는 방법을 합의안으로 삼아요. 붙은 조건은 약속이 돼요.</p></div>`;
  if (d.status !== "done") return head + `<div class="aibox"><p class="q">미래 계산이 먼저 필요해요.</p></div>`;
  if (!started(s.check) && s.check.status !== "error") setTimeout(() => run(s.check, "/api/agreement/check", { family: F(), goal: s.goalForm, specs: d.specs, summaries: summariesOf() }), 0);
  const opts1 = d.specs.map((sp, k) => [sp.option_id, optLabel(sp), results()[k].goal_hit_display]);
  const cs = consentState();
  const kc = s.check.result;
  let h = head + `<section class="sec"><h2 class="st">먼저, 각자 꼭 지키고 싶은 것으로 살펴봤어요</h2>${pend(s.check, "AI가 방법마다 점검표를 만들고 있어요", "retry-check")}
   ${kc ? `<div class="famtab-wrap"><table class="famtab kc"><thead><tr><th>방법</th>${F().members.map(m => `<th>${av(m.member_id, "sm")} ${esc(m.name)}<span class="kp">${esc(ivState(m.member_id).summary.keep)}</span></th>`).join("")}</tr></thead><tbody>${d.specs.map(sp => `<tr><td class="ol2">${esc(optLabel(sp))}</td>${F().members.map(m => { const c = (kc.keep_check[sp.option_id] || {})[m.member_id] || { ok: false, reason: "" }; return `<td><span class="kv2 ${c.ok ? "ok" : "ng"}"><b>${c.ok ? "✓ 지켜요" : "✕ 깨져요"}</b><span>${esc(c.reason)}</span></span></td>`; }).join("")}</tr>`).join("")}</tbody></table></div><p class="ailine">${esc(kc.note)}</p>${vbadge(s.check.verification, s.check.calls)}` : ""}</section>`;
  h += `<section class="sec"><h2 class="st">각자의 의사</h2>
   ${!s.sub1[vw] ? `<div class="act"><div class="rl">${av(vw, "sm")}${esc(mem(vw).name)}님, 방법마다 의사를 남겨 주세요</div>${stanceRows(1, opts1)}<div class="row"><span style="flex:1"></span><button class="btn primary sm" data-act="sub" data-rd="1" ${d.specs.every(sp => (s.r1[vw] || {})[sp.option_id]) ? "" : "disabled"}>내 의사 보내기</button></div></div>` : ""}
   <div style="margin-top:16px">${famTable(1, opts1)}</div>${turn(mids().filter(m => !s.sub1[m]), "의사 표시")}
   ${cs.all1 && cs.cand1.length > 1 ? `<p class="cs" style="margin-top:10px">반대 없는 방법이 둘 이상이에요. 실제로는 그중 하나를 함께 고르는 질문을 한 번 더 해요. 체험판에서는 ${esc(cs.cand1[0])}로 이어가요.</p>` : ""}</section>`;
  if (cs.needRev) {
    if (!started(s.revise) && s.revise.status !== "error") setTimeout(() => run(s.revise, "/api/agreement/revise", { family: F(), goal: s.goalForm, specs: d.specs, stances: s.r1, summaries: summariesOf() }), 0);
    const rv = s.revise.result;
    h += `<section class="sec"><h2 class="st">반대가 있어서 AI가 방법을 다듬었어요</h2>${pend(s.revise, "AI가 반대 이유를 읽고 수정안을 만들고 있어요", "retry-revise")}
     ${rv ? `<div class="aibox"><p class="q">모든 방법에 반대가 하나 이상 있어요. 반대 이유를 바탕으로 <b>${esc(rv.label)}</b>을 만들었어요.</p><p class="sub">${esc(rv.why)}</p>
      <table class="chg">${rv.changes.map(c => `<tr><th>${esc(c.field)}</th><td>${esc(c.before)} → ${esc(c.after)}${mem(c.reason_member_id)?.name !== "?" ? ` (${esc(mem(c.reason_member_id).name)}님 의견)` : ""}</td></tr>`).join("")}<tr><th>계산 결과</th><td>${esc(rv.simulation.results[0].goal_hit_display)} (원래 ${esc(results()[d.specs.findIndex(l => l.option_id === rv.from_option_id)].goal_hit_display)})</td></tr></table></div>${vbadge(s.revise.verification, s.revise.calls)}
      ${!s.sub2[vw] ? `<div class="act"><div class="rl">${av(vw, "sm")}${esc(mem(vw).name)}님, 다듬은 방법에 의사를 남겨 주세요</div>${stanceRows(2, [["x", rv.label, ""]])}<div class="row"><span style="flex:1"></span><button class="btn primary sm" data-act="sub" data-rd="2" ${(s.r2[vw] || {}).x ? "" : "disabled"}>내 의사 보내기</button></div></div>` : ""}
      <div style="margin-top:16px">${famTable(2, [["x", rv.label]])}</div>${turn(mids().filter(m => !s.sub2[m]), "의사 표시")}
      ${cs.rejected2 ? `<p class="okline"><span class="chk" style="background:var(--bad)">!</span><span>다듬은 방법에도 반대가 있어요. 체험판에서는 수정을 한 번까지만 해요. 미래 계산으로 돌아가 숫자를 직접 바꿔 보거나, 의사를 다시 남겨 주세요. <button class="btn sm" data-act="redo-consent">의사 다시 남기기</button></span></p>` : ""}` : ""}</section>`;
  }
  const dr = s.draft;
  if (cs.final) {
    const key = JSON.stringify([cs.final.spec, cs.conds]);
    if (dr.key !== key) { Object.keys(dr).forEach(k => delete dr[k]); dr.key = key; s.signed = {}; }
    if (!started(dr) && dr.status !== "error") setTimeout(() => run(dr, "/api/agreement/draft", { family: F(), goal: s.goalForm, criterion: s.criterion.result.criterion, spec: cs.final.spec, method_label: cs.final.label, conditions: cs.conds, summaries: summariesOf(), version: s.version || 1, revision: cs.final.revised ? { label: s.revise.result.label, changes: s.revise.result.changes, why: s.revise.result.why } : null }), 0);
    const a = dr.result;
    h += `<section class="sec"><h2 class="st">반대 없이 모인 방법</h2><p class="okline"><span class="chk">✓</span><span><b>${esc(cs.final.label)}</b>${cs.final.revised ? " (다듬은 안)" : ""} — 가족 모두 반대하지 않았어요.</span></p>
     ${cs.conds.length ? `<ul class="conds">${cs.conds.map(c => `<li>${av(c.member_id, "sm")}<span><b>${esc(mem(c.member_id).name)}님의 조건</b>${esc(c.text)}</span></li>`).join("")}</ul>` : ""}
     ${pend(dr, "AI가 합의안과 합의 리포트를 쓰고 있어요", "retry-draft")}
     ${a ? paper(a, dr) : ""}</section>`;
  }
  const allSigned = mids().every(m => s.signed[m]);
  return h + next("약속에 맞는 금융상품 보기", !allSigned, "가족 모두 서명하면 다음으로 넘어갈 수 있어요");
}
function paper(a, dr) {
  const s = S(), vw = viewer(), f = F();
  const allSigned = mids().every(m => s.signed[m]);
  const ct = a.contribution.map(c => `${esc(c.label)} 월 ${won(c.amount)}`).join(" + ");
  return `<article class="paper" style="margin-top:22px"><div class="ptitle">${esc(f.room.name)} 합의안</div>
   <div class="pmeta">Ver.${a.version} · ${f.members.length}명 · 다음 점검 ${esc(a.review.next)} · 법적 합의문이 아닌 가족의 의사결정 기록이에요</div>
   <div class="psec"><h4>함께 이룰 목표</h4><p>${esc(a.goal)}</p></div>
   <div class="psec"><h4>고른 방법</h4><p><b>${esc(a.method.display_label)}</b> · 한 달 ${a.method.monthly_flow > 0 ? "+" : ""}${won(a.method.monthly_flow)}</p></div>
   <div class="psec"><h4>목표금액</h4><p>${esc(a.target_amount.label)}</p></div>
   <div class="psec"><h4>분담방식</h4><p>${ct || "따로 나누지 않아요"}</p></div>
   <div class="psec"><h4>이행시기</h4><p>${esc(a.timing.text)}</p></div>
   <div class="psec"><h4>변경조건</h4><p>${a.change_conditions.map(esc).join(" · ")}</p></div>
   <div class="psec"><h4>함께 지킬 약속</h4><ol>${a.commitments.map(c => `<li>${esc(c.text)} <span class="src">${esc(SRC[c.source.type] || "")}${c.source.member_id ? " · " + esc(mem(c.source.member_id)?.name || "") : ""}</span></li>`).join("")}</ol></div>
   <div class="psec"><h4>합의 리포트</h4><div><p><b>왜 이 방법인가요</b></p><ul>${a.report.reasons.map(t => `<li>${esc(t)}</li>`).join("")}</ul>
    ${a.report.outcomes.length ? `<p style="margin-top:8px"><b>결과</b> ${a.report.outcomes.map(o => `${esc(o.label)} ${esc(o.display)}`).join(" · ")}</p>` : ""}
    <p style="margin-top:8px"><b>실행 계획</b></p><ul>${a.report.action_plan.map(x => `<li>${esc(x.when)} · ${esc(x.what)}</li>`).join("")}</ul></div></div>
   ${vbadge(dr.verification, dr.calls)}
   <div class="psec"><h4>서명</h4><div><div class="sigs">${f.members.map(m => `<button class="sig ${s.signed[m.member_id] ? "on" : ""}" data-act="sign" ${m.member_id !== vw || s.signed[m.member_id] ? "disabled" : ""}>${av(m.member_id, "sm")}<span><b>${esc(m.name)}</b><br><span class="st">${s.signed[m.member_id] ? `Ver.${a.version}에 서명했어요` : m.member_id === vw ? "눌러서 서명하기" : "서명 대기"}</span></span></button>`).join("")}</div>
    ${allSigned ? `<div class="sealed"><span class="chk">✓</span>가족 모두 같은 합의안(Ver.${a.version})에 서명했어요. 합의안이 확정됐어요.</div>` : turn(mids().filter(m => !s.signed[m]), "서명")}</div></div></article>`;
}

/* ---------- 화면 6: 상품 추천 ---------- */
function s6() {
  const s = S(), a = s.draft.result, rc = s.rec;
  const head = `<div class="head"><div class="eyebrow">상품 추천</div><h1 class="h1">합의안의 약속을 지켜 줄 금융상품 유형이에요</h1><p class="lead">AI는 약속을 '필요'와 '제약'으로 바꾸기만 하고, 상품 유형은 금융 온톨로지를 따라 코드가 골라요. 그래서 왜 이 상품인지 경로로 설명할 수 있어요.</p></div>`;
  if (!a || !mids().every(m => s.signed[m])) return head + `<div class="aibox"><p class="q">가족 모두 서명한 합의안이 먼저 필요해요.</p></div>`;
  if (!started(rc) && rc.status !== "error") setTimeout(() => run(rc, "/api/recommend", { family: F(), agreement: a }), 0);
  if (rc.status !== "done") return head + pend(rc.status ? rc : { status: "loading" }, "AI가 약속을 온톨로지 어휘로 바꾸고 있어요", "retry-rec");
  const recs = rc.result.recommendations;
  const cards = recs.map(r => r.product_type_id ? `<div class="prod"><div class="top"><span class="inm">${esc(r.need_label)}</span><span class="kindtag">${{ policy: "정책금융·공적 제도", consult: "상담 연결", product: "상품 유형", action: "행동" }[r.kind] || ""}</span></div>
     <div><div class="pn">${esc(r.product_label)}</div><div class="what">${esc(r.summary)}</div></div>
     <dl class="attrs">${Object.entries({ rate: "금리", term: "기간", risk: "위험도", liquidity: "유동성", tax: "세제혜택", eligibility: "가입조건" }).map(([k, l]) => `<dt>${l}</dt><dd>${esc(r.attributes[k])}</dd>`).join("")}</dl>
     <div class="why2"><b>왜 이 상품인가요</b><br>${esc(r.reason_text)}</div>
     ${r.excluded.length ? `<div class="excl">제외: ${r.excluded.map(e => `${esc(e.label)}(${esc(e.reason)})`).join(", ")}</div>` : ""}</div>`
    : `<div class="prod"><div class="top"><span class="inm">${esc(r.need_label)}</span></div><div class="why2">${esc(r.reason_text)}</div></div>`).join("");
  return head + `${cards ? `<div class="pgrid">${cards}</div>` : `<div class="aibox"><p class="q">이 합의안의 약속에는 연결할 상품 유형이 없어요. 약속은 가족이 직접 지켜요.</p></div>`}${vbadge(rc.verification, rc.calls)}
   <p class="disc">상품은 유형 예시이며 특정 금융회사 상품이 아니에요. '확인 필요'는 공시·제도 안내로 확인해야 하는 항목이에요. 최종 선택과 가입은 본인이 결정해요.</p>${next("가족 홈으로 가기")}`;
}

/* ---------- 화면 7: 가족 홈 ---------- */
const pad2 = n => String(n).padStart(2, "0");
const isoDate = d => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
const todayIso = () => isoDate(new Date());
function addMonthsIso(iso, n) { const [y, m, d] = iso.split("-").map(Number); const t = new Date(y, m - 1 + n, 1); const last = new Date(t.getFullYear(), t.getMonth() + 1, 0).getDate(); return isoDate(new Date(t.getFullYear(), t.getMonth(), Math.min(d, last))); }
const krDate = iso => { const [y, m, d] = iso.split("-").map(Number); return `${y}년 ${m}월 ${d}일`; };
function calEvents() {
  const s = S(), a = s.draft.result, out = [];
  if (a && s.signedAt) for (let k = 1; k <= 6; k++) out.push({ date: addMonthsIso(s.signedAt, a.review.interval_months * k), title: `정기 점검(${a.review.interval_label})`, kind: "review" });
  ((s.cal || {}).events || []).forEach(e => out.push({ ...e, kind: "user" }));
  (s.reviewLog || []).forEach(x => out.push({ date: x.date, title: `재점검 기록: ${x.text}`, kind: "log" }));
  return out.sort((x, y) => x.date.localeCompare(y.date));
}
function calendar() {
  const s = S(), c = s.cal || (s.cal = { events: [], view: todayIso().slice(0, 7), sel: todayIso() });
  const [y, m] = c.view.split("-").map(Number);
  const first = new Date(y, m - 1, 1).getDay(), days = new Date(y, m, 0).getDate();
  const evs = calEvents(), by = {};
  evs.forEach(e => (by[e.date] = by[e.date] || []).push(e));
  let cells = "";
  for (let i = 0; i < first; i++) cells += `<span class="cd empty"></span>`;
  for (let d = 1; d <= days; d++) {
    const iso = `${y}-${pad2(m)}-${pad2(d)}`, e = by[iso] || [];
    cells += `<button class="cd ${iso === c.sel ? "sel" : ""} ${iso === todayIso() ? "today" : ""}" data-act="cal-day" data-d="${iso}"><span>${d}</span>${e.length ? `<i class="${e.some(x => x.kind === "review") ? "rv" : ""}"></i>` : ""}</button>`;
  }
  const selEv = by[c.sel] || [];
  const upcoming = evs.filter(e => e.date >= todayIso()).slice(0, 4);
  const rvEvents = s.draft.result?.review?.events || [];
  return `<div class="card cal"><div class="calh"><button class="btn sm" data-act="cal-nav" data-n="-1" aria-label="이전 달">‹</button><b>${y}년 ${m}월</b><button class="btn sm" data-act="cal-nav" data-n="1" aria-label="다음 달">›</button></div>
   <div class="calg">${["일", "월", "화", "수", "목", "금", "토"].map(w => `<span class="cw">${w}</span>`).join("")}${cells}</div>
   <div class="calsel"><div class="ct" style="margin-bottom:6px">${krDate(c.sel)}</div>
    ${selEv.length ? selEv.map(e => `<div class="tli"><span class="d">${e.kind === "review" ? "점검" : e.kind === "log" ? "기록" : "일정"}</span><span class="evt">${esc(e.title)}${e.kind === "user" ? `<button class="btn sm" data-act="cal-del" data-id="${e.id}">삭제</button>` : ""}</span></div>`).join("") : `<p class="cs">이 날은 일정이 없어요.</p>`}
    <div class="row" style="margin-top:8px"><input id="calTitle" maxlength="40" placeholder="이 날에 일정 더하기(예: 자동이체 확인)" style="flex:1;padding:8px 10px"><button class="btn sm primary" data-act="cal-add">추가</button></div></div>
   <div class="calup"><div class="ct" style="margin:14px 0 6px">다가오는 일정</div>${upcoming.length ? upcoming.map(e => `<div class="tli"><span class="d">${e.date.slice(2).replace(/-/g, ".")}</span><span>${esc(e.title)}</span></div>`).join("") : `<p class="cs">아직 없어요.</p>`}
    ${rvEvents.length ? `<p class="cs" style="margin-top:8px">이럴 때도 다시 모여요: ${rvEvents.map(esc).join(" · ")}</p>` : ""}</div></div>`;
}
function reviewCard(goal) {
  const s = S(), rv = s.review, inp = s.reviewIn || (s.reviewIn = {});
  const hasLoan = F().finance.some(x => x.kind === "loan" && x.amount);
  const f = (k, label, unit, ph) => `<label>${label}<div class="amt-in"><input data-rv="${k}" value="${esc(inp[k] ?? "")}" inputmode="decimal" placeholder="${ph}"><span>${unit}</span></div></label>`;
  const unit = k => k === "loan_rate_delta" || k === "return_delta" ? "%p" : k === "lump" ? "만원" : "만원/월";
  if (rv.status === "done" && !rv.change_labels) { s.review = {}; return reviewCard(goal); } // 예전 형식 결과는 버린다
  const res = rv.status === "done" ? `<div class="aibox" style="margin-top:12px"><p class="q">${Object.entries(rv.change_labels).map(([k, l]) => `${esc(l)} ${rv.changes[k] > 0 ? "+" : ""}${rv.changes[k]}${unit(k)}`).join(" · ")}</p>
     <p class="sub">${METRIC[goal.type]}: ${esc(rv.before)} → <b>${esc(rv.after)}</b>${rv.hit_month_delta != null && rv.hit_month_delta !== 0 ? ` (${rv.hit_month_delta > 0 ? rv.hit_month_delta + "개월 늦어져요" : -rv.hit_month_delta + "개월 빨라져요"})` : rv.hit_month_delta === 0 ? " (그대로예요)" : ""}. 한 달에 늘거나 줄어드는 돈 ${won(rv.flow_before)} → ${won(rv.flow_after)}.
     ${rv.within_after === false && rv.within_before !== false ? "<br><b>이대로면 정한 기한을 넘겨요.</b> 합의안을 다시 정하는 것을 권해요." : ""}</p></div>
     <div class="row" style="margin-top:10px">${rv.saved ? `<span class="cs">✓ 재점검 기록에 저장했어요</span>` : `<button class="btn sm" data-act="review-save">재점검 결과 저장하기</button>`}<button class="btn primary sm" data-act="renegotiate">이 상황으로 합의안 다시 정하기(Ver.${(s.version || 1) + 1})</button><span class="cs">가족이 넣은 금융 정보를 바뀐 값으로 고치고, 미래 계산부터 다시 해요. 공동 목표는 그대로예요.</span></div>` : pend(rv, "다시 계산하고 있어요", "review");
  return `<div class="card"><div class="ct">재점검 · 상황이 바뀌면 다시 계산해요</div><p class="cs" style="margin:4px 0 10px">바뀐 것만 넣으세요(늘면 +, 줄면 −). 계산엔진이 지난 합의와 무엇이 달라지는지 다시 계산해요. AI를 쓰지 않아 비용이 들지 않아요.</p>
   <div class="gform rvform">${f("income_delta", "매달 들어오는 돈", "만원/월", "예: -50")}${f("expense_delta", "매달 나가는 돈", "만원/월", "예: 30")}${f("lump", "한 번에 생기거나 나간 돈", "만원", "예: -300")}${f("return_delta", "예금·투자 수익률", "%p", "예: -0.5")}${hasLoan ? f("loan_rate_delta", "대출 금리", "%p", "예: 1") : ""}</div>
   <div class="row" style="margin-top:10px"><button class="btn sm" data-act="review">다시 계산하기</button></div>${res}
   ${(s.reviewLog || []).length ? `<div class="ct" style="margin:16px 0 4px">재점검 기록</div>${s.reviewLog.slice().reverse().map((x, i, arr) => `<div class="tli"><span class="d">${x.date.slice(2).replace(/-/g, ".")}</span><span class="evt"><span>Ver.${x.version} · ${esc(x.text)} → ${esc(METRIC[goal.type])} ${esc(x.before)} → ${esc(x.after)}</span><button class="btn sm" data-act="review-del" data-i="${arr.length - 1 - i}">삭제</button></span></div>`).join("")}` : ""}</div>`;
}
function s7() {
  const s = S(), a = s.draft.result, f = F(), cs = consentState(), goal = s.design.goal || goalNow();
  const head = `<div class="head"><div class="eyebrow">가족 홈</div><h1 class="h1">${esc(mem(f.room.host_member_id).name)}님 가족의 이번 달</h1><p class="lead">합의하고 3개월이 지났다고 가정한 화면이에요. 약속을 잘 지키고 있는지 가족 모두 같은 화면으로 봐요.</p></div>`;
  if (!a || !cs.final || !mids().every(m => s.signed[m])) return head + `<div class="aibox"><p class="q">확정된 합의안이 먼저 필요해요.</p></div>` + next("", true, "");
  const hm = s.home;
  if (!started(hm) && hm.status !== "error") setTimeout(() => run(hm, "/api/simulate", { family: F(), goal: s.goalForm, specs: [cs.final.spec] }), 0);
  if (hm.status !== "done") return head + pend(hm.status ? hm : { status: "loading" }, "계산엔진이 이번 달 상태를 계산하고 있어요", "retry-home");
  const r = hm.results[0], m3 = r.monthly[2];
  // 메인 목표 카드는 가족이 동의한 목표 종류에 따라 정해진 틀로 보여 준다(AI가 아니라 계산엔진 값이라 틀릴 일이 없다).
  let big, pct = 0, label;
  if (goal.type === "reach_target") { big = won(m3.end) + `<small>/ ${won(goal.target_amount)}</small>`; pct = Math.max(0, Math.min(100, Math.round(m3.end / goal.target_amount * 100))); label = goal.label || "모은 돈"; }
  else if (goal.type === "debt_free") { const d0 = r.start_debt; big = won(m3.debt) + "<small> 남았어요</small>"; pct = d0 ? Math.round((1 - m3.debt / d0) * 100) : 100; label = "남은 대출 · " + (goal.label || "대출 다 갚기"); }
  else { big = esc(r.goal_hit_display); pct = 100; label = "예금으로 버틸 수 있는 기간 · 지금 예금 " + won(m3.end); }
  const hist = s.history || [];
  return head + `<div class="homegrid"><div class="stackv">
   <div class="card goalcard"><div class="cs" style="font-weight:600">${esc(label)}</div><div class="gv">${big}</div>${goal.type !== "runway" ? `<div class="pbar"><i style="width:${pct}%"></i></div>` : ""}<div class="pmeta2"><span>합의 후 3개월 · 이대로면 ${esc(r.goal_hit_display)}${goal.type === "runway" ? "" : " 뒤"}</span><span class="num">${goal.type !== "runway" ? pct + "%" : ""}</span></div></div>
   <div class="card"><div class="ct" style="margin-bottom:6px">이번 달 약속</div><div>${a.contribution.map(c => `<div class="trow done"><span class="c">✓</span><span class="tt">${esc(c.label)}</span><span class="ta">${won(c.amount)}</span></div>`).join("")}${a.report.action_plan.map(x => `<div class="trow"><span class="c"></span><span class="tt">${esc(x.what)}</span><span class="ta">${esc(x.when)}</span></div>`).join("")}</div></div>
   ${reviewCard(goal)}
  </div><div class="stackv">
   ${calendar()}
   <div class="card"><div class="ct" style="margin-bottom:10px">우리 가족 합의안</div><p class="cs" style="margin-bottom:12px">${f.members.length}명 서명 · Ver.${a.version}${s.signedAt ? ` · ${krDate(s.signedAt)} 확정` : ""}</p><div class="stack" style="margin-bottom:14px">${f.members.map(m => av(m.member_id, "sm")).join("")}</div><button class="btn sm" data-act="go" data-i="5">합의안 보기</button>
    ${hist.length ? `<p class="cs" style="margin-top:12px">지난 합의안: ${hist.map(h => `Ver.${h.version}(${esc(h.method)}${h.signedAt ? ", " + krDate(h.signedAt) : ""})`).join(" · ")}</p>` : ""}</div>
  </div></div>${next("", true, "")}`;
}

/* ---------- 체험 코드 ---------- */
function codeScreen(msg) {
  return `<div class="head"><div class="eyebrow">체험 코드</div><h1 class="h1">체험 코드를 넣어 주세요</h1><p class="lead">AI 사용량을 지키기 위해 체험 코드가 있는 분만 AI 기능을 쓸 수 있어요. 코드는 공모전 심사·체험 안내에 함께 드려요.</p></div>
  <div class="act" style="max-width:460px"><div class="rl">체험 코드</div><input id="codeIn" maxlength="40" autocomplete="off"><div class="row"><span class="cs" style="color:var(--bad)">${esc(msg || "")}</span><span style="flex:1"></span><button class="btn primary sm" data-act="code">확인</button></div></div>`;
}
let needCode = false, codeMsg = "";
window.onAccessDenied = () => { ACCESS.set(""); needCode = true; codeMsg = "체험 코드가 맞지 않거나 바뀌었어요"; render(); };

/* ---------- 틀 ---------- */
const SCR = [s0, s1, s2, s3, s4, s5, s6, s7];
function chrome() {
  const f = F();
  $("#roomName").textContent = f.room.name || "새 가족방";
  $("#stack").innerHTML = f.members.filter(m => m.name).map(m => av(m.member_id, "sm")).join("");
  $("#rail").innerHTML = `<h3>목차</h3>` + STEPS.map((t, i) => `<button data-act="go" data-i="${i}" class="${i < step ? "done" : ""}" ${i === step ? 'aria-current="step"' : ""}><span>${t}</span><span class="dots"></span><span class="num">${i + 1}</span></button>`).join("");
  $("#pos").textContent = (step + 1) + " / " + STEPS.length;
  $("#viewer").innerHTML = f.members.map(m => `<option value="${m.member_id}" ${m.member_id === viewer() ? "selected" : ""}>${esc(m.name || "이름 없음")}</option>`).join("");
  $("#roomLabel").textContent = ROOMS[room];
  $("#prev").disabled = step === 0; $("#nextBtn").disabled = step === STEPS.length - 1;
}
function render() {
  if (view !== "app" || !S() || !CFG) return;
  chrome();
  const keep = document.activeElement && (document.activeElement.id || document.activeElement.dataset?.bind);
  if (needCode) { $("#main").innerHTML = `<div class="screen">${codeScreen(codeMsg)}</div>`; return; }
  const sc = (step > 0 && !S().setupDone) ? s0 : SCR[step];
  $("#main").innerHTML = `<div class="screen">${sc()}</div>`;
  const eb = $("#main .head .eyebrow"); if (eb) eb.textContent = `제${step + 1}장 · ${eb.textContent}`;
  const ch = $("#chat"); if (ch) ch.scrollTop = ch.scrollHeight;
  bindInputs();
  if (keep) { const el = document.getElementById(keep) || document.querySelector(`[data-bind="${keep}"]`); if (el) el.focus(); }
  save();
}
function go(i) { if (i < 0 || i >= STEPS.length) return; step = i; S().step = i; render(); window.scrollTo({ top: 0, behavior: "smooth" }); }

async function ensureConfig() {
  if (!CFG) CFG = await api("/api/config", {});
  if (!HEALTH) HEALTH = await api("/api/health", null, "GET");
}
async function startApp(k) {
  view = "app";
  $("#landing").hidden = true; $("#app").hidden = false; $("#gnb").hidden = true; $("#hLanding").hidden = true; $("#hApp").hidden = false;
  document.body.classList.add("app");
  $("#main").innerHTML = `<div class="pending"><span class="spin"></span>가족방을 불러오고 있어요</div>`;
  try {
    await ensureConfig();
    room = k;
    if (!R[k]) {
      if (k === "custom") freshState(k, blankFamily());
      else { const p = await api("/api/preset", { preset_id: k }); const sc = p.scripts; delete p.scripts; delete p._note; freshState(k, p, sc); }
    }
    step = R[k].step || 0;
    needCode = HEALTH.access_required && !ACCESS.get();
  } catch (e) {
    const why = e.code === "not_found" ? "서버가 예전 버전이에요. 서버를 껐다가(Ctrl+C) 다시 켜 주세요(python dev_server.py 8000)."
      : e.code === "network" ? "서버에 연결하지 못했어요. 서버(python dev_server.py 8000)가 켜져 있는지 확인해 주세요." : "";
    $("#main").innerHTML = `<div class="failbox"><b>가족방을 불러오지 못했어요</b>${esc(e.message)}${why ? "<br>" + esc(why) : ""}</div>`; return;
  }
  render(); window.scrollTo({ top: 0 });
}
function showLanding() { view = "landing"; $("#landing").hidden = false; $("#app").hidden = true; $("#gnb").hidden = false; $("#hLanding").hidden = false; $("#hApp").hidden = true; document.body.classList.remove("app"); window.scrollTo({ top: 0 }); save(); }

/* ---------- 입력 · 동작 ---------- */
function setPath(obj, path, val) { const ks = path.split("."); let o = obj; for (const k of ks.slice(0, -1)) o = o[k]; o[ks[ks.length - 1]] = val; }
function getPath(obj, path) { return path.split(".").reduce((o, k) => o?.[k], obj); }
function famEdited(path) {
  const s = S();
  if (path.startsWith("story") || path.startsWith("finance") || path.startsWith("room")) {
    if (s.story.status) s.story = {};
    s.profile = null; reset("goal");
  }
}
function bindInputs() {
  const s = S();
  document.querySelectorAll("[data-bind]").forEach(el => {
    const path = el.dataset.bind, isNum = "num" in el.dataset;
    const val = () => el.type === "checkbox" ? el.checked : isNum ? (el.value.trim() === "" ? null : Number(el.value.replace(/,/g, ""))) : el.value;
    if (el.tagName === "SELECT" || el.type === "checkbox") el.onchange = () => {
      setPath(s.fam, path, val());
      if (/^finance\.\d+\.kind$/.test(path)) { const it = getPath(s.fam, path.replace(/\.kind$/, "")); if (it.kind === "loan") { it.loan_type = it.loan_type || "credit"; it.rate = it.rate ?? 5; } }
      famEdited(path); render();
    };
    else el.oninput = () => { setPath(s.fam, path, val()); famEdited(path); save(); };
  });
  document.querySelectorAll("[data-gf]").forEach(el => {
    const k = el.dataset.gf, isNum = "num" in el.dataset;
    const apply = () => {
      const v = isNum ? (el.value.trim() === "" ? null : Number(el.value)) : el.value;
      if (k === "within_years") s.goalForm.within_months = v ? Math.round(v * 12) : null; else s.goalForm[k] = v;
      if (k === "target_amount") s.goalForm.target_note = null;
      s.goalChk = {}; s.approvals = {}; reset("design");
    };
    if (el.tagName === "SELECT") el.onchange = () => { apply(); render(); }; else { el.oninput = apply; el.onchange = () => render(); }
  });
  document.querySelectorAll("input.tx").forEach(t => t.oninput = () => { const rd = +t.dataset.rd, R1 = rd === 1 ? s.r1 : s.r2; R1[viewer()][t.dataset.oi].text = t.value; });
  document.querySelectorAll("[data-rv]").forEach(el => el.oninput = () => { (s.reviewIn = s.reviewIn || {})[el.dataset.rv] = el.value; });
  const ans = $("#ans"); if (ans) ans.oninput = () => { ivState(viewer()).draft = ans.value; };
  const sv = $("#sv"), rr = $("#rr");
  if (sv && rr) {
    const fire = () => {
      const i = s.pick; s.ovIn[i] = { delta: +sv.value, ret: +rr.value };
      clearTimeout(bindInputs._t);
      bindInputs._t = setTimeout(async () => {
        try {
          const out = await api("/api/simulate", { family: F(), goal: s.goalForm, specs: [s.design.specs[i]], override: { monthly_delta: +sv.value, expected_return: +rr.value } });
          s.override[i] = out.results[0]; render();
        } catch (e) { toast(e.message); }
      }, 250);
    };
    sv.oninput = fire; rr.oninput = fire;
  }
}
function nextId(list, key, prefix) { return prefix + (Math.max(-1, ...list.map(x => +String(x[key]).slice(1))) + 1); }
function setupProblem() {
  const f = F();
  if (!f.room.name.trim()) return "가족방 이름을 적어 주세요";
  for (const m of f.members) {
    if (!m.name || !m.name.trim()) return "가족 모두의 이름을 적어 주세요";
    if (!m.role || !m.role.trim()) return `${m.name}님의 관계를 적어 주세요`;
    if (!(m.age >= 1 && m.age <= 110)) return `${m.name}님의 나이를 적어 주세요`;
  }
  return "";
}
const ACT = {
  next: () => go(step + 1),
  prev: () => go(step - 1),
  go: b => go(+b.dataset.i),
  toggle: b => { const el = document.getElementById(b.dataset.target); if (el) el.hidden = !el.hidden; },
  viewer: b => { S().viewer = b.dataset.mid; toast(mem(b.dataset.mid).name + "님 화면이에요"); render(); window.scrollTo({ top: 0 }); },
  code: async () => { const v = ($("#codeIn").value || "").trim(); if (!v) return; ACCESS.set(v); try { await api("/api/access", { code: v }); needCode = false; codeMsg = ""; toast("확인했어요"); render(); } catch (e) { ACCESS.set(""); codeMsg = e.message; render(); } },
  "add-member": () => { const f = F(); f.members.push({ member_id: nextId(f.members, "member_id", "m"), name: "", role: "", age: null, easy_mode: false }); render(); },
  "del-member": b => { const f = F(), m = f.members[+b.dataset.i]; f.members.splice(+b.dataset.i, 1); f.finance.forEach(x => { if (x.owner_id === m.member_id) x.owner_id = "joint"; }); if (f.room.host_member_id === m.member_id) f.room.host_member_id = f.members[0].member_id; delete S().iv[m.member_id]; if (S().viewer === m.member_id) S().viewer = f.members[0].member_id; render(); },
  "setup-done": () => { const p = setupProblem(); if (p) { $("#setupHint").textContent = p; toast(p); return; } const s = S(); s.setupDone = true; s.fam.story.author_id = s.fam.room.host_member_id; s.viewer = s.fam.room.host_member_id; render(); },
  "edit-setup": () => { S().setupDone = false; render(); },
  "add-fin": b => { const f = F(), k = b.dataset.kind; const it = { item_id: nextId(f.finance, "item_id", "f"), owner_id: "joint", kind: k, label: "", amount: null }; if (k === "loan") Object.assign(it, { loan_type: "credit", rate: 5, payment: null }); f.finance.push(it); famEdited("finance"); render(); },
  "del-fin": b => { const f = F(), it = f.finance[+b.dataset.i]; f.finance.splice(+b.dataset.i, 1); delete f.disclosure[it.item_id]; famEdited("finance"); render(); },
  disc: b => { F().disclosure[b.dataset.item] = b.dataset.v; famEdited("finance"); render(); },
  understand: async () => {
    const s = S();
    s.story = { status: "loading" }; render();
    try { const chk = await api("/api/family/check", { family: F() }); s.profile = chk.profile; }
    catch (e) { s.story = { status: "error", error: e }; render(); return; }
    s.story = {}; run(s.story, "/api/story/understand", { family: F() });
  },
  "send-ans": () => { const st = ivState(viewer()), t = ($("#ans").value || "").trim(); if (!t) { toast("답을 적어 주세요"); return; } st.answers.push(t); st.draft = ""; render(); },
  "fill-ans": () => { const st = ivState(viewer()); st.draft = S().scripts.answers[viewer()][st.answers.length]; render(); },
  finish: b => finishInterview(b.dataset.mid),
  "clar-resume": b => { const st = ivState(b.dataset.mid); st.clar = { state: "asking" }; st.clarTries = 0; st.resolve = {}; render(); },
  confirm: b => { ivState(b.dataset.mid).confirmed = true; toast("요약을 가족에게 공유했어요"); render(); },
  clar: b => answerClar(b.dataset.mid, +b.dataset.i),
  "clar-text": b => { const t = ($("#clarTxt").value || "").trim(); if (!t) return; answerClar(b.dataset.mid, -1, t); },
  reask: b => { const st = ivState(b.dataset.mid); S().viewer = b.dataset.mid; st.clar = { state: "asking" }; st.confirmed = false; st.summary = null; st.resolve = {}; st.review2 = {}; reset("goal"); toast(mem(b.dataset.mid).name + "님의 1:1 대화로 이동했어요"); go(2); },
  "retry-goal": () => { S().goal = {}; render(); },
  reply: () => { const t = $("#myReply").value.trim(); if (!t) { toast("답을 적어 주세요"); return; } S().replies[viewer()] = t; toast("답을 보냈어요"); render(); },
  "reply-chip": b => { const t = $("#myReply"); t.value = b.dataset.t; t.focus(); },
  "fill-reply": () => { $("#myReply").value = S().scripts.replies[viewer()] || ""; },
  "retry-criterion": () => { S().criterion = {}; render(); },
  "fill-goal": () => { const s = S(); Object.assign(s.goalForm, s.scripts.goal_form, { target_note: null }); s.goalChk = {}; s.approvals = {}; reset("design"); render(); },
  "goal-check": () => { const s = S(); run(s.goalChk, "/api/goal/check", { family: F(), goal: s.goalForm }); },
  approve: () => { S().approvals[viewer()] = true; toast("동의했어요"); render(); },
  "retry-design": () => { reset("design"); render(); },
  pick: b => { S().pick = +b.dataset.i; render(); },
  "reset-ov": () => { const s = S(); delete s.override[s.pick]; delete s.ovIn[s.pick]; render(); },
  "retry-check": () => { S().check = {}; render(); },
  stance: b => { const s = S(), rd = +b.dataset.rd, R1 = rd === 1 ? s.r1 : s.r2, vw = viewer(), oi = b.dataset.oi, v = b.dataset.v; R1[vw] = R1[vw] || {}; const prev = R1[vw][oi] || {}; R1[vw][oi] = { v, text: v === "good" ? "" : prev.text || "" }; render(); },
  sub: b => { const s = S(), rd = +b.dataset.rd, R1 = rd === 1 ? s.r1 : s.r2, SB = rd === 1 ? s.sub1 : s.sub2, mine = R1[viewer()] || {}; if (Object.values(mine).some(x => x.v === "no" && !x.text.trim())) { toast("받아들이기 어려운 이유를 적어 주세요"); return; } SB[viewer()] = true; toast("의사를 보냈어요"); render(); },
  "redo-consent": () => { const s = S(); s.r1 = {}; s.sub1 = {}; s.revise = {}; s.r2 = {}; s.sub2 = {}; render(); },
  "retry-revise": () => { S().revise = {}; render(); },
  "retry-draft": () => { const d = S().draft; Object.keys(d).forEach(k => delete d[k]); render(); },
  sign: () => { const s = S(); s.signed[viewer()] = true; if (mids().every(m => s.signed[m]) && !s.signedAt) s.signedAt = todayIso(); toast("서명했어요"); render(); },
  "retry-rec": () => { S().rec = {}; render(); },
  "retry-home": () => { S().home = {}; render(); },
  review: () => {
    const s = S(), ch = {};
    for (const [k, v] of Object.entries(s.reviewIn || {})) { const n = Number(String(v).replace(/[,+\s]/g, "")); if (String(v).trim() !== "" && !isNaN(n) && n !== 0) ch[k] = n; }
    if (!Object.keys(ch).length) { toast("바뀐 상황을 하나 이상 넣어 주세요"); return; }
    s.review = {}; run(s.review, "/api/review/compare", { family: F(), goal: s.goalForm, spec: consentState().final.spec, changes: ch });
  },
  "review-save": () => {
    const s = S(), rv = s.review, unit = k => k === "loan_rate_delta" || k === "return_delta" ? "%p" : k === "lump" ? "만원" : "만원/월";
    const text = Object.entries(rv.change_labels).map(([k, l]) => `${l} ${rv.changes[k] > 0 ? "+" : ""}${rv.changes[k]}${unit(k)}`).join(", ");
    (s.reviewLog = s.reviewLog || []).push({ date: todayIso(), version: s.draft.result.version, text, before: rv.before, after: rv.after, changes: rv.changes, hit_month_delta: rv.hit_month_delta });
    rv.saved = true; toast("재점검 결과를 저장했어요. 캘린더에도 표시돼요"); render();
  },
  "review-del": b => { const s = S(); s.reviewLog.splice(+b.dataset.i, 1); render(); },
  renegotiate: async () => {
    const s = S(), ch = s.review.changes, f = F();
    if (!(await ask("바뀐 상황으로 합의안을 다시 정할까요?", `금융 정보를 바뀐 값으로 고치고 미래 계산부터 다시 해요. 지금 합의안(Ver.${s.draft.result.version})은 지난 합의안으로 남아요.`, [{ label: "다시 정하기", value: true, primary: true }]))) return;
    const add = (kind, label, amount) => f.finance.push({ item_id: nextId(f.finance, "item_id", "f"), owner_id: "joint", kind, label, amount: Math.abs(amount) });
    if (ch.income_delta) add(ch.income_delta > 0 ? "income" : "expense", ch.income_delta > 0 ? "늘어난 수입(재점검)" : "줄어든 수입(재점검)", ch.income_delta);
    if (ch.expense_delta) add(ch.expense_delta > 0 ? "expense" : "income", ch.expense_delta > 0 ? "늘어난 지출(재점검)" : "줄어든 지출(재점검)", ch.expense_delta);
    if (ch.lump > 0) add("deposit", "새로 생긴 돈(재점검)", ch.lump);
    if (ch.lump < 0) { let left = -ch.lump; for (const it of f.finance.filter(x => x.kind === "deposit" || x.kind === "investment")) { const t = Math.min(it.amount, left); it.amount = Math.round((it.amount - t) * 10) / 10; left -= t; if (left <= 0) break; } }
    if (ch.loan_rate_delta) f.finance.filter(x => x.kind === "loan").forEach(x => x.rate = Math.max(0, Math.round((x.rate + ch.loan_rate_delta) * 100) / 100));
    (s.history = s.history || []).push({ version: s.draft.result.version, method: s.draft.result.method.display_label, signedAt: s.signedAt, agreement: s.draft.result });
    s.version = (s.version || 1) + 1; s.signedAt = null; s.profile = null; s.reviewIn = {};
    reset("design");
    try { const g = await api("/api/goal/check", { family: F(), goal: s.goalForm }); s.goalChk = { status: "done", goal: g.goal }; go(4); toast(`Ver.${s.version}을 위해 미래 계산부터 다시 해요`); }
    catch (e) { s.goalChk = {}; s.approvals = {}; go(3); toast("바뀐 상황에서는 목표를 다시 정해야 해요: " + e.message); }
  },
  "cal-nav": b => { const c = S().cal; const [y, m] = c.view.split("-").map(Number); const t = new Date(y, m - 1 + +b.dataset.n, 1); c.view = `${t.getFullYear()}-${pad2(t.getMonth() + 1)}`; render(); },
  "cal-day": b => { S().cal.sel = b.dataset.d; render(); },
  "cal-add": () => { const t = ($("#calTitle").value || "").trim(); if (!t) { toast("일정 이름을 적어 주세요"); return; } const c = S().cal; c.events.push({ id: "e" + Date.now(), date: c.sel, title: t.slice(0, 40) }); toast("일정을 더했어요"); render(); },
  "cal-del": b => { const c = S().cal; c.events = c.events.filter(e => e.id !== b.dataset.id); toast("일정을 지웠어요"); render(); },
  restart: async () => {
    const how = await ask("처음부터 다시 할까요?", "이 가족방에서 진행한 내용은 이 브라우저에만 저장돼 있어요.", [
      { label: "입력은 그대로 두고 다시 진행", value: "soft", primary: true },
      { label: "모두 지우고 새로 시작", value: "hard" }]);
    if (!how) return;
    const k = room, old = R[k];
    delete R[k];
    if (how === "soft" && old) {  // 가족방·이야기·금융정보는 남기고 AI 단계부터 다시
      const fam = JSON.parse(JSON.stringify(old.fam));
      freshState(k, fam, old.scripts);
      R[k].setupDone = true; R[k].step = 1;
      toast("입력은 그대로 두고 처음부터 다시 진행해요");
    } else toast("모두 지우고 새로 시작해요");
    save(); startApp(k);
  },
};
document.addEventListener("click", e => {
  const b = e.target.closest("[data-act]");
  if (!b || b.disabled) return;
  const a = b.dataset.act;
  if (/^retry-(review2?|resolve):/.test(a)) {
    const [kind, mid] = a.split(":"); const st = ivState(mid);
    if (kind === "retry-review") { st.review = {}; finishInterview(mid); }
    else if (kind === "retry-resolve") { st.resolve = {}; st.clar = { state: "asking" }; render(); }
    else { st.review2 = {}; answerClar(mid, st.clar.choice ?? -1, st.clar.answer); }
    return;
  }
  if (ACT[a]) ACT[a](b);
});
document.querySelectorAll("[data-start]").forEach(b => b.onclick = () => startApp(b.dataset.start));
document.querySelectorAll("[data-scroll]").forEach(b => b.onclick = () => { if (view !== "landing") showLanding(); const t = document.getElementById(b.dataset.scroll); if (t) window.scrollTo({ top: t.getBoundingClientRect().top + window.scrollY - 64, behavior: "smooth" }); });
$("#logo").onclick = showLanding; $("#exit").onclick = showLanding;
$("#viewer").onchange = e => { S().viewer = e.target.value; render(); };
$("#prev").onclick = () => go(step - 1); $("#nextBtn").onclick = () => go(step + 1);
$("#restart").onclick = () => ACT.restart();
document.addEventListener("keydown", e => { if (view !== "app" || ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return; if (e.key === "ArrowRight") go(step + 1); if (e.key === "ArrowLeft") go(step - 1); });
const aimk = document.getElementById("aimk"); if (aimk) aimk.innerHTML = AIMARK;
load();
// 모델 이름은 화면에 보이지 않는다. 개발용 재생 모드일 때만 "실제 AI 아님"을 알려 준다(혼동 방지).
api("/api/health", null, "GET").then(h => { HEALTH = h; const p = $("#prov"); if (h.provider === "replay") { p.hidden = false; p.classList.add("replay"); p.textContent = "개발용 재생 모드 — 실제 AI 아님"; } }).catch(() => { const p = $("#prov"); p.hidden = false; p.textContent = "서버 연결 안 됨"; });
