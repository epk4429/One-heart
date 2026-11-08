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
// 공동 목표 제안·방법 설계 속 금융꿀팁 근거([[tip:조각ID|근거 문구|원문 인용]]): 문구를 누르면 그 자리에서 원문 인용·출처가 보인다(용어 풀이와 같은 방식)
const tipText = (text, tips) => { const by = Object.fromEntries((tips || []).map(t => [t.tip_id + "|" + t.quote, t])); return String(text || "").split(/(\[\[tip:[A-Za-z0-9_]+\|[^\]|]+\|[^\]|]+\]\])/).map(part => { const m = part.match(/^\[\[tip:([A-Za-z0-9_]+)\|([^\]|]+)\|([^\]|]+)\]\]$/); if (!m) return esc(part); const t = by[m[1] + "|" + m[3].trim()]; if (!t) return esc(m[2]); const def = `“${t.quote}”\n— ${t.publisher} 「${t.source_title}」(${t.fetched_at} 수집)`; return `<button type="button" class="term cardref" data-def="${esc(def)}">${esc(m[2].trim())}</button>`; }).join(""); };
const VL = { good: ["괜찮아요", "✓"], cond: ["괜찮아요, 단", "△"], no: ["어려워요", "✕"] };
const SRC = { goal_setting: "공동 목표", condition: "조건", revision: "수정안", keep: "꼭 지키고 싶은 것" };
const GT = { reach_target: "목표 금액 모으기", runway: "예금이 얼마나 버티는지", debt_free: "대출 다 갚기" };
const METRIC = { reach_target: "목표에 닿는 때", runway: "예금이 버티는 기간", debt_free: "대출을 다 갚는 때" };

// mock 체험판(web/demo.html, tools/build_demo.py)에서는 예시대로만 진행한다: AI 답은 재생 공급자(mock), 계산은 브라우저 안의 Python.
const DEMO = !!(window.ONEHEART && window.ONEHEART.DEMO);
const STORE = DEMO ? "oneheart.demo.v3" : "oneheart.v3";
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
  goal: { goal: {}, pg: [], pgView: null, rd: {}, rev: {}, stuck: {}, cycleStart: 0, discDraft: "", criterion: {}, goalForm: null, goalChk: {}, approvals: {}, size: null, goalNums: {}, worldSel: {}, backPending: null },
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
    story: { author_id: "m0", text: "" }, goal_input: null, finance: [], disclosure: {} };
}
function freshState(key, fam, scripts) {
  const s = { key, fam, scripts: scripts || null, profile: null, setupDone: false, viewer: fam.room.host_member_id || fam.members[0].member_id,
    story: {}, iv: {} };
  R[key] = s; const prev = room; room = key; reset("goal"); room = prev;
  return s;
}
function save() {
  try { localStorage.setItem(STORE, JSON.stringify({ R, room, step })); } catch (e) { }
}
function load() {
  try {
    const d = JSON.parse(localStorage.getItem(STORE) || "null");
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
const turn = (list, what) => { const o = list.filter(m => m !== viewer()); return o.length ? `<div class="turn"><span>${o.map(m => esc(mem(m).name) + "님").join(", ")}의 ${what}${(c => c >= 0xac00 && c <= 0xd7a3 && (c - 0xac00) % 28 ? "이" : "가")(what.charCodeAt(what.length - 1))} 남았어요.</span><button class="btn sm" data-act="viewer" data-mid="${o[0]}">${esc(mem(o[0]).name)}님 차례로 바꾸기</button></div>` : ""; };
const oneDevice = () => `<div class="onedev"><b>한 기기에서 가족이 돌아가며 입력해요</b><span>아래 검은 막대의 <b>보는 사람</b>을 바꾸면 그 사람의 화면이 돼요. 실제 서비스에서는 가족마다 자기 휴대폰에서 알림을 받고 직접 입력해요.</span></div>`;
const customOn = () => !CFG || CFG.custom_family !== false;
const retSource = b => { const id = (b.source || "").startsWith("assumption:") ? b.source.slice(11) : "", r = (CFG?.assumptions?.returns || []).find(x => x.id === id); return r && r.expected_return === b.value ? r.source || "" : ""; }; // 수익률 가정값의 출처(data/assumptions.json). 예전에 저장한 계산이라 값이 다르면 보이지 않는다
const presetLocked = () => !customOn() && S() && S().key !== "custom"; // 공개 체험판: 예시 가족의 기본 정보는 고칠 수 없음
function applyPublicMode(h) {
  if (h.custom_family !== false) return;
  document.querySelectorAll('[data-start="custom"]').forEach(b => {
    b.removeAttribute("data-start"); b.dataset.scroll = "stories";
    b.textContent = b.textContent.includes("→") ? "예시 가족으로 체험하기 →" : "예시 가족으로 체험하기";
    b.onclick = () => { const t = document.getElementById("stories"); if (t) window.scrollTo({ top: t.getBoundingClientRect().top + window.scrollY - 64, behavior: "smooth" }); };
  });
  document.querySelectorAll("[data-custom-text]").forEach(el => el.textContent = el.dataset.customText);
  document.querySelectorAll(".cover .cta button").forEach(b => { if (b.textContent.includes("먼저 보기")) b.hidden = true; });
}
const exampleBtn = (act, extra = "") => S().scripts ? `<button class="btn sm" data-act="${act}" ${extra}>예시 답 넣기</button>` : "";

/* ---------- 화면 0: 가족방 만들기 ---------- */
function s0() {
  const s = S(), f = F(), host = f.room.host_member_id;
  if (presetLocked() && !s.setupDone) { s.setupDone = true; s.viewer = f.room.host_member_id; }
  if (s.setupDone) {
    const ivStarted = Object.values(s.iv).some(x => (x.answers || []).length);
    return `<div class="head"><div class="eyebrow">가족방 만들기</div><h1 class="h1">${esc(f.room.name)}</h1><p class="lead">${esc(mem(host).name)}님이 가족방을 만들었어요. 이제 가족의 이야기를 들어볼 차례예요.</p></div>
    ${oneDevice()}
    <div class="stackv">
     ${f.room.reason ? `<div class="card"><div class="ct">가족방을 만든 이유</div><p class="quote">${esc(f.room.reason)}</p><p class="qby">${esc(mem(host).name)} · ${esc(mem(host).role)}</p></div>` : ""}
     <div class="card"><div class="ct">참여한 가족 <span class="cs">${f.members.length}명</span></div>
      <div class="plist">${f.members.map(m => `<div class="prow">${av(m.member_id)}<div class="who"><div class="nm">${esc(m.name)} <span class="rl">· ${esc(m.role)} · ${m.age}세</span></div><div class="rl">${m.member_id === host ? "가족방을 만들었어요" : m.easy_mode ? "큰 글씨·쉬운 말로 참여" : "참여"}</div></div><span class="pill ${m.member_id === host ? "brand" : m.easy_mode ? "warm" : "good"}">${m.member_id === host ? "방장" : m.easy_mode ? "간편 모드" : "참여"}</span></div>`).join("")}</div>
      ${presetLocked() ? `<p class="cs" style="margin-top:12px">예시 가족이라 구성원은 정해져 있어요.</p>` : ivStarted ? `<p class="cs" style="margin-top:12px">각자의 생각을 듣기 시작해서 구성원은 바꿀 수 없어요. 바꾸려면 아래 검은 막대의 '처음부터'를 눌러 주세요.</p>` : `<button class="btn sm" style="margin-top:12px" data-act="edit-setup">구성원 고치기</button>`}</div>
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
  const s = S(), f = F(), vw = viewer(), own = it.owner_id === vw, ro = presetLocked() ? "disabled" : "";
  const d = f.disclosure[it.item_id] || "share";
  const kinds = CFG.kinds;
  const loan = it.kind === "loan";
  return `<tr>
   <td><select data-bind="finance.${i}.owner_id" ${ro}>${[["joint", "공동"], ...f.members.map(m => [m.member_id, m.name])].map(([v, l]) => `<option value="${v}" ${it.owner_id === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></td>
   <td><select data-bind="finance.${i}.kind" ${ro}>${Object.entries(kinds).map(([k, l]) => `<option value="${k}" ${it.kind === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></td>
   <td><input ${ro} data-bind="finance.${i}.label" value="${esc(it.label)}" placeholder="이름(예: 월급)" maxlength="30"></td>
   <td><div class="amt-in"><input ${ro} data-bind="finance.${i}.amount" data-num value="${it.amount ?? ""}" inputmode="decimal" placeholder="0"><span>만원${CFG.monthly_kinds.includes(it.kind) ? "/월" : ""}</span></div>
    ${loan ? `<div class="loanx"><select ${ro} data-bind="finance.${i}.loan_type">${Object.entries(CFG.loan_types).map(([k, l]) => `<option value="${k}" ${it.loan_type === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
      <label>금리 <input ${ro} data-bind="finance.${i}.rate" data-num value="${it.rate ?? ""}" inputmode="decimal" style="width:64px">%</label>
      ${it.loan_type !== "lease" ? `<label>월 상환액 <input ${ro} data-bind="finance.${i}.payment" data-num value="${it.payment ?? ""}" inputmode="decimal" style="width:72px">만원</label>` : ""}</div>` : ""}</td>
   <td>${own ? `<span class="disc">${["share", "hide"].map(k => `<button class="${d === k ? "on" : ""}" data-act="disc" data-item="${it.item_id}" data-v="${k}">${{ share: "공개", hide: "비공개" }[k]}</button>`).join("")}</span>` : `<span class="cs">${{ share: "공개", hide: "비공개" }[d === "summary_only" ? "hide" : d]}${it.owner_id !== "joint" ? `<br>(${esc(mem(it.owner_id).name)}님이 정해요)` : ""}</span>`}</td>
   <td>${ro ? "" : `<button class="btn sm" data-act="del-fin" data-i="${i}" aria-label="빼기">빼기</button>`}</td></tr>`;
}
/* ---------- 목표 카테고리와 필수 입력값(서버 llm/goals.py와 같은 정의를 /api/config로 받는다) ---------- */
const GI = () => CFG && CFG.goal_input;
const giState = () => F().goal_input;
function giFields() {
  const gi = giState(), c = GI();
  if (!gi || !c || !c.categories[gi.category]) return [];
  const base = c.categories[gi.category].fields;
  if (gi.category !== "other") return base;
  const eng = c.other_engine_map[(gi.fields || {}).engine_kind];
  return eng ? [...base, ...c.other_extra[eng]] : base;
}
function giProblem() { // 빠진 값 안내(다 채웠으면 빈 글)
  const gi = giState();
  if (!GI()) return "";
  if (!gi || !gi.category) return "이루고 싶은 목표를 하나 골라 주세요";
  for (const f of giFields()) {
    const v = gi.fields?.[f.key];
    if (v == null || String(v).trim() === "") { if (f.decide) continue; return `'${f.label}'을(를) 입력해 주세요`; }
    if (f.kind === "number" && !(v >= f.min && v <= f.max)) return `'${f.label}'은(는) ${f.min}~${f.max}${f.unit || ""} 사이로 적어 주세요`;
  }
  return "";
}
function giField(f) {
  const gi = giState(), v = gi.fields?.[f.key] ?? "", ro = presetLocked() ? "disabled" : "", path = `goal_input.fields.${f.key}`;
  let ctl;
  if (f.kind === "number") ctl = `<div class="amt-in"><input ${ro} data-bind="${path}" data-num value="${v}" inputmode="decimal"><span>${esc(f.unit || "")}</span></div>`;
  else if (f.kind === "choice") ctl = `<div class="chips gopts">${f.options.map(o => `<button type="button" class="chip ${v === o ? "on" : ""}" ${ro} data-act="gi-set" data-k="${f.key}" data-v="${esc(o)}">${esc(o)}</button>`).join("")}</div>`;
  else if (f.kind === "member") ctl = `<select ${ro} data-bind="${path}"><option value="">고르세요</option>${F().members.map(m => `<option value="${m.member_id}" ${v === m.member_id ? "selected" : ""}>${esc(m.name || "이름 없음")}(${m.age ?? "?"}세)</option>`).join("")}</select>`;
  else ctl = `<input ${ro} data-bind="${path}" value="${esc(v)}" maxlength="${f.max || 30}">`;
  const tag = f.decide ? `<i class="req opt">선택</i>` : `<i class="req">필수</i>`;
  const hint = f.decide ? "잘 모르겠으면 비워 두세요. 공동 목표 설정에서 우리 가족 숫자를 보며 함께 정해요." : "";
  return `<div class="gfield"><span class="gl">${esc(f.label)} ${tag}</span>${ctl}${[f.help, hint].filter(Boolean).map(t => `<span class="cs">${esc(t)}</span>`).join("")}</div>`;
}
function s1() {
  const s = S(), f = F(), st = s.story, u = st.result, p = s.profile;
  const author = f.room.host_member_id;
  const rows = f.finance.map(finRow).join("");
  const cats = GI()?.categories || {}, gi = giState(), prob = giProblem();
  return `<div class="head"><div class="eyebrow">우리 가족 이야기</div><h1 class="h1">우리 가족의 목표와 지금 상황을 알려 주세요</h1><p class="lead">목표를 고르고 그 목표에 필요한 값을 넣어 주세요. 얼마를 언제까지 모을지는 몰라도 괜찮아요. 공동 목표 설정에서 함께 정해요. 더 하고 싶은 이야기는 자유롭게 적으면 돼요.</p></div>
  <div class="warnbox"><b>실제 계좌 정보나 정확한 금액은 넣지 마세요.</b> 체험판이라 대략적인 값이나 가상의 값으로 충분해요. 입력한 내용은 서버에 저장하지 않아요.</div>
  <section class="sec"><h2 class="st">1. 가장 이루고 싶은 목표를 하나 골라 주세요</h2>
   <div class="gcats">${Object.entries(cats).map(([k, c]) => `<button type="button" class="gcat ${gi?.category === k ? "on" : ""}" ${presetLocked() ? "disabled" : ""} data-act="gi-cat" data-c="${k}">${esc(c.label)}</button>`).join("")}</div>
   ${gi?.category && cats[gi.category] ? `<div class="gfields"><p class="cs" style="margin-bottom:10px">'${esc(cats[gi.category].label)}'에 필요한 값이에요. '선택'인 금액·기한은 감이 안 오면 비워 둬도 돼요.</p>${giFields().map(giField).join("")}</div>` : `<p class="cs" style="margin-top:8px">우리 가족의 목표가 목록에 없으면 '기타'를 골라 주세요.</p>`}
   ${presetLocked() ? `<p class="cs" style="margin-top:8px">예시 가족이라 목표와 값은 정해져 있어요.</p>` : ""}</section>
  <section class="sec"><h2 class="st">2. ${esc(mem(author).name)}님이 쓰는 우리 가족 이야기 <span class="cs">자유롭게</span></h2>
   <textarea ${presetLocked() ? "readonly" : ""} data-bind="story.text" data-reset="story" maxlength="1500" style="min-height:130px" placeholder="예: 결혼 1년 차 부부예요. 전세에 살고 있고, 2년 안에 아이를 갖고 싶어요. 남편은 집을 빨리 사자는 쪽이고 저는 아이가 먼저라는 생각이에요.">${esc(f.story.text)}</textarea>
   <p class="cs" style="margin-top:6px">목표 말고도 사는 곳, 각자의 생각 차이, 걱정되는 것을 자유롭게 써 주세요. 1,500자까지.</p></section>
  <section class="sec"><h2 class="st">3. 금융 정보 <span class="cs">단위 만원 · 체험용 값</span></h2>
   <div class="finblock mydata"><div class="fb-h"><h3 class="st3">마이데이터로 불러오기</h3><span class="tagsoft">체험판에서는 쓸 수 없어요</span></div>
    <p class="cs">실제 서비스에서는 내가 동의하면 흩어진 금융 정보를 자동으로 가져와요(마이데이터). 체험판에서는 아래 '직접 입력'에 넣어 주세요.</p>
    <button type="button" class="btn sm" disabled>마이데이터 연결하기</button></div>
   <div class="finblock direct"><div class="fb-h"><h3 class="st3">직접 입력</h3></div>
   <p class="cs" style="margin-bottom:8px">내 항목은 가족에게 보일 범위를 내가 골라요(공개 / 비공개). 비공개 항목도 계산에는 들어가요.</p>
   <div class="ftab-wrap"><table class="ftab fin"><thead><tr><th>누구 것</th><th>종류</th><th>이름</th><th>금액</th><th>가족에게 보이기</th><th></th></tr></thead><tbody>${rows || `<tr><td colspan="6" class="cs" style="padding:14px">아직 항목이 없어요. 아래 버튼으로 더해 주세요.</td></tr>`}</tbody></table></div>
   ${presetLocked() ? `<p class="cs" style="margin-top:8px">예시 가족이라 이야기와 금액은 정해져 있어요. 가족에게 보일 범위(공개·비공개)는 바꿔 볼 수 있어요.</p>` : ""}
   <div class="row" style="margin-top:10px" ${presetLocked() ? "hidden" : ""}><button class="btn sm" data-act="add-fin" data-kind="income">+ 매달 들어오는 돈</button><button class="btn sm" data-act="add-fin" data-kind="expense">+ 생활비</button><button class="btn sm" data-act="add-fin" data-kind="deposit">+ 예금·투자</button><button class="btn sm" data-act="add-fin" data-kind="loan">+ 대출</button><button class="btn sm" data-act="add-fin" data-kind="home">+ 집·보증금</button></div></div></section>
  <section class="sec"><h2 class="st">AI가 이해한 내용</h2>
   ${!started(st) && st.status !== "error" ? `<button class="btn primary" data-act="understand" ${prob ? "disabled" : ""}>목표와 금융 정보 정리 맡기기</button>${prob ? `<p class="cs" style="margin-top:8px;color:var(--warm)">${esc(prob)}</p>` : ""}` : ""}
   ${pend(st, "AI가 이야기를 읽고 있어요", "understand")}
   ${u ? `<div>${[["가족 단계", u.family_stage], ["사는 곳", u.living], ["함께 이루고 싶은 것", u.shared_goal], ["생각이 다른 부분", (u.differences || []).join(" · ")]].map(r => `<div class="urow"><span>${r[0]}</span><b>${esc(r[1])}</b></div>`).join("")}</div>${vbadge(st.verification, st.calls)}` : ""}
   ${p && u ? `<div class="urow"><span>한 달 들어오는 돈</span><b>${won(p.income_total)}</b></div><div class="urow"><span>한 달 나가는 돈</span><b>${won(p.expense_total)}${p.loan_payment_total ? ` · 대출 상환 ${won(p.loan_payment_total)}` : ""}</b></div><div class="urow"><span>예금·투자</span><b>${won(p.liquid_total)}</b></div><p class="cs">합계는 AI가 아니라 코드가 계산했어요.</p>` : ""}
  </section>${next("각자의 생각 듣기", !(u && u.family_stage), prob || "AI 정리를 받으면 다음으로 넘어갈 수 있어요")}`;
}

/* ---------- 화면 2: 각자의 생각 ---------- */
const ivState = mid => { const s = S(); return s.iv[mid] || (s.iv[mid] = { answers: [], review: {}, resolve: {}, clar: null, review2: {}, summary: null, confirmed: false }); };
// 질문 = 고정 3개 + 가족 이야기를 보고 AI가 만든 그 사람 맞춤 질문 0~2개(우리 가족 이야기 정리 때 함께 만듦). 대화를 시작하면 고정한다
const ivQs = mid => { const st = ivState(mid); if (!st.qs || !st.answers.length) st.qs = [...CFG.questions.map(q => ({ text: q.text, easy: q.easy })), ...(S().story.result?.member_questions?.[mid] || []).map(q => ({ ...q, extra: true }))]; return st.qs; };
const qText = (mid, i) => { const q = ivQs(mid)[i]; return mem(mid).easy_mode ? q.easy : q.text; };
const KNUM = ["", "한", "두", "세", "네", "다섯"];
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
  const qs = ivQs(mid), qMsg = i => ai(esc(qText(mid, i)) + (qs[i].extra ? `<div class="cs">가족 이야기 속 “${esc(qs[i].from)}” 부분을 보고 ${esc(m.name)}님께 따로 여쭤봐요</div>` : ""));
  let h = ai(`${esc(m.name)}님, 안녕하세요. ${KNUM[qs.length] || qs.length} 가지만 여쭤볼게요. 이 대화는 ${esc(m.name)}님만 볼 수 있어요.`);
  st.answers.forEach((a, i) => { h += qMsg(i) + me(a); });
  if (st.answers.length < qs.length) h += qMsg(st.answers.length);
  else if (!started(st.review) && st.review.status !== "error") h += `<div class="sysnote">질문에 모두 답했어요</div>`;
  h += pend(st.review, "AI가 대화를 정리하고 있어요", `retry-review:${mid}`);
  const d = st.review.result;
  if (d && d.ambiguous && d.ambiguous.length && st.clar) {
    h += ai(esc(d.question));
    h += ai(esc(d.easy_question));
    const picked = st.clar.choice;
    h += `<div class="choices">${d.choices.map((t, i) => `<button class="choice ${picked === i ? "on" : ""} ${i === d.choices.length - 1 ? "muted" : ""}" data-act="clar" data-mid="${mid}" data-i="${i}" ${st.clar.state !== "asking" || mid !== viewer() || (DEMO && i !== 0) ? "disabled" : ""}><span class="n">${i + 1}</span>${esc(t)}</button>`).join("")}</div>`;
    if (st.clar.retry && st.clar.state === "asking") h += me(st.clar.lastAnswer) + ai("제가 잘 알아듣지 못했어요. 아래에서 가까운 것을 골라 주시거나, 조금 더 자세히 말씀해 주세요.");
    if (st.clar.answer && st.clar.state !== "asking") h += me(st.clar.answer);
    h += pend(st.resolve, "AI가 답을 확인하고 있어요", `retry-resolve:${mid}`);
    if (st.clar.state === "done") h += ai(esc(st.resolve.result.confirm_message)) + me("네, 맞아요.");
    if (st.clar.state === "later") h += ai("괜찮아요. 편하실 때 다시 답해 주세요. 이 말의 뜻이 정해지기 전에는 AI가 짐작해서 계산하지 않아서, 요약도 그때 함께 공유해요.");
    h += pend(st.review2, "AI가 요약을 다시 만들고 있어요", `retry-review2:${mid}`);
  }
  const sm = st.summary;
  if (sm) h += ai(`가족에게 공유할 요약을 만들었어요. 확인해 주세요.<div class="sumcard"><dl><dt>꼭 지키고 싶은 것</dt><dd>${esc(sm.keep)}</dd><dt>양보할 수 있는 것</dt><dd>${esc(sm.flexible)}</dd><dt>가장 큰 걱정</dt><dd>${esc(sm.worry)}</dd>${sm.details?.length ? `<dt>그 밖에 정한 것</dt><dd>${sm.details.map(esc).join(" · ")}</dd>` : ""}</dl></div>${vbadge((st.review2.verification) || st.review.verification, st.review2.calls || st.review.calls)}`);
  return h;
}
function s2() {
  const s = S(), vw = viewer(), m = mem(vw), st = ivState(vw);
  let action = "";
  if (st.answers.length < ivQs(vw).length) {
    const ex = s.scripts?.answers?.[vw]?.[st.answers.length];
    action = DEMO && !ex ? `<textarea id="ans" maxlength="500">아직 정하지 못했어요. 가족과 같이 정하고 싶어요.</textarea><div class="crow"><span class="cs" style="flex:1">맞춤 질문은 예시 답이 없어요. 고쳐 써도 돼요</span><button class="btn primary sm" data-act="send-ans">보내기</button></div>`
      : DEMO ? `<textarea id="ans" readonly>${esc(ex || "")}</textarea><div class="crow"><span class="cs" style="flex:1">체험판이라 예시 답 그대로 보내요</span><button class="btn primary sm" data-act="send-ans">보내기</button></div>`
      : `<textarea id="ans" maxlength="500" placeholder="${esc(m.name)}님의 답을 적어 주세요">${esc(st.draft || "")}</textarea><div class="crow">${ex ? `<button class="btn sm" data-act="fill-ans">예시 답 넣기</button>` : ""}<button class="btn primary sm" data-act="send-ans">보내기</button></div>`;
  } else if (!started(st.review) && st.review.status !== "error") action = `<button class="btn primary" data-act="finish" data-mid="${vw}">대화 마치고 AI 요약 받기</button>`;
  else if (st.clar?.state === "asking" && DEMO) action = `<span class="cs">체험판이라 1번 답으로 이어가요</span>`;
  else if (st.clar?.state === "asking") action = `<input id="clarTxt" placeholder="또는 직접 적어 주세요" maxlength="200"><button class="btn sm" data-act="clar-text" data-mid="${vw}">보내기</button>`;
  else if (st.clar?.state === "later") action = `<span class="cs">질문에 답해야 요약을 공유할 수 있어요. 다른 가족이 먼저 이야기해도 괜찮아요.</span><button class="btn primary sm" data-act="clar-resume" data-mid="${vw}">지금 답하기</button>`;
  else if (st.summary && !st.confirmed) action = `<button class="btn primary" data-act="confirm" data-mid="${vw}">요약 확인하고 가족에게 공유하기</button>`;
  else if (st.confirmed) action = `<span class="cs">✓ 요약을 가족에게 공유했어요</span>`;
  const fam = F().members.map(x => {
    const xs = ivState(x.member_id), sm = xs.summary;
    const pending = xs.clar && xs.clar.state !== "done";
    let body;
    if (xs.confirmed && sm) body = `<dl><dt>꼭 지키고 싶은 것</dt><dd>${esc(sm.keep)}${pending ? ` <span class="pend">· 뜻을 여쭤보는 중</span>` : ""}</dd><dt>양보할 수 있는 것</dt><dd>${esc(sm.flexible)}</dd><dt>가장 큰 걱정</dt><dd>${esc(sm.worry)}</dd>${sm.details?.length ? `<dt>그 밖에 정한 것</dt><dd>${sm.details.map(esc).join(" · ")}</dd>` : ""}</dl>
      <div class="meta"><span>✓ 본인 확인 후 공유</span>${xs.clar?.state === "done" ? "<span>AI가 한 번 더 여쭤보고 정리했어요</span>" : ""}${x.member_id !== vw ? "<span>🔒 대화 내용 비공개</span>" : ""}</div>`;
    else if (xs.review.status === "loading") body = `<div class="pending"><span class="spin"></span>AI가 정리하고 있어요</div>`;
    else body = `<div class="cs" style="margin:8px 0 0 44px">${xs.clar?.state === "later" ? "AI가 한 가지를 다시 여쭤보는 중이에요(나중에 답하기)" : xs.clar?.state === "asking" ? "AI가 한 가지를 다시 여쭤보는 중이에요" : xs.answers.length ? `대화 중이에요(${xs.answers.length}/${ivQs(x.member_id).length})` : "아직 대화하지 않았어요"}</div>`;
    return `<div class="fm"><div class="fh">${av(x.member_id)}<span class="nm">${esc(x.name)}</span><span class="rl">${esc(x.role)}</span>${x.member_id === vw ? '<span class="me">나</span>' : ""}</div>${body}</div>`;
  }).join("");
  const left = mids().filter(x => !ivState(x).confirmed);
  return `<div class="head"><div class="eyebrow">각자의 생각</div><h1 class="h1">가족 한 사람씩 AI 상담사와 따로 이야기해요</h1><p class="lead">AI 상담사가 가족 모두에게 같은 세 가지를 묻고, 가족 이야기를 보고 그 사람에게 필요한 질문을 한두 개 더 해요. 뜻이 분명하지 않은 말이 있으면 AI가 그 사람에게만 다시 여쭤봐요.</p></div>
  <div class="privacy"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" stroke-width="2" style="margin-top:2px"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg><div><b>대화 내용은 본인만 볼 수 있어요</b><span>가족에게는 AI가 정리하고 본인이 확인한 요약만 공유돼요. 공유 단계의 AI에도 원문 대화는 들어가지 않아요. 체험판에서는 같은 기기를 쓰니, 다른 사람 차례에는 화면을 넘겨 주세요.</span></div></div>
  <div class="cols keep2">
   <div class="chatwin"><div class="chatbar"><span class="aimark">${AIMARK}</span><div class="cb"><b>AI 상담사</b><span>${esc(m.name)}님과의 1:1 대화 · 나만 볼 수 있어요</span></div>${m.easy_mode ? `<span class="easy">간편 모드 · 큰 글씨</span>` : ""}</div>
    <div class="chat ${m.easy_mode ? "big" : ""}" id="chat">${chatHtml(vw)}</div>
    <div class="composer ${st.answers.length < ivQs(vw).length ? "col" : ""}" style="justify-content:flex-end">${action}</div></div>
   <div class="card"><div class="ct">가족 모두의 의견</div><div class="cs" style="margin-bottom:8px">AI가 정리하고 본인이 확인한 요약이에요</div><div class="fam">${fam}</div>${turn(left, "대화")}</div>
  </div>${next("가족 모두의 생각 함께 보기", left.length > 0, "가족 모두 요약을 공유하면 다음으로 넘어갈 수 있어요")}`;
}

/* ---------- 화면 3: 공동 목표 설정 ---------- */
const summariesOf = () => Object.fromEntries(mids().map(m => [m, ivState(m).summary ? { keep: ivState(m).summary.keep, flexible: ivState(m).summary.flexible, worry: ivState(m).summary.worry, details: ivState(m).summary.details || [] } : null]).filter(x => x[1]));
const clarList = () => mids().filter(m => ivState(m).clar?.state === "done").map(m => ({ member_id: m, word: ivState(m).clar.word, meaning: ivState(m).clar.meaning }));
const KIND_LABEL = { order: "순서가 달라요", method: "방법이 달라요", amount: "금액이 달라요", value: "가치가 달라요" };
const REPLY_LBL = { good: "좋아요", cond: "괜찮아요, 단", other: "다른 의견이 있어요" };
const MAX_PAGES = 3; // 제안은 최대 3번까지 고친다. 그래도 모이지 않으면 이야기가 필요한 부분을 안내한다(서버 llm/pipeline.py MAX_ROUNDS_PER_CYCLE과 같게)
// 생각이 갈리는 부분 카드: 위치(좌·우)로 나누지 않고, 사람마다 자기 말로 한 줄 입장을 보여 준다
function issueCard(is) {
  const rows = F().members.filter(m => is.stances && is.stances[m.member_id] != null).map(m =>
    `<div class="strow">${av(m.member_id)}<div><div class="snm">${esc(m.name)}</div><div class="say">${esc(is.stances[m.member_id])}</div></div></div>`).join("");
  return `<div class="icard"><div class="ihead"><h4>${esc(is.title)}</h4>${KIND_LABEL[is.kind] ? `<span class="itag k-${esc(is.kind)}">${KIND_LABEL[is.kind]}</span>` : ""}</div>
   <div class="strows">${rows}</div><div class="ishared"><span class="dot" aria-hidden="true"></span><span><b>함께 지키고 싶은 것</b> · ${esc(is.shared)}</span></div></div>`;
}
const roundsOf = () => S().pg.map(x => ({ proposal: x.prop.text, reasons: x.prop.reasons, replies: x.replies }));
const analysisOf = () => { const r = S().goal.result; return { headline: r.headline, agreed_points: r.agreed_points, issues: r.issues }; };
const once = (slot, fn) => setTimeout(() => { if (!started(slot)) fn(); }, 0);
function pushPage(res) { const s = S(); s.pg.push({ prop: res.result.proposal, replies: {} }); s.pgView = null; s.rev = {}; }
// 제안 한 쪽: 먼저 제안, 그다음 이유(~한 이유로 이렇게 제안했어요), 낸 의견을 어떻게 반영했는지, 모두의 지키고 싶은 것
function propBox(pg, n) {
  const p = pg.prop;
  return `<div class="aibox prop"><div class="plabel">${n > 1 ? "의견을 모아 다시 제안해요" : "이렇게 해 보면 어때요?"}</div>
   <p class="q">${tipText(p.text, p.tips)}</p>
   ${p.changed ? `<p class="chg"><b>바뀐 점</b> ${esc(p.changed)}</p>` : ""}
   <div class="why3"><b>이런 이유로 제안했어요</b><ul>${p.reasons.map(r => `<li>${tipText(r, p.tips)}</li>`).join("")}</ul>${p.tips?.length ? `<p class="cs">밑줄 친 근거를 누르면 금융감독원 금융꿀팁 원문이 보여요</p>` : ""}</div>
   ${p.heard && Object.keys(p.heard).length ? `<div class="heard"><b>낸 의견은 이렇게 반영했어요</b>${Object.entries(p.heard).map(([m, t]) => `<div class="hrow">${av(m, "sm")}<span><b>${esc(mem(m).name)}님</b> ${esc(t)}</span></div>`).join("")}</div>` : ""}
   <div class="covers"><b>모두의 지키고 싶은 것을 담았어요</b>${F().members.filter(m => p.covers && p.covers[m.member_id]).map(m => `<div class="hrow">${av(m.member_id, "sm")}<span><b>${esc(m.name)}님</b> ${esc(p.covers[m.member_id])}</span></div>`).join("")}</div>
   <div class="to">받는 사람 ${p.to.map(m => av(m, "sm")).join("")} ${p.to.map(m => esc(mem(m).name) + "님").join(", ")}</div></div>`;
}
const replyList = pg => {
  const rows = pg.prop.to.filter(m => pg.replies[m]).map(m => { const r = pg.replies[m];
    return `<div class="reply2 v-${r.v}">${av(m, "sm")}<div><b>${esc(mem(m).name)}님${m === viewer() ? " (나)" : ""}</b><span class="vtag">${REPLY_LBL[r.v]}</span>${r.text ? `<p>${esc(r.text)}</p>` : ""}</div></div>`; });
  return rows.length ? `<div class="replies2">${rows.join("")}</div>` : "";
};
// 의견 남기기: 좋아요 / 괜찮아요, 단 … / 다른 의견이 있어요 (뒤의 둘은 내용을 꼭 적는다)
function replyBox(n) {
  const s = S(), vw = viewer(), d = s.rd[vw] || { v: null, text: "" }, ex = s.scripts?.rounds?.[n - 1]?.[vw];
  const head = `<div class="rl">${av(vw, "sm")}${esc(mem(vw).name)}님의 의견을 남겨 주세요</div>`;
  if (DEMO) {
    const e = ex || { v: "good", text: "" };
    return `<div class="act">${head}<div class="rbtns">${["good", "cond", "other"].map(k => `<span class="rb ${e.v === k ? "on v-" + k : ""}">${REPLY_LBL[k]}</span>`).join("")}</div>${e.text ? `<textarea readonly>${esc(e.text)}</textarea>` : ""}
     <div class="row"><span class="cs" style="flex:1">체험판이라 예시 의견 그대로 보내요</span><button class="btn primary sm" data-act="reply-demo">이 의견 보내기</button></div></div>`;
  }
  return `<div class="act">${head}<div class="rbtns">${["good", "cond", "other"].map(k => `<button type="button" class="rb ${d.v === k ? "on v-" + k : ""}" data-act="reply-pick" data-v="${k}">${REPLY_LBL[k]}</button>`).join("")}</div>
   ${d.v && d.v !== "good" ? `<textarea id="myReply" maxlength="500" placeholder="${d.v === "cond" ? "어떤 조건이 필요한지 적어 주세요 (예: 휴직 중 생활비는 꼭 지켜 주세요)" : "어떤 다른 생각이 있는지 적어 주세요"}">${esc(d.text || "")}</textarea>` : ""}
   <div class="row"><span style="flex:1"></span>${ex ? `<button class="btn sm" data-act="fill-round">예시 의견 넣기</button>` : ""}<button class="btn primary sm" data-act="reply-send" ${d.v ? "" : "disabled"}>의견 보내기</button></div></div>`;
}
// 2단계에 보여 주는 확정된 목표(읽기만 한다. 값은 '우리 가족 이야기'에서 가족이 입력한 것)
function goalCard(g) {
  const yrs = g.within_months ? g.within_months / 12 : 0;
  const rows = [["목표", esc(g.label)], ["계산 종류", GT[g.type]]];
  if (g.type === "reach_target") rows.push(["목표 금액", won(g.target_amount)]);
  if (g.within_months) rows.push(["언제까지", (yrs % 1 === 0 ? yrs : yrs.toFixed(1)) + "년 안"]);
  if (g.type === "runway" && g.base_member_id) rows.push(["나이 기준", esc(mem(g.base_member_id).name) + "님"]);
  return `<div class="goalcard">${rows.map(r => `<div class="urow"><span>${r[0]}</span><b>${r[1]}</b></div>`).join("")}</div>`;
}
/* 2단계: 목표를 숫자로 정하기(우리 가족 기준은 서버 llm/goal_size.py가 엔진으로 계산. AI는 숫자를 정하지 않는다) */
function applySize(sz) {
  const s = S();
  s.size = sz;
  if (!sz) return;
  s.goalForm = sz.goal_raw;
  s.goalChk = sz.goal ? { status: "done", goal: sz.goal } : sz.missing.length ? { status: "missing" } : { status: "bad", message: sz.message };
}
async function sizeUpdate(keep) { // keep: 세상 기준 지역만 바꿀 때(숫자는 그대로라 동의를 지우지 않는다)
  const s = S();
  if (!keep) { s.approvals = {}; reset("design"); }
  try { applySize(await api("/api/goal/size", { family: F(), values: s.goalNums, world: s.worldSel })); }
  catch (e) { s.goalChk = { status: "bad", message: e.message }; }
  render();
}
function worldBox(w) { // 세상 기준: 공공 통계·제도 원문으로 코드가 만든 값(서버 llm/world_size.py)
  if (!w) return "";
  const o = w.options, sel = (k, list, cur) => `<select data-world="${k}">${list.map(x => `<option value="${x.code}" ${x.code === cur ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select>`;
  return `<h3 class="st3" style="margin-top:14px">세상 기준 <span class="cs">공공 통계·제도 원문</span></h3>
   ${o ? `<div class="row" style="gap:8px;margin:6px 0">${sel("region", o.regions, w.region)}${sel("type", o.types, w.type)}</div>` : ""}
   ${w.message ? `<p class="cs">${esc(w.message)}</p>` : ""}
   <div>${w.lines.map(l => `<div class="urow"><span>${esc(l.label)}${l.note ? `<br><small class="cs">${esc(l.note)}</small>` : ""}</span><b>${esc(l.display)}</b></div>`).join("")}</div>
   ${w.sources?.length ? `<p class="cs">출처: ${w.sources.map(esc).join(" · ")}. 참고용이고, 우리 집 숫자는 가족이 정해요.</p>` : ""}`;
}
function stepTwoSize() {
  const s = S(), sz = s.size, crit = s.criterion, vw = viewer();
  const ready = s.goalChk.status === "done", allApproved = ready && mids().every(m => s.approvals[m]);
  const fields = sz.fields.map(f => `<div class="gfield"><span class="gl">${esc(f.label)}${f.entered ? ` <span class="cs">· 우리 가족 이야기에서 적은 값</span>` : ""}</span>
    <div class="amt-in"><input data-gnum="${f.key}" inputmode="decimal" value="${s.goalNums[f.key] ?? ""}" placeholder="${f.entered ? "" : "함께 정해 주세요"}"><span>${esc(f.unit || "")}</span></div></div>`).join("");
  const lines = sz.anchors.lines.map(l => `<div class="urow"><span>${esc(l.label)}${l.note ? `<br><small class="cs">${esc(l.note)}</small>` : ""}</span><b>${esc(l.display)}</b></div>`).join("");
  return `<section class="sec"><h2 class="st">2단계 · 목표를 숫자로 정하고 모두 동의하기</h2><p class="cs" style="margin-bottom:10px">1단계에서 모두 '좋아요'라고 한 방향으로, 이제 목표의 크기를 정해요. 숫자를 바꾸면 우리 가족 기준이 바로 다시 계산돼요. 숫자는 가족이 정하고, 어떻게 이룰지는 다음 단계(미래 계산)에서 함께 봐요.</p>
   ${pend(crit, "AI가 기준 문장을 정리하고 있어요", "retry-criterion")}
   ${crit.result ? `<div class="aibox"><p class="q">${esc(crit.result.criterion)}</p>${crit.result.size_note ? `<p class="sub"><b>숫자를 정할 때 생각해 볼 점</b> ${esc(crit.result.size_note)}</p>` : ""}</div>${vbadge(crit.verification, crit.calls)}
   ${fields ? `<div class="gfields">${fields}</div>` : `<p class="cs">이 목표는 우리 가족 이야기에서 적은 값으로 정해져 있어요.</p>`}
   ${lines ? `<h3 class="st3" style="margin-top:14px">우리 가족 기준 <span class="cs">지금처럼 지낼 때 · 계산엔진이 계산</span></h3><div>${lines}</div>${sz.anchors.note ? `<p class="cs">${esc(sz.anchors.note)}</p>` : ""}` : ""}
   ${worldBox(sz.world)}
   ${s.goalChk.status === "missing" ? `<p class="cs" style="margin-top:10px;color:var(--warm)">정할 숫자를 모두 넣으면 동의할 수 있어요.</p>` : ""}
   ${s.goalChk.status === "bad" ? `<div class="failbox"><b>이 목표는 계산할 수 없어요</b>${esc(s.goalChk.message || "")}<br>위의 숫자를 고쳐 주세요.</div>` : ""}
   ${ready ? `<h3 class="st3" style="margin-top:14px">정한 목표</h3>${goalCard(s.goalForm)}<div class="agreelist">${F().members.map(m => `<div class="agr">${av(m.member_id)}<div><div class="nm">${esc(m.name)}</div><div class="cm">${s.approvals[m.member_id] ? "동의했어요" : "아직 답하지 않았어요"}</div></div>${m.member_id === vw && !s.approvals[vw] ? `<button class="btn primary sm" data-act="approve">동의해요</button>` : ""}</div>`).join("")}</div>
   <p class="cs">숫자를 바꾸면 동의를 다시 받아요.</p>
   ${allApproved ? `<p class="okline"><span class="chk">✓</span><span><b>가족 모두 이 목표에 동의했어요.</b> 이 목표로 방법을 설계하고 계산할게요.</span></p>` : turn(mids().filter(m => !s.approvals[m]), "동의")}` : ""}` : ""}</section>`;
}
function s3() {
  const s = S(), g = s.goal, vw = viewer();
  const head = r => `<div class="head"><div class="eyebrow">공동 목표 설정</div>${r ? `<div class="refreshrow"><button class="btn sm" data-act="goal-refresh" title="이 단계의 내용을 지우고 처음부터 다시 받아요">↻ 내용 새로고침</button></div><p class="big">${esc(r.headline)}</p>` : `<h1 class="h1">가족의 생각을 함께 읽고 있어요</h1>`}</div>`;
  if (!mids().every(m => ivState(m).confirmed)) return head() + `<div class="aibox"><p class="q">아직 모든 가족의 요약이 모이지 않았어요.</p></div>` + next("", true, "");
  const lockBy = mids().find(m => ivState(m).clar && ivState(m).clar.state !== "done");
  if (lockBy) {
    const w = ivState(lockBy).review.result.ambiguous[0].word;
    return head() + `<section class="sec"><h2 class="st">AI의 제안을 준비하고 있어요</h2><div class="aibox"><p class="q">${esc(mem(lockBy).name)}님이 말씀하신 '${esc(w)}'의 뜻을 아직 확인하지 못했어요.</p><p class="sub">AI는 짐작해서 계산하지 않아요. 다른 가족에게 묻지 않고, ${esc(mem(lockBy).name)}님께 1:1로 다시 여쭤볼게요.</p></div><div class="actrow"><button class="btn primary" data-act="reask" data-mid="${lockBy}">${esc(mem(lockBy).name)}님과 1:1로 확인하기</button></div></section>` + next("", true, "");
  }
  if (s.story.status !== "done") return head() + `<div class="aibox"><p class="q">우리 가족 이야기의 AI 정리가 먼저 필요해요.</p></div><div class="actrow"><button class="btn" data-act="go" data-i="1">우리 가족 이야기로 가기</button></div>`;
  if (!started(g) && g.status !== "error") setTimeout(() => run(g, "/api/goal/analyze", { family: F(), summaries: summariesOf(), story_understanding: s.story.result, clarifications: clarList() }), 0);
  if (g.status !== "done") return head() + pend(g.status ? g : { status: "loading" }, "AI가 쟁점을 정리하고 공동 목표를 제안하고 있어요", "retry-goal");
  const r = g.result;
  if (!s.pg.length && r.proposal) s.pg = [{ prop: r.proposal, replies: {} }];
  const pgs = s.pg, N = pgs.length, cur = pgs[N - 1];
  const issuesHtml = `<section class="sec"><h2 class="st">이미 같은 생각인 부분</h2><ul class="agree">${r.agreed_points.map(a => `<li><span class="chk">✓</span><span>${esc(a)}</span></li>`).join("")}</ul></section>
  <section class="sec"><h2 class="st">생각이 갈리는 부분</h2><p class="cs" style="margin-bottom:10px">각자 확인한 요약을 바탕으로 AI가 정리했어요(대화 원문은 쓰지 않아요)</p>${r.issues.map(issueCard).join("")}</section>`;
  if (!cur) return head(r) + issuesHtml + `<section class="sec"><h2 class="st">1단계 · AI의 제안</h2><div class="failbox"><b>제안을 만들지 못했어요</b><br><button class="btn sm" data-act="retry-goal">다시 시도</button></div></section>` + next("방법별로 미래 계산하기", true, "제안이 있어야 해요");
  const view = s.pgView == null ? N - 1 : Math.min(s.pgView, N - 1), isLast = view === N - 1, pgv = pgs[view];
  const to = cur.prop.to;
  const allReplied = to.every(m => cur.replies[m]);
  const allGood = allReplied && to.every(m => cur.replies[m].v === "good");
  const needRev = allReplied && !allGood;
  const stuck = needRev && N - s.cycleStart >= MAX_PAGES;
  const crit = s.criterion;
  if (needRev && !stuck && !started(s.rev) && s.rev.status !== "error")
    once(s.rev, () => run(s.rev, "/api/goal/revise", { family: F(), summaries: summariesOf(), analysis: analysisOf(), rounds: roundsOf(), clarifications: clarList() }, pushPage));
  if (stuck && !started(s.stuck) && s.stuck.status !== "error")
    once(s.stuck, () => run(s.stuck, "/api/goal/stuck", { family: F(), summaries: summariesOf(), rounds: roundsOf() }));
  if (allGood && !s.backPending && !started(crit) && crit.status !== "error")
    once(crit, () => run(crit, "/api/goal/criterion", { family: F(), summaries: summariesOf(), proposal: cur.prop.text, reasons: cur.prop.reasons, replies: cur.replies, story_understanding: s.story.result },
      res => { const kept = Object.keys(s.goalNums || {}).length ? s.goalNums : null; applySize(res.size || null); if (!res.size) { s.goalForm = { ...res.result.goal }; s.goalChk = res.goal_check.ok ? { status: "done", goal: res.goal_check.goal } : { status: "bad", message: res.goal_check.message }; } s.goalNums = res.size ? (kept || Object.fromEntries(res.size.fields.map(f => [f.key, f.value]))) : {}; s.approvals = {}; if (res.size && kept) sizeUpdate(true); }));
  const pager = N > 1 ? `<div class="pager"><button class="btn sm" data-act="pg-view" data-d="-1" ${view === 0 ? "disabled" : ""}>‹ 이전 제안</button><b>제안 ${view + 1}/${N}</b><button class="btn sm" data-act="pg-view" data-d="1" ${isLast ? "disabled" : ""}>다음 제안 ›</button></div>` : "";
  const stuckBox = () => { const st = s.stuck; return `<div class="stuck"><h3 class="st3">서로 이야기가 필요한 부분이에요</h3>${pend(st.status ? st : { status: "loading" }, "이야기가 필요한 부분을 정리하고 있어요", "retry-stuck")}
    ${st.result ? `<p class="q2">${esc(st.result.message)}</p>${st.result.topics.map(issueCard).join("")}
     <div class="act"><div class="rl">가족끼리 이야기를 나눈 뒤, 나눈 내용을 적고 다시 제안받아요</div><textarea id="discTxt" maxlength="300" placeholder="예: 집은 지키되, 병원비가 모자라면 그때 다시 이야기하기로 했어요">${esc(s.discDraft || "")}</textarea>
      ${pend(s.rev, "나눈 이야기를 반영해 다시 제안하고 있어요", "disc-go")}<div class="row"><span class="cs" style="flex:1">AI는 결정을 대신하지 않아요. 가족이 직접 이야기한 뒤에 눌러 주세요.</span><button class="btn primary sm" data-act="disc-go">이야기 나눴어요, 다시 제안받기</button></div></div>` : ""}</div>`; };
  const stepOne = `<section class="sec"><h2 class="st">1단계 · AI의 제안과 가족의 의견</h2>
   ${pager}${propBox(pgv, view + 1)}${replyList(pgv)}
   ${!isLast ? `<p class="cs" style="margin-top:10px">지난 제안이에요. <button class="btn sm" data-act="pg-last">가장 최근 제안으로</button></p>` : ""}
   ${isLast && !allReplied ? (to.includes(vw) && !cur.replies[vw] ? replyBox(N) : "") + turn(to.filter(m => !cur.replies[m]), "의견") : ""}
   ${isLast && needRev && !stuck ? pend(s.rev.status ? s.rev : { status: "loading" }, "모두의 의견을 모아 더 공평한 제안을 만들고 있어요", "retry-rev") : ""}
   ${isLast && stuck ? stuckBox() : ""}
   ${isLast && allGood ? `<p class="okline"><span class="chk">✓</span><span><b>가족 모두 '좋아요'라고 했어요.</b> 이 제안으로 목표를 정리해요.</span></p>` : ""}</section>`;
  const ready = s.goalChk.status === "done";
  const allApproved = ready && mids().every(m => s.approvals[m]);
  if (s.backPending) return head(r) + issuesHtml + `<section class="sec"><h2 class="st">1단계 · AI의 제안과 가족의 의견</h2>${pager}${propBox(pgv, view + 1)}${replyList(pgv)}
    <div class="aibox"><p class="q">합의안 단계에서 가족 모두가 고른 방법이 없어 돌아왔어요.</p><p class="sub">${esc(s.backPending.reason)}</p></div>
    ${pend(s.rev.status ? s.rev : { status: "loading" }, "돌아온 이유를 반영해 공동 목표를 다시 제안하고 있어요", "retry-back")}</section>`;
  const stepTwo = allGood ? (s.size ? stepTwoSize() : `<section class="sec"><h2 class="st">2단계 · 가족 모두의 최종 동의</h2><p class="cs" style="margin-bottom:10px">1단계에서 모두 '좋아요'라고 한 제안으로 목표를 정리했어요. 맞으면 동의해 주세요. 다음 단계에서 이 목표로 미래를 계산해요.</p>
   ${pend(crit, "AI가 기준 문장을 정리하고 있어요", "retry-criterion")}
   ${crit.result && s.goalForm ? `<div class="aibox"><p class="q">${esc(crit.result.criterion)}</p></div>${vbadge(crit.verification, crit.calls)}${goalCard(s.goalForm)}
   ${s.goalChk.status === "bad" ? `<div class="failbox"><b>이 목표는 계산할 수 없어요</b>${esc(s.goalChk.message)}<br><button class="btn sm" data-act="go" data-i="1">우리 가족 이야기에서 값 고치기</button></div>` : ""}
   ${ready ? `<div class="agreelist">${F().members.map(m => `<div class="agr">${av(m.member_id)}<div><div class="nm">${esc(m.name)}</div><div class="cm">${s.approvals[m.member_id] ? "동의했어요" : "아직 답하지 않았어요"}</div></div>${m.member_id === vw && !s.approvals[vw] ? `<button class="btn primary sm" data-act="approve">동의해요</button>` : ""}</div>`).join("")}</div>
   ${allApproved ? `<p class="okline"><span class="chk">✓</span><span><b>가족 모두 이 목표에 동의했어요.</b> 이 목표로 방법을 설계하고 계산할게요.</span></p>` : turn(mids().filter(m => !s.approvals[m]), "동의")}` : ""}` : ""}</section>`) : "";
  return head(r) + issuesHtml + stepOne + stepTwo + next("방법별로 미래 계산하기", !allApproved, "가족 모두 동의하면 다음으로 넘어갈 수 있어요");
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
const kpiHtml = (r, g, ok, ret) => `<div class="kpis"><div class="kpi ${ok ? "good" : "bad"}"><div class="kl">${METRIC[g.type]}</div><div class="kv">${esc(r.goal_hit_display)}</div><div class="kn">${kpiNote(r, g)}</div></div>
    <div class="kpi"><div class="kl">첫 달에 늘거나 줄어드는 돈</div><div class="kv" style="font-size:22px">${(r.monthly_flow > 0 ? "+" : "") + won(r.monthly_flow)}</div></div>
    <div class="kpi"><div class="kl">돈을 불리는 방식</div><div class="kv" style="font-size:19px;line-height:1.4;margin-top:4px">${T("수익률")} 연 ${ret}%</div></div></div>`;
// 그래프 바로 아래의 숫자 조절: 움직이면 그래프와 위의 핵심 숫자가 곧바로 바뀐다(계산은 서버의 계산엔진)
function liveTuner(i, ret) {
  const s = S(), cur = s.ovIn[i] || {}, delta = cur.delta ?? 0, rv = cur.ret ?? ret;
  return `<div class="tuner"><div class="tuner-h"><b>숫자를 바꿔 보세요</b><span class="cs">움직이면 위 그래프가 바로 바뀌어요</span></div>
   <div class="sliders live">
    <div class="sl"><label>한 달에 더 모으거나(+) 덜 모으는(−) 돈 <b id="svOut">${delta > 0 ? "+" : ""}${delta}만원</b></label><input type="range" id="sv" min="-100" max="100" step="10" value="${delta}"></div>
    <div class="sl"><label>1년에 불어나는 비율(${T("수익률")}) <b id="rrOut">${(+rv).toFixed(1)}%</b></label><input type="range" id="rr" min="0" max="10" step="0.5" value="${rv}"></div>
   </div><p class="cs tuner-note" id="ovNote">${s.override[i] ? `직접 바꾼 값으로 계산했어요. <button class="btn sm" data-act="reset-ov">원래대로</button>` : "원래 값이에요."}</p></div>`;
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
   ${interp.easy ? `<div class="aibox easybox"><p><b>쉽게 말하면</b> ${esc(interp.easy)}</p></div>` : ""}${(() => { const n = (d.design_notes || []).find(x => x.option_id === sp.option_id); return n?.why ? `<p class="why"><b>이렇게 설계한 근거</b> ${tipText(n.why, n.tips)}${n.tips?.length ? ` <span class="cs">(밑줄을 누르면 금융감독원 금융꿀팁 원문)</span>` : ""}</p>` : ""; })()}${vbadge(d.verification, d.calls)}
   <div id="kpiSlot">${kpiHtml(r, g, ok, ret)}</div>
   <div class="chg2"><b>이 방법이 바꾼 것</b><ul>${changes.map(c => `<li>${esc(c)}</li>`).join("")}</ul></div>
   <div class="livebox"><div class="chart-wrap" id="chartSlot">${chart(r, g)}</div>
   ${liveTuner(i, ret)}</div>
   <p class="readme">${g.type === "reach_target" ? "선이 올라갈수록 모인 돈이 많아요. 선이 점선(목표)에 닿는 때가 목표를 이루는 때예요." : g.type === "runway" ? "선은 예금에 남은 돈이에요. 아래 점선(0원)에 닿으면 예금을 다 쓴 거예요." : "선은 남은 대출이에요. 아래 점선(0원)에 닿으면 대출을 다 갚은 거예요."}</p>
   ${r.range ? `<details class="tune"><summary>운이 좋을 때와 나쁠 때도 보기(보조 정보)</summary><p class="cs" style="margin-top:8px">같은 계획을 ${r.range.paths}번, 매번 다른 경기 상황을 가정해 계산했어요. ${g.type === "reach_target" ? `운이 좋으면 ${r.range.p10_hit_month ? (r.range.p10_hit_month / 12).toFixed(1) + "년" : "-"}, 보통 ${r.range.p50_hit_month ? (r.range.p50_hit_month / 12).toFixed(1) + "년" : "-"}, 운이 나쁘면 ${r.range.p90_hit_month ? (r.range.p90_hit_month / 12).toFixed(1) + "년" : "기간 안에 못 모임"}${g.within_months ? ` · ${g.within_months / 12}년 안에 모일 가능성 ${Math.round(r.range.prob_reach_within * 100)}%` : ""}` : `끝까지 예금이 남을 가능성 ${Math.round((r.range.prob_last_through ?? 0) * 100)}%`}</p></details>` : ""}
  </section>
  <section class="sec"><h2 class="st">이렇게 계산했어요</h2>
   <table class="btab"><thead><tr><th>항목</th><th>값</th><th>어디서 나왔나요</th></tr></thead><tbody>${r.basis.map(b => `<tr><td class="bk">${esc(b.label)}</td><td class="bv num">${esc(b.display)}</td><td class="bd">${esc(b.detail || retSource(b))}<span class="src">${esc({ financial_snapshot: "가족이 넣은 금융정보", option: "AI가 고른 방법", goal_setting: "공동 목표", assumption: "가정" }[b.source] || (b.source.startsWith("assumption") ? "가정(공개)" : b.source))}</span></td></tr>`).join("")}</tbody></table>
   <p class="how2"><b>계산 방법</b> 매달 ① 남아 있는 돈에 한 달 치 이자를 붙이고 ② 그달에 늘거나 줄어드는 돈(생활비에는 ${T("물가")} 오름 반영)과 대출 상환을 더하고 빼요. 이걸 ${g.horizon_months}개월 동안 반복했어요. 세금은 넣지 않았고, 수익률·물가·주택연금은 공개된 가정값이에요.</p>
   <details class="tune"><summary>해마다 계산한 표 보기</summary><div class="ytab-wrap"><table class="ytab num"><thead><tr><th>${g.type === "runway" ? esc(mem(g.base_member_id).name) + "님 나이" : "연도"}</th><th>해의 시작</th><th>늘거나 줄어든 돈</th><th>이자로 불어난 돈</th>${hasLoan ? "<th>대출 상환</th><th>남은 대출</th>" : ""}<th>해의 끝</th><th>${T("순자산")}</th></tr></thead><tbody>${yr}</tbody></table></div></details>
  </section>
  <section class="sec"><h2 class="st">한 사람 한 사람에게 달라지는 점</h2><div>${F().members.map(m => `<div class="irow">${av(m.member_id)}<div><div class="nm">${esc(m.name)}</div><p>${esc((interp.per_member || {})[m.member_id] || "")}</p></div></div>`).join("")}</div></section>
  ${next("가족이 함께 고르기")}`;
}

/* ---------- 화면 5: 합의안 ---------- */
const optLabel = sp => `${sp.option_id}. ${sp.label}`;
// 의사 표시: 괜찮은 방법을 모두 누르기만 한다(2026-11-08 형님 결정, 조건·이유는 받지 않는다).
// 누른 방법 = 괜찮아요, 누르지 않은 방법 = 어려워요. 모두가 누른 방법이 합의안이 되고, 없으면 공동 목표 설정으로 돌아간다(수정안 없음)
const isOk = x => x && x.v !== "no";
function stanceRows(rd, opts) {
  const s = S(), vw = viewer(), R1 = rd === 1 ? s.r1 : s.r2, mine = R1[vw] || {};
  const demoFill = DEMO ? `<div class="row"><span class="cs" style="flex:1">체험판이라 예시 의사 그대로 남겨요</span><button class="btn sm" data-act="fill-stance" data-rd="${rd}">예시 의사 채우기</button></div>` : "";
  return demoFill + `<p class="cs" style="margin:4px 0 8px">받아들일 수 있는 방법을 모두 눌러 주세요. 하나만 골라도, 여러 개 골라도 돼요.</p>
   <div class="okcards">${opts.map(([oid, label, res]) => { const on = isOk(mine[oid]); return `<button type="button" class="okcard ${on ? "on" : ""}" ${DEMO ? "disabled" : ""} data-act="okpick" data-rd="${rd}" data-oi="${oid}" aria-pressed="${on}">
    <span class="okhead"><span class="okbox" aria-hidden="true">${on ? "✓" : ""}</span><span><b>${esc(label)}</b>${res ? `<span class="cs">${esc(res)}</span>` : ""}</span></span>
    <span class="okstate ${on ? "v-good" : ""}">${on ? "✓ 괜찮아요" : "눌러서 고르기"}</span></button>`; }).join("")}</div>`;
}
function famTable(rd, opts) {
  const s = S(), R1 = rd === 1 ? s.r1 : s.r2, SB = rd === 1 ? s.sub1 : s.sub2;
  const cell = x => !x ? `<span class="rv wait-v">기다리는 중</span>` : isOk(x) ? `<span class="rv v-good"><b>✓ 괜찮아요</b></span>` : `<span class="rv v-no"><b>− 안 골랐어요</b></span>`;
  return `<div class="famtab-wrap"><table class="famtab"><thead><tr><th>방법</th>${F().members.map(m => `<th>${av(m.member_id, "sm")} ${esc(m.name)}</th>`).join("")}</tr></thead><tbody>${opts.map(([oid, label]) => `<tr><td class="ol2">${esc(label)}</td>${F().members.map(m => `<td>${SB[m.member_id] ? cell((R1[m.member_id] || {})[oid]) : cell(null)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
function consentState() {
  const s = S(), d = s.design;
  if (!d.specs) return {};
  const ids = d.specs.map(l => l.option_id);
  const all1 = mids().every(m => s.sub1[m]);
  const cand1 = all1 ? ids.filter(oid => mids().every(m => isOk((s.r1[m] || {})[oid]))) : [];
  const noCommon = all1 && cand1.length === 0;
  let final = null;
  if (all1 && cand1.length) { const sp = d.specs[ids.indexOf(cand1[0])]; final = { spec: sp, label: optLabel(sp) }; }
  return { all1, cand1, noCommon, final, conds: [] };
}
// 모두가 고른 방법이 없을 때 공동 목표로 넘길 말(누가 무엇을 골랐는지). 가족에게 이유를 따로 묻지 않는다
function pickSummary() {
  const s = S(), d = s.design;
  return d.specs.map(sp => { const who = mids().filter(m => isOk((s.r1[m] || {})[sp.option_id])).map(m => mem(m).name + "님");
    const l = optLabel(sp), c = l.charCodeAt(l.length - 1), topic = c >= 0xac00 && c <= 0xd7a3 && (c - 0xac00) % 28 ? "은" : "는";
    return `${l}${topic} ${who.length ? who.join("·") + "만 괜찮다고 했어요" : "아무도 고르지 않았어요"}`; }).join(", ");
}
function s5() {
  const s = S(), d = s.design, vw = viewer(), goal = d.goal || goalNow();
  const head = `<div class="head"><div class="eyebrow">합의안</div><h1 class="h1">아무도 반대하지 않는 방법을 함께 찾아요</h1><p class="lead">점수를 더하지 않아요. 각자 받아들일 수 있는 방법을 모두 누르고, 가족 모두가 누른 방법이 합의안이 돼요. 모두가 누른 방법이 없으면 공동 목표부터 다시 이야기해요.</p></div>`;
  if (d.status !== "done") return head + `<div class="aibox"><p class="q">미래 계산이 먼저 필요해요.</p></div>`;
  if (!started(s.check) && s.check.status !== "error") setTimeout(() => run(s.check, "/api/agreement/check", { family: F(), goal: s.goalForm, specs: d.specs, summaries: summariesOf() }), 0);
  const opts1 = d.specs.map((sp, k) => [sp.option_id, optLabel(sp), results()[k].goal_hit_display]);
  const cs = consentState();
  const kc = s.check.result;
  let h = head + `<section class="sec"><h2 class="st">먼저, 각자 꼭 지키고 싶은 것으로 살펴봤어요</h2>${pend(s.check, "AI가 방법마다 점검표를 만들고 있어요", "retry-check")}
   ${kc ? `<div class="famtab-wrap"><table class="famtab kc"><thead><tr><th>방법</th>${F().members.map(m => `<th>${av(m.member_id, "sm")} ${esc(m.name)}<span class="kp">${esc(ivState(m.member_id).summary.keep)}</span></th>`).join("")}</tr></thead><tbody>${d.specs.map(sp => `<tr><td class="ol2">${esc(optLabel(sp))}</td>${F().members.map(m => { const c = (kc.keep_check[sp.option_id] || {})[m.member_id] || { ok: false, reason: "" }; return `<td><span class="kv2 ${c.ok ? "ok" : "ng"}"><b>${c.ok ? "✓ 지켜요" : "✕ 깨져요"}</b><span>${esc(c.reason)}</span></span></td>`; }).join("")}</tr>`).join("")}</tbody></table></div><p class="ailine">${esc(kc.note)}</p>${vbadge(s.check.verification, s.check.calls)}` : ""}</section>`;
  h += `<section class="sec"><h2 class="st">각자의 의사</h2>
   ${!s.sub1[vw] ? `<div class="act"><div class="rl">${av(vw, "sm")}${esc(mem(vw).name)}님, 방법마다 의사를 남겨 주세요</div>${stanceRows(1, opts1)}<div class="row"><span style="flex:1"></span><button class="btn primary sm" data-act="sub" data-rd="1">내 의사 보내기</button></div></div>` : ""}
   <div style="margin-top:16px">${famTable(1, opts1)}</div>${turn(mids().filter(m => !s.sub1[m]), "의사 표시")}
   ${cs.all1 && cs.cand1.length > 1 ? `<p class="cs" style="margin-top:10px">모두가 고른 방법이 ${cs.cand1.length}개예요. 앞 순서인 ${esc(cs.cand1[0])}를 합의안으로 삼았어요.</p>` : ""}</section>`;
  if (cs.noCommon) h += `<section class="sec"><h2 class="st">모두가 고른 방법이 없어요</h2><div class="aibox"><p class="q">${esc(pickSummary())}.</p>
    <p class="sub">합의안을 억지로 고르지 않고, 공동 목표부터 다시 이야기해요. AI가 누가 무엇을 골랐는지를 보고 공동 목표를 다시 제안해요. 미래 계산과 합의안은 그 목표로 다시 만들어요.</p></div>
    <div class="actrow"><button class="btn primary" data-act="back-goal">공동 목표 설정으로 돌아가기</button></div></section>`;
  const dr = s.draft;
  if (cs.final) {
    const key = JSON.stringify([cs.final.spec, cs.conds]);
    if (dr.key !== key) { Object.keys(dr).forEach(k => delete dr[k]); dr.key = key; s.signed = {}; }
    if (!started(dr) && dr.status !== "error") setTimeout(() => run(dr, "/api/agreement/draft", { family: F(), goal: s.goalForm, criterion: s.criterion.result.criterion, spec: cs.final.spec, method_label: cs.final.label, conditions: [], summaries: summariesOf(), version: s.version || 1, revision: null }), 0);
    const a = dr.result;
    h += `<section class="sec"><h2 class="st">가족 모두가 고른 방법</h2><p class="okline"><span class="chk">✓</span><span><b>${esc(cs.final.label)}</b> — 가족 모두 괜찮다고 했어요.</span></p>
     ${pend(dr, "AI가 합의안과 합의 리포트를 쓰고 있어요", "retry-draft")}
     ${a ? paper(a, dr) : ""}</section>`;
  }
  const allSigned = mids().every(m => s.signed[m]);
  return h + next("약속에 맞는 금융상품 보기", !allSigned, "가족 모두 서명하면 다음으로 넘어갈 수 있어요");
}
function backRevise() {
  const s = S(), b = s.backPending;
  return run(s.rev, "/api/goal/revise", { family: F(), summaries: summariesOf(), analysis: analysisOf(), rounds: roundsOf(), clarifications: clarList(),
    discussion: `합의안 단계에서 가족 모두가 고른 방법이 없어 공동 목표로 돌아왔어요. ${b.reason}` },
    res => { pushPage(res); s.stuck = {}; s.cycleStart = s.pg.length - 1; s.backPending = null; });
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
  const head = `<div class="head"><div class="eyebrow">상품 추천</div><h1 class="h1">합의안의 약속을 지켜 줄 금융상품 유형이에요</h1><p class="lead">AI는 약속을 '필요'와 '제약'으로 바꾸기만 하고, 상품 유형은 금융 온톨로지를 따라 코드가 골라요. 그래서 왜 이 상품인지 경로로 설명할 수 있어요. ${DEMO ? "" : `<a href="graph.html" target="_blank" rel="noopener">온톨로지 연결 그래프 보기 →</a>`}</p></div>`;
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
   <p class="disc">${CFG.real_products ? "위 카드는 상품 유형이고, 아래 실제 상품은 금감원 공시(개발용 예시)로 만든 정보예요." : "상품은 유형 예시이며 특정 금융회사 상품이 아니에요."} '확인 필요'는 공시·제도 안내로 확인해야 하는 항목이에요. 최종 선택과 가입은 본인이 결정해요.</p>${fitSections(a, recs)}${next("가족 홈으로 가기")}`;
}

/* 화면 6 아래: 필요마다 갈 수 있는 길(ontology/routes.py)과, 실제 상품이 있는 길은 우리 목표에 잘 맞는 순서(ontology/fit.py, AI 없음).
   개발용 공시 데이터가 있을 때만(CFG.real_products). 맞는 상품이 없으면 없다고, 데이터가 없으면 없다고 보여 준다. */
const wonK = v => { const a = Math.round(v * 10), c = a % 10; let m = Math.floor(a / 10); const e = Math.floor(m / 10000); m %= 10000;
  return ([e ? e + "억" : "", m ? m.toLocaleString("ko-KR") + "만" : "", c ? c + "천" : ""].filter(Boolean).join(" ") || "0") + "원"; };
const LOANS = ["mortgage", "rent_loan", "credit_loan", "busi_loan"];
const CAT_LABEL = { saving: "적금", deposit: "정기예금", mortgage: "주택담보대출", rent_loan: "전세자금대출", credit_loan: "개인신용대출", busi_loan: "개인사업자대출" };
const BANDS = { avg: "모름(평균)", "900+": "900점 초과", "801-900": "801~900점", "701-800": "701~800점", "601-700": "601~700점", "501-600": "501~600점", "401-500": "401~500점", "301-400": "301~400점", "300-": "300점 이하" };
const loanSum = types => F().finance.filter(x => x.kind === "loan" && types.includes(x.loan_type)).reduce((t, x) => t + (+x.amount || 0), 0) || null;
const finSum = kind => F().finance.filter(x => x.kind === kind).reduce((t, x) => t + (+x.amount || 0), 0) || null;
function fitState(nid, cat, r, a) {
  const s = S(), key = `${nid}|${cat}`;
  s.fit = s.fit || {};
  if (!s.fit[key]) {
    const c = (a.commitments || []).find(x => x.commitment_id === (r && r.commitment_id));
    const sum = (a.contribution || []).reduce((t, x) => t + (+x.amount || 0), 0);
    const debt = nid === "N_debt_repayment";
    const st = { member: (c && c.source && c.source.member_id) || F().room.host_member_id, all: false, open: {}, res: {}, actions: [],
      cno: r && /^c\d+$/.test(r.commitment_id || "") ? +r.commitment_id.slice(1) : null, ctext: c && c.text };
    if (cat === "saving" || cat === "deposit") {  // 사람 조건: 가족 구성원 중 18세 이하를 자녀 수로 미리 채움(바꿀 수 있음), 없으면 '모름'
      const minors = F().members.filter(m => m.age < 19).length;
      st.kids = minors ? Math.min(minors, 3) : null;
      st.flags = F().members.some(m => m.age <= 1) ? ["newborn"] : [];
    }
    if (cat === "saving") Object.assign(st, { monthly: nid === "N_goal_saving" && sum ? Math.round(sum) : null, term: 12 });
    if (cat === "deposit") Object.assign(st, { amount: null, term: 12 });
    if (cat === "mortgage") Object.assign(st, { amount: debt ? loanSum(["mortgage"]) : null, years: 30, repay: "split", rate_pref: "any", house: "아파트", home_price: debt ? finSum("home") : null });
    if (cat === "rent_loan") Object.assign(st, { amount: debt ? loanSum(["lease"]) : null, years: 2, repay: "bullet", deposit_amount: finSum("lease_deposit") });
    if (cat === "credit_loan") Object.assign(st, { amount: debt ? loanSum(["credit"]) : null, years: 3, repay: "split", band: "avg" });
    if (cat === "busi_loan") Object.assign(st, { amount: null, years: 5, repay: "split", band: "avg" });
    s.fit[key] = st;
  }
  if (!s.fit[key].flags) Object.assign(s.fit[key], { kids: null, flags: [] });  // 5단계 전에 저장된 진행 상태
  return s.fit[key];
}
function fitBody(nid, cat, st) {
  const base = { family: F(), need_id: nid, category: cat, member_id: st.member, commitment: st.cno ? { no: st.cno, text: st.ctext } : null };
  const person = { kids: st.kids, flags: st.flags };
  if (cat === "saving") return { ...base, monthly: st.monthly, term_months: st.term, actions: st.actions, person };
  if (cat === "deposit") return { ...base, amount: st.amount, term_months: st.term, actions: st.actions, person };
  const b = { ...base, amount: st.amount, months: st.years * 12, repay: st.repay };
  if (cat === "mortgage") Object.assign(b, { rate_pref: st.rate_pref, house: st.house, home_price: st.home_price });
  if (cat === "rent_loan") Object.assign(b, { deposit_amount: st.deposit_amount });
  if (cat === "credit_loan" || cat === "busi_loan") b.band = st.band;
  return b;
}
function routeLine(nid) {
  const rt = (CFG.need_routes[nid] || {}).routes || [];
  const other = rt.filter(x => x.route !== "real" && x.route !== "program").map(x => x.route === "none" ? `${esc(x.label)}: 아직 실제 상품 데이터가 없어요(${esc(x.note)})`
    : x.route === "consult" ? `${esc(x.label)}: 전문가 상담으로 연결해요` : esc(x.note || x.label) + (x.note ? "" : ": 상품 없이 가족이 직접 지켜요"));
  return other.length ? `<ul class="routes">${other.map(t => `<li>${t}</li>`).join("")}</ul>` : "";
}
function fitSections(a, recs) {
  if (!CFG.real_products || !CFG.need_routes) return "";
  const seen = new Set(), needs = [];
  recs.forEach(r => { if (!seen.has(r.need_id) && CFG.need_routes[r.need_id]) { seen.add(r.need_id); needs.push(r); } });
  return needs.map(r => {
    const nid = r.need_id, cats = (CFG.need_routes[nid].routes || []).filter(x => x.route === "real").map(x => x.category);
    const hasProg = (CFG.need_routes[nid].routes || []).some(x => x.route === "program" && x.programs.length);
    return `<section class="fitsec"><h2 class="st">${esc(CFG.need_routes[nid].label)}</h2>${routeLine(nid)}
      ${hasProg ? progSection(nid) : ""}${cats.map(c => fitSection(nid, c, r, a)).join("")}</section>`;
  }).join("");
}
function ragPanel(key, kind, label) {
  // 법령 원문 찾기(rag/index.py): 판정이 아니라 설명·근거. 온톨로지와 독립이라 어떤 제도·상품인지와 상관없이 법령 전체에서 찾는다. 결과는 원문 그대로.
  if (!CFG.rag || !CFG.rag.available) return "";
  const s = S();
  s.rag = s.rag || {};
  const r = s.rag[key] || (s.rag[key] = { open: false, q: "", res: {} });
  const btn = `<button class="linkbtn" data-act="rag-open" data-k="${esc(key)}">${r.open ? "원문 찾기 닫기" : esc(label)}</button>`;
  if (!r.open) return btn;
  const tops = CFG.rag.topics[kind] || [];
  const topics = tops.map(([l, q]) => `<button class="${r.q === q ? "on" : ""}" data-act="rag-q" data-k="${esc(key)}" data-q="${esc(q)}">${esc(l)}</button>`).join("");
  const res = r.res, done = res.status === "done";
  const item = x => `<div class="ragitem"><div class="rh"><span class="rk">${esc(x.kind)}</span><b>${esc(x.doc_title)} · ${esc(x.title)}</b></div>
    <div class="rt">${esc(x.text).replace(esc(x.focus), `<mark>${esc(x.focus)}</mark>`)}</div>
    <div class="rs">${esc(x.publisher)}${x.effective_date ? ` · 시행 ${esc(x.effective_date)}` : ""} · ${esc(x.fetched_at)} 수집 · <a href="${esc(x.url)}" target="_blank" rel="noopener">원문 보기</a></div></div>`;
  const body = !res.status ? "" : !done ? pend(res, "법령 원문에서 찾고 있어요", null)
    : res.results.length ? `<p class="cs">${esc(res.note)}</p>${res.results.map(item).join("")}`
    : `<p class="cs">법령 원문에서 '${esc(res.query)}'와 관련된 부분을 찾지 못했어요. 다른 말로 찾아보거나 기관에 문의해 주세요.</p>`;
  const typed = r.q && !tops.some(t => t[1] === r.q) ? r.q : "";
  return `${btn}<div class="ragbox"><div class="acts">${topics}</div>
    <div class="ragq"><input data-rag="${esc(key)}" placeholder="궁금한 것을 적고 Enter (예: 비과세종합저축)" value="${esc(typed)}"></div>${body}</div>`;
}
function ragSearch(key, q) {
  const r = S().rag[key];
  r.q = q; r.res = {};
  run(r.res, "/api/rag/search", { query: q });
}
function progSection(nid) {
  const s = S();
  s.prog = s.prog || {};
  const slot = s.prog[nid] || (s.prog[nid] = {});
  if (!started(slot) && slot.status !== "error") setTimeout(() => run(slot, "/api/programs/judge", { family: F(), need_id: nid }), 0);
  if (slot.status !== "done") return pend(slot.status ? slot : { status: "loading" }, "제도 조건을 따져 보고 있어요", `prog-retry:${nid}`);
  const icon = { met: "✓", not_met: "✕", unknown: "?" }, cls = { eligible: "ok", not_eligible: "no", check: "chk" };
  const terms = t => [t.rate && t.rate.min != null ? `금리 연 ${t.rate.min}~${t.rate.max}%` : t.rate && t.rate.note ? esc(t.rate.note) : "",
    t.limit ? `한도 최대 ${won(t.limit.max_manwon)}${t.limit.ltv_pct ? ` (LTV ${t.limit.ltv_pct}%)` : ""}${t.limit.deposit_pct ? ` (보증금의 ${t.limit.deposit_pct}%)` : ""}${t.limit.note ? ` · ${esc(t.limit.note)}` : ""}` : "",
    t.monthly ? `매달 ${won(t.monthly.min_manwon)}~${won(t.monthly.max_manwon)}` : "",
    t.amount ? `월 최대 ${wonK(t.amount.monthly_manwon)}(${esc(t.amount.note)})` : ""].filter(Boolean).join(" · ");
  const card = g => {
    const open = (slot.open || {})[g.program_id];
    return `<div class="prog"><div class="ph"><b>${esc(g.label)}</b><span class="pk">${esc(g.publisher)} · ${esc(g.kind)}</span><span class="ps ${cls[g.status]}">${esc(g.status_text)}</span></div>
      <p class="cs">${esc(g.summary)}</p>
      <ul class="pconds">${g.conditions.map(c => `<li class="${c.status}"><i>${icon[c.status]}</i><span>${esc(c.label)}${c.hint ? `<em>${esc(c.hint)}</em>` : ""}</span></li>`).join("")}</ul>
      ${g.estimate ? `<p class="pest"><b>${esc(g.estimate.label)} 약 ${wonK(g.estimate.monthly_manwon)}</b><span>${esc(g.estimate.basis)}</span></p>` : ""}
      ${terms(g.terms) ? `<p class="cs">${terms(g.terms)}</p>` : ""}
      ${g.unmodeled.length ? `<p class="cs">기관이 확인하는 조건: ${g.unmodeled.map(u => esc(u.label)).join(" / ")}</p>` : ""}
      ${open ? `<div class="fev">${esc([...g.conditions.map(c => `· ${c.label}: "${c.quote}"`), ...g.facts.map(f => `· ${f.label}: "${f.quote}"`),
        ...Object.values(g.terms).filter(t => t.quote).map(t => `· "${t.quote}"`), `출처: ${g.publisher} 공식 안내(2026-11-03 수집) · 판정은 넣은 정보 기준이고, 최종 판단은 기관이 해요`].join("\n"))}</div>` : ""}
      <button class="linkbtn" data-act="prog-open" data-need="${nid}" data-pid="${g.program_id}">${open ? "근거 닫기" : "근거 보기(공식 원문)"}</button>
      ${ragPanel(`${nid}|${g.program_id}`, "law", "관련 법령 찾아보기")}</div>`;
  };
  return `<div class="progs"><h3 class="st3">제도 · 공식 안내 기준으로 따져 봤어요</h3>${slot.programs.map(card).join("")}</div>`;
}
function fitControls(key, cat, st, res) {
  const sel = (k, opts) => `<select data-fit="${k}" data-need="${key}">${opts.map(([v, l]) => `<option value="${v}" ${String(st[k]) === String(v) ? "selected" : ""}>${l}</option>`).join("")}</select>`;
  const num = (k, ph) => `<div class="amt-in"><input data-fit="${k}" data-need="${key}" inputmode="decimal" placeholder="${ph}" value="${st[k] ?? ""}"><span>만원</span></div>`;
  const who = `<label>누구 이름으로${sel("member", F().members.filter(m => !LOANS.includes(cat) || m.age >= 19 || m.member_id === st.member).map(m => [m.member_id, `${esc(m.name)}(${m.age}세)`]))}</label>`;
  const f = [who];
  if (cat === "saving") f.push(`<label>매달 넣을 돈${num("monthly", "예: 60")}</label>`, `<label>기간${sel("term", [6, 12, 24, 36].map(t => [t, t + "개월"]))}</label>`);
  if (cat === "deposit") f.push(`<label>한 번에 맡길 돈${num("amount", "예: 3000")}</label>`, `<label>기간${sel("term", [6, 12, 24, 36].map(t => [t, t + "개월"]))}</label>`);
  if (LOANS.includes(cat)) {
    f.push(`<label>빌릴 돈${num("amount", "예: 20000")}</label>`,
      `<label>기간${sel("years", (cat === "mortgage" ? [10, 20, 30, 40] : cat === "rent_loan" ? [1, 2, 4] : [1, 2, 3, 5, 10]).map(y => [y, y + "년"]))}</label>`,
      `<label>갚는 방식${sel("repay", [["split", "나눠 갚기"], ["bullet", "만기에 한 번에"]])}</label>`);
    if (cat === "mortgage") f.push(`<label>금리${sel("rate_pref", [["any", "상관없음"], ["fixed", "고정"], ["variable", "변동"]])}</label>`,
      `<label>집 종류${sel("house", [["아파트", "아파트"], ["아파트외", "아파트 외"]])}</label>`, `<label>집값(한도 계산)${num("home_price", "예: 40000")}</label>`);
    if (cat === "rent_loan") f.push(`<label>전세 보증금(한도 계산)${num("deposit_amount", "예: 25000")}</label>`);
    if (cat === "credit_loan" || cat === "busi_loan") f.push(`<label>신용점수${sel("band", Object.entries(BANDS))}</label>`);
  }
  const acts = res && res.actions && !LOANS.includes(cat) ? `<div class="cs">내가 할 수 있는 우대 조건을 고르면 받을 금리가 다시 계산돼요</div><div class="acts">${Object.entries(res.actions).map(([k, l]) => `<button class="${st.actions.includes(k) ? "on" : ""}" data-act="fit-act" data-need="${key}" data-k="${k}">${st.actions.includes(k) ? "✓ " : ""}${esc(l)}</button>`).join("")}</div>` : "";
  const me = F().members.find(m => m.member_id === st.member);
  const ps = res && res.person && !LOANS.includes(cat) ? `<div class="cs">나에게 해당하는 것을 고르면 사람 조건 우대·가입 조건을 따져요(가입할 때 금융회사가 증빙으로 확인해요). 나이는 ${esc(me.name)}님(${me.age}세) 기준이에요.</div>
    <div class="acts"><label class="kids">18세 이하 자녀${sel("kids", [["", "모름"], [0, "없음"], [1, "1명"], [2, "2명"], [3, "3명 이상"]])}</label>${Object.entries(res.person.options).map(([k, l]) => `<button class="${st.flags.includes(k) ? "on" : ""}" data-act="fit-flag" data-need="${key}" data-k="${k}">${st.flags.includes(k) ? "✓ " : ""}${esc(l)}</button>`).join("")}</div>` : "";
  return `<div class="fitctl">${f.join("")}</div>${acts}${ps}`;
}
function fitSection(nid, cat, r, a) {
  const st = fitState(nid, cat, r, a), key = `${nid}|${cat}`;
  if (!started(st.res) && st.res.status !== "error") setTimeout(() => run(st.res, "/api/products/fit", fitBody(nid, cat, st)), 0);
  const res = st.res.status === "done" ? st.res : null, loan = LOANS.includes(cat);
  const evS = x => { const e = x.evidence; return [`우대조건 원문\n${e.benefits.map(q => "· " + q).join("\n") || "· 없음"}`, e.join_member ? `가입대상: ${e.join_member}` : "",
    e.limit_quote ? `한도: ${e.limit_quote}` : "", e.caveats.length ? `유의: ${e.caveats.join(" / ")}` : ""]; };
  const evL = x => { const t = x.evidence.texts, L = { loan_lmt: "한도", loan_limit: "한도", loan_limit_detl: "한도(세부)", erly_rpay_fee: "중도상환 수수료", loan_inci_expn: "부대비용", dly_rate: "연체 이자율", join_deny: "가입조건", join_deny_detl: "가입조건(세부)", spcl_rate: "우대금리", loan_term: "대출기간" };
    return Object.entries(t).map(([k, v]) => `${L[k] || k}: ${v}`); };
  const ev = x => [...(loan ? evL(x) : evS(x)), `출처: 금감원 금융상품 한눈에 공시(${x.evidence.as_of.slice(0, 4)}년 ${+x.evidence.as_of.slice(4)}월) · 개발용 예시`].filter(Boolean).map(esc).join("\n\n");
  const meta = x => loan ? `${esc(x.provider)}${x.loan_kind ? " · " + esc(x.loan_kind) : ""}${x.rate_type ? " · " + (x.rate_type === "fixed" ? "고정" : "변동") : ""} · 연 ${x.rate_min.toFixed(2)}~${x.rate_max.toFixed(2)}%${x.limit_manwon ? ` · 한도 약 ${won(x.limit_manwon)}` : ""}`
    : `${esc(x.provider)} · ${x.term_months}개월 · ${esc(x.rsrv || "")} ${esc(x.rate_type || "")} · 기본 ${x.base_rate.toFixed(2)}% · 최대 ${(x.max_rate ?? x.base_rate).toFixed(2)}%${x.limit_manwon ? ` · ${cat === "saving" ? "월" : "최고"} ${won(x.limit_manwon)}까지` : ""}`;
  const tags = x => loan ? x.checks.map(c => `<span class="w">확인 필요 · ${esc(c)}</span>`).join("")
    : x.got.map(g => `<span class="g">${esc(g.label)} +${g.pp}</span>`).join("") + x.more.map(g => `<span>${esc(g.label)} 하면 +${g.pp}</span>`).join("")
      + x.maybe.map(g => `<span class="w">해당되면 · ${esc(g.label)} +${g.pp}</span>`).join("") + x.checks.map(c => `<span class="w">확인 필요 · ${esc(c)}</span>`).join("");
  const right = x => loan ? `<span>보통 받는 금리</span><b>${x.my_rate.toFixed(2)}%</b>${x.cost ? `<span>총 이자 약 ${wonK(x.total_cost)}</span>` : ""}`
    : `<span>내가 받을 금리</span><b>${x.my_rate.toFixed(2)}%</b>${x.money ? `<span>만기 약 ${wonK(x.money.total)}</span>` : ""}`;
  const row = (x, i) => `<div class="frow"><div class="rk">${i + 1}</div><div>
    <div class="fn">${esc(x.name)}</div><div class="fm">${meta(x)}</div><div class="ftags">${tags(x)}</div>
    ${i === 0 || st.open[x.product_id] ? `<ul class="freason">${x.reasons.map(t => `<li>${esc(t)}</li>`).join("")}</ul>` : ""}
    ${x.why_lower ? `<div class="flow">1번보다 아래인 이유: ${esc(x.why_lower)}</div>` : ""}
    ${st.open[x.product_id] ? `<div class="fev">${ev(x)}</div>` : ""}
    <button class="linkbtn" data-act="fit-open" data-need="${key}" data-pid="${x.product_id}">${st.open[x.product_id] ? "근거 닫기" : "근거 보기"}</button></div>
    <div class="rt">${right(x)}</div></div>`;
  let body;
  if (!res) body = pend(st.res.status ? st.res : { status: "loading" }, "상품 조건을 따져 보고 있어요", `fit-retry:${key}`);
  else {
    const sm = res.summary, items = res.items, okSt = sm.state === "ok";
    const money = cat === "saving" ? st.monthly : st.amount;
    body = `<div class="${okSt ? "fsum" : "fsum warn"}"><b>${esc(sm.text)}</b>${sm.why ? `<span>${esc(sm.why)}</span>` : ""}
      ${!okSt ? `<span>${money == null ? "금액을 넣으면 한도까지 따져 볼 수 있어요. " : ""}기간·금액·갚는 방식을 바꿔 보거나, 아래 '확인 필요' 상품은 금융회사에 직접 확인해 주세요.</span>` : ""}</div>
      ${money == null && items.length ? `<p class="cs">${loan ? "빌릴 돈을 적으면 총 이자와 한도까지 따져 순서를 정해요. 지금은 금리 순서예요." : "금액을 적으면 만기 금액과 한도까지 따져 순서를 정해요. 지금은 받을 금리 순서예요."}</p>` : ""}
      ${items.length && !okSt ? `<p class="cs">참고: 조건이 맞지 않거나 확인이 필요한 상품이에요.</p>` : ""}
      ${(st.all ? items : items.slice(0, res.shown)).map(row).join("")}
      ${items.length > res.shown ? `<button class="btn sm" style="margin-top:10px" data-act="fit-all" data-need="${key}">${st.all ? "5개만 보기" : `${items.length - res.shown}개 더 보기`}</button>` : ""}
      ${res.excluded && res.excluded.length ? `<p class="excl">${esc(res.member.name)}님(${res.member.age}세)은 가입 조건(나이·자녀·무주택)이 맞지 않아 ${res.excluded.length}개는 뺐어요.</p>` : ""}
      <p class="srcline">${esc(res.note)}${res.tax ? ` 세후 이자는 ${esc(res.tax.label)}를 뺀 값이에요.` : ""}${loan ? " 부대비용(인지세·보증료 등)은 계산에 넣지 않았어요." : ""}</p>
      ${loan ? "" : ragPanel(`${key}|law`, "law", "예금자보호·비과세 법령 찾아보기")}`;
  }
  return `<div class="fitcat"><h3 class="st3">${CAT_LABEL[cat]} · 우리 목표에 잘 맞는 순서예요</h3>${fitControls(key, cat, st, res)}${body}</div>`;
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
// 가족 홈 숫자(모두 계산엔진 결과. AI를 쓰지 않는다). base: 합의안을 확정한 날(없으면 오늘)
const krMonth = iso => { const [y, m] = iso.split("-").map(Number); return `${y}년 ${m}월`; };
const signedWon = v => (v > 0 ? "+" : v < 0 ? "−" : "") + won(Math.abs(v));
function homeKpis(goal, r, m3, base) {
  const hit = r.goal_hit_month, within = goal.within_months;
  const when = hit ? krMonth(addMonthsIso(base, hit)) : "계산 기간 안에는 어려워요";
  const gap = hit && within ? (hit <= within ? `기한보다 ${within - hit}개월 빨라요` : `기한보다 ${hit - within}개월 늦어요`) : "";
  const k = (label, value, note, tone) => `<div class="kpi"><span class="kl">${label}</span><b class="kv ${tone || ""}">${value}</b>${note ? `<span class="kn">${note}</span>` : ""}</div>`;
  const flow = goal.type === "runway" ? m3.inflow + m3.outflow : r.monthly_flow; // 모으기·대출은 합의안 '매달 모이는 돈'과 같은 값(첫 달)
  if (goal.type === "reach_target") return [
    k("목표까지 남은 돈", won(Math.max(0, goal.target_amount - m3.end)), `목표 ${won(goal.target_amount)}`),
    k("한 달에 모이는 돈", signedWon(flow), `이자·수익 ${won(m3.interest)}은 따로`, flow < 0 ? "neg" : ""),
    k("목표에 닿는 때", when, gap, hit && within && hit > within ? "neg" : "")].join("");
  if (goal.type === "debt_free") return [
    k("지금까지 갚은 돈", won(Math.max(0, r.start_debt - m3.debt)), `처음 대출 ${won(r.start_debt)}`),
    k("한 달 대출 상환", won(m3.loan_payment), "원금과 이자를 합친 금액"),
    k("다 갚는 때", r.debt_free_month ? krMonth(addMonthsIso(base, r.debt_free_month)) : "계산 기간 안에는 어려워요", gap)].join("");
  return [
    k("지금 예금", won(m3.end), ""),
    k("한 달에 늘거나 줄어드는 돈", signedWon(flow), "이자·수익은 따로", flow < 0 ? "neg" : ""),
    k("예금이 버티는 때", hit ? krMonth(addMonthsIso(base, hit)) + (r.age_at_hit ? ` · ${r.age_at_hit}세` : "") : "끝까지 버텨요", "")].join("");
}
function homeMonths(r, base) {
  const rows = r.monthly.slice(0, 3).map((m, i) => `<tr><td>${krMonth(addMonthsIso(base, i + 1))}</td><td class="n">${won(m.inflow)}</td><td class="n neg">−${won(-m.outflow)}${m.loan_payment ? `<small>대출 ${won(m.loan_payment)} 포함</small>` : ""}</td><td class="n">${m.lump ? signedWon(m.lump) : "−"}</td><td class="n">${won(m.interest)}</td><td class="n"><b>${won(m.end)}</b></td></tr>`).join("");
  return `<div class="ftab-wrap"><table class="numtab"><thead><tr><th>달</th><th>들어온 돈</th><th>나간 돈</th><th>큰돈</th><th>불어난 돈</th><th>달 말 잔액</th></tr></thead><tbody>${rows}</tbody></table></div>
   <p class="cs">달 말 잔액 = 지난달 잔액 + 들어온 돈 − 나간 돈 ± 큰돈 + 불어난 돈. 합의한 방법대로 지냈다고 가정한 값이에요.</p>`;
}
function homeAhead(goal, r, base) {
  const ys = [...new Set([1, 3, 5, goal.within_months ? Math.ceil(goal.within_months / 12) : 0].filter(y => y && y <= r.yearly.length))].sort((a, b) => a - b);
  const head = goal.type === "debt_free" ? "<th>남은 대출</th><th>갚은 비율</th>" : goal.type === "reach_target" ? "<th>모인 돈</th><th>목표 대비</th>" : "<th>남은 예금</th><th></th>";
  const row = y => { const v = r.yearly[y - 1], mark = goal.within_months && y === Math.ceil(goal.within_months / 12) ? ' <span class="tag">기한</span>' : "";
    const c = goal.type === "debt_free" ? `<td class="n">${won(v.debt_end)}</td><td class="n">${r.start_debt ? Math.round((1 - v.debt_end / r.start_debt) * 100) : 100}%</td>`
      : goal.type === "reach_target" ? `<td class="n">${won(v.end)}</td><td class="n">${Math.round(v.end / goal.target_amount * 100)}%</td>` : `<td class="n">${won(v.end)}</td><td></td>`;
    return `<tr><td>${y}년 뒤 · ${krMonth(addMonthsIso(base, y * 12))}${mark}</td>${c}</tr>`; };
  return `<div class="ftab-wrap"><table class="numtab"><thead><tr><th>언제</th>${head}</tr></thead><tbody>${ys.map(row).join("")}</tbody></table></div>`;
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
  const hist = s.history || [], base = s.signedAt || todayIso();
  return head + `<div class="homegrid"><div class="stackv">
   <div class="card goalcard"><div class="cs" style="font-weight:600">${esc(label)}</div><div class="gv">${big}</div>${goal.type !== "runway" ? `<div class="pbar"><i style="width:${pct}%"></i></div>` : ""}<div class="pmeta2"><span>합의 후 3개월 · 이대로면 ${esc(r.goal_hit_display)}${goal.type === "runway" ? "" : " 뒤"}</span><span class="num">${goal.type !== "runway" ? pct + "%" : ""}</span></div>
    <div class="kpis">${homeKpis(goal, r, m3, base)}</div></div>
   <div class="card"><div class="ct" style="margin-bottom:6px">지난 3개월 돈의 흐름</div>${homeMonths(r, base)}</div>
   <div class="card"><div class="ct" style="margin-bottom:6px">이대로 가면</div>${homeAhead(goal, r, base)}<p class="cs">합의한 방법(${esc(cs.final.label)})의 가정 수익률로 계산했어요. 실제와 달라지면 아래 재점검에서 바뀐 값을 넣어 보세요.</p></div>
   <div class="card"><div class="ct" style="margin-bottom:6px">이번 달 약속</div><div>${a.contribution.map(c => `<div class="trow done"><span class="c">✓</span><span class="tt">${esc(c.label)}<small class="cs" style="display:block">3개월 동안 ${won(Math.round(c.amount) * 3)}</small></span><span class="ta">월 ${won(c.amount)}</span></div>`).join("")}${a.report.action_plan.map(x => `<div class="trow"><span class="c"></span><span class="tt">${esc(x.what)}</span><span class="ta">${esc(x.when)}</span></div>`).join("")}</div></div>
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
  if (path.startsWith("story") || path.startsWith("finance") || path.startsWith("room") || path.startsWith("goal_input")) {
    if (s.story.status) s.story = {};
    s.profile = null; reset("goal");
  }
}
function bindInputs() {
  const s = S();
  if (DEMO) document.querySelectorAll("[data-demo-lock] select, [data-demo-lock] input").forEach(el => el.disabled = true);
  document.querySelectorAll("[data-rag]").forEach(el => el.onchange = () => { const q = el.value.trim().slice(0, 80); if (q) ragSearch(el.dataset.rag, q); });
  document.querySelectorAll("[data-fit]").forEach(el => el.onchange = () => {
    const st = s.fit[el.dataset.need], k = el.dataset.fit, v = el.value.trim().replace(/,/g, "");
    const money = ["monthly", "amount", "home_price", "deposit_amount"].includes(k);
    if (money && v !== "" && !(Number(v) >= 1 && Number(v) <= (k === "monthly" ? 10000 : 10000000))) { toast("금액은 만원 단위 숫자로 적어 주세요"); return; }
    st[k] = money ? (v === "" ? null : Number(v)) : ["term", "years"].includes(k) ? +v : k === "kids" ? (v === "" ? null : +v) : v;
    st.res = {}; render();
  });
  document.querySelectorAll("[data-world]").forEach(el => el.onchange = () => { s.worldSel[el.dataset.world] = el.value; sizeUpdate(true); });
  document.querySelectorAll("[data-gnum]").forEach(el => el.onchange = () => {
    const t = el.value.trim().replace(/,/g, ""), v = t === "" ? null : Number(t);
    if (v !== null && !Number.isFinite(v)) { toast("숫자로 적어 주세요"); return; }
    s.goalNums[el.dataset.gnum] = v; sizeUpdate();
  });
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
  document.querySelectorAll("[data-rv]").forEach(el => el.oninput = () => { (s.reviewIn = s.reviewIn || {})[el.dataset.rv] = el.value; });
  const ans = $("#ans"); if (ans) ans.oninput = () => { ivState(viewer()).draft = ans.value; };
  const mr = $("#myReply"); if (mr) mr.oninput = () => { const d = (s.rd[viewer()] = s.rd[viewer()] || { v: null, text: "" }); d.text = mr.value; };
  const dt = $("#discTxt"); if (dt) dt.oninput = () => { s.discDraft = dt.value; };
  const sv = $("#sv"), rr = $("#rr");
  if (sv && rr) {
    const paint = () => {
      const i = s.pick, g = s.design.goal || goalNow(), r = resultOf(i), ret0 = s.design.simulation.results[i].basis.find(x => x.key === "return").value;
      const ret = (s.ovIn[i] ? s.ovIn[i].ret : ret0), d = s.ovIn[i] ? s.ovIn[i].delta : 0;
      const cs = $("#chartSlot"), ks = $("#kpiSlot"), nt = $("#ovNote");
      if (cs) cs.innerHTML = chart(r, g);
      if (ks) ks.innerHTML = kpiHtml(r, g, kpiOk(r, g), ret);
      if (nt) nt.innerHTML = s.override[i] ? `직접 바꾼 값으로 계산했어요. <button class="btn sm" data-act="reset-ov">원래대로</button>` : "원래 값이에요.";
      $("#svOut").textContent = (d > 0 ? "+" : "") + d + "만원"; $("#rrOut").textContent = (+ret).toFixed(1) + "%";
      const opt = document.querySelector(`.opt[data-i="${i}"] .res`); if (opt) opt.textContent = r.goal_hit_display;
    };
    const fire = () => {
      const i = s.pick; s.ovIn[i] = { delta: +sv.value, ret: +rr.value };
      $("#svOut").textContent = (+sv.value > 0 ? "+" : "") + sv.value + "만원"; $("#rrOut").textContent = (+rr.value).toFixed(1) + "%";
      clearTimeout(bindInputs._t);
      const seq = bindInputs._seq = (bindInputs._seq || 0) + 1;
      bindInputs._t = setTimeout(async () => {
        try {
          const out = await api("/api/simulate", { family: F(), goal: s.goalForm, specs: [s.design.specs[i]], override: { monthly_delta: +sv.value, expected_return: +rr.value } });
          if (seq !== bindInputs._seq) return;  // 더 최근에 움직였으면 이 결과는 버린다
          s.override[i] = out.results[0]; paint(); save();
        } catch (e) { toast(e.message); }
      }, 120);
    };
    sv.oninput = fire; rr.oninput = fire;
    sv.onchange = rr.onchange = () => { setTimeout(render, 160); };
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
    const pr = giProblem(); if (pr) { toast(pr); return; }
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
  "retry-goal": () => { const s = S(); s.goal = {}; s.pg = []; s.pgView = null; s.rev = {}; s.stuck = {}; s.cycleStart = 0; render(); },
  "retry-criterion": () => { S().criterion = {}; render(); },
  "gi-cat": b => { if (presetLocked()) return; const f = F(); if (!f.goal_input || f.goal_input.category !== b.dataset.c) f.goal_input = { category: b.dataset.c, fields: {} }; famEdited("goal_input"); render(); },
  "gi-set": b => { if (presetLocked()) return; const gi = F().goal_input; gi.fields[b.dataset.k] = b.dataset.v; famEdited("goal_input"); render(); },
  "pg-view": b => { const s = S(), N = s.pg.length, cur = s.pgView == null ? N - 1 : s.pgView, nx = Math.max(0, Math.min(N - 1, cur + +b.dataset.d)); s.pgView = nx === N - 1 ? null : nx; render(); },
  "pg-last": () => { S().pgView = null; render(); },
  "reply-pick": b => { const s = S(), d = (s.rd[viewer()] = s.rd[viewer()] || { v: null, text: "" }); d.v = b.dataset.v; if (d.v === "good") d.text = ""; render(); },
  "fill-round": () => { const s = S(), ex = s.scripts?.rounds?.[s.pg.length - 1]?.[viewer()]; if (ex) { s.rd[viewer()] = { ...ex }; render(); } },
  "reply-send": () => {
    const s = S(), vw = viewer(), d = s.rd[vw];
    if (!d || !d.v) { toast("좋아요 / 괜찮아요, 단 / 다른 의견 중 하나를 골라 주세요"); return; }
    if (d.v !== "good" && (d.text || "").trim().length < 2) { toast(d.v === "cond" ? "어떤 조건이 필요한지 적어 주세요" : "어떤 다른 생각이 있는지 적어 주세요"); return; }
    s.pg[s.pg.length - 1].replies[vw] = { v: d.v, text: d.v === "good" ? "" : d.text.trim() }; delete s.rd[vw]; toast("의견을 보냈어요"); render();
  },
  "reply-demo": () => { const s = S(), vw = viewer(), ex = s.scripts?.rounds?.[s.pg.length - 1]?.[vw] || { v: "good", text: "" }; s.pg[s.pg.length - 1].replies[vw] = { v: ex.v, text: ex.text || "" }; toast("의견을 보냈어요"); render(); },
  "disc-go": () => {
    const s = S(), t = (s.discDraft || "").trim();
    if (t.length < 4) { toast("가족끼리 이야기 나눈 내용을 짧게 적어 주세요"); return; }
    run(s.rev, "/api/goal/revise", { family: F(), summaries: summariesOf(), analysis: analysisOf(), rounds: roundsOf(), clarifications: clarList(), discussion: t },
      res => { pushPage(res); s.stuck = {}; s.cycleStart = s.pg.length - 1; s.discDraft = ""; });
  },
  "retry-rev": () => { S().rev = {}; render(); },
  "back-goal": () => {
    const s = S();
    s.backPending = { reason: pickSummary().slice(0, 240) };
    reset("design"); s.criterion = {}; s.approvals = {}; s.rev = {};
    go(3); backRevise();
  },
  "retry-back": () => { const s = S(); s.rev = {}; backRevise(); },
  "goal-refresh": async () => {
    const ok = await ask("공동 목표 설정을 처음부터 다시 할까요?", "지금까지의 쟁점 정리, 제안과 의견, 2단계에서 정한 숫자와 동의, 그 뒤의 미래 계산·합의안이 지워지고 AI가 처음부터 다시 정리해요. 우리 가족 이야기와 각자의 요약은 그대로예요.", [{ label: "지우고 다시 받기", value: true, primary: true }]);
    if (!ok) return;
    reset("goal"); toast("공동 목표 설정을 처음부터 다시 해요"); render();
  },
  "retry-stuck": () => { S().stuck = {}; render(); },
  approve: () => { S().approvals[viewer()] = true; toast("동의했어요"); render(); },
  "retry-design": () => { reset("design"); render(); },
  pick: b => { S().pick = +b.dataset.i; render(); },
  "reset-ov": () => { const s = S(); delete s.override[s.pick]; delete s.ovIn[s.pick]; render(); },
  "retry-check": () => { S().check = {}; render(); },
  okpick: b => { const s = S(), rd = +b.dataset.rd, R1 = rd === 1 ? s.r1 : s.r2, vw = viewer(), oi = b.dataset.oi; R1[vw] = R1[vw] || {};
    const x = R1[vw][oi]; R1[vw][oi] = isOk(x) ? { v: "no", text: "" } : { v: "good", text: "" }; render(); },
  stance: b => { const s = S(), rd = +b.dataset.rd, R1 = rd === 1 ? s.r1 : s.r2, vw = viewer(), oi = b.dataset.oi, v = b.dataset.v; R1[vw] = R1[vw] || {}; const prev = R1[vw][oi] || {}; R1[vw][oi] = { v, text: v === "good" ? "" : prev.text || "" }; render(); },
  sub: b => { const s = S(), rd = +b.dataset.rd, R1 = rd === 1 ? s.r1 : s.r2, SB = rd === 1 ? s.sub1 : s.sub2, mine = (R1[viewer()] = R1[viewer()] || {});
    const ids = rd === 1 ? s.design.specs.map(sp => sp.option_id) : ["x"];
    ids.forEach(oid => { mine[oid] = isOk(mine[oid]) ? { v: "good", text: "" } : { v: "no", text: "" }; }); // 누르지 않은 방법 = 어려워요
    SB[viewer()] = true; toast("의사를 보냈어요"); render(); },
  "fill-stance": b => { const s = S(), rd = +b.dataset.rd, ex = ((window.ONEHEART.DEMO_STANCES || {})[room] || {})[rd === 1 ? "r1" : "r2"] || {};
    const mine = ex[viewer()]; if (!mine) { toast("이 사람의 예시 의사가 없어요"); return; }
    (rd === 1 ? s.r1 : s.r2)[viewer()] = JSON.parse(JSON.stringify(mine)); render(); },
  "redo-consent": () => { const s = S(); s.r1 = {}; s.sub1 = {}; s.revise = {}; s.r2 = {}; s.sub2 = {}; render(); },
  "retry-revise": () => { S().revise = {}; render(); },
  "retry-draft": () => { const d = S().draft; Object.keys(d).forEach(k => delete d[k]); render(); },
  sign: () => { const s = S(); s.signed[viewer()] = true; if (mids().every(m => s.signed[m]) && !s.signedAt) s.signedAt = todayIso(); toast("서명했어요"); render(); },
  "retry-rec": () => { S().rec = {}; S().fit = {}; S().prog = {}; render(); },
  "fit-flag": b => { const st = S().fit[b.dataset.need], k = b.dataset.k; st.flags = st.flags.includes(k) ? st.flags.filter(x => x !== k) : [...st.flags, k]; st.res = {}; render(); },
  "fit-act": b => { const st = S().fit[b.dataset.need], k = b.dataset.k; st.actions = st.actions.includes(k) ? st.actions.filter(x => x !== k) : [...st.actions, k]; st.res = {}; render(); },
  "fit-open": b => { const st = S().fit[b.dataset.need]; st.open[b.dataset.pid] = !st.open[b.dataset.pid]; render(); },
  "rag-open": b => { const r = S().rag[b.dataset.k]; r.open = !r.open; render(); },
  "rag-q": b => ragSearch(b.dataset.k, b.dataset.q),
  "prog-open": b => { const sl = S().prog[b.dataset.need]; sl.open = sl.open || {}; sl.open[b.dataset.pid] = !sl.open[b.dataset.pid]; render(); },
  "fit-all": b => { const st = S().fit[b.dataset.need]; st.all = !st.all; render(); },
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
    catch (e) { s.goalChk = {}; s.approvals = {}; go(1); toast("바뀐 상황에서는 목표 값을 다시 정해야 해요: " + e.message); }
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
  if (a.startsWith("prog-retry:")) { S().prog[a.slice(11)] = {}; render(); return; }
  if (a.startsWith("fit-retry:")) { S().fit[a.slice(10)].res = {}; render(); return; }
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
api("/api/health", null, "GET").then(h => { HEALTH = h; applyPublicMode(h); const p = $("#prov"); if (h.provider === "replay") { p.hidden = false; p.classList.add("replay"); p.textContent = "개발용 재생 모드 — 실제 AI 아님"; } if (h.provider === "mock") { p.hidden = false; p.classList.add("replay"); p.textContent = "mock 체험 · AI 답은 규칙으로 만든 예시(실제 AI 아님), 계산은 지금 실제로"; } }).catch(() => { const p = $("#prov"); p.hidden = false; p.textContent = "서버 연결 안 됨"; });
