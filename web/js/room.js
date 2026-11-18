/* 가족방(여러 기기) — 한 사람이 가족방을 만들면 가족마다 링크(?r=방번호&k=열쇠)를 받아 각자 화면에서 같은 가족방에 참여한다(2026-11-17).
   화면 상태 한 덩어리를 서버에 두고(server/rooms.py), 바뀐 만큼만 합쳐서 서로 받아 본다. app.js 다음에 불러온다(app.js의 R·S·render를 쓴다).
   - 합치기(mergeState): 내가 마지막으로 받은 상태(base) · 내 지금 상태(mine) · 서버 상태(theirs)를 3-way로 합친다. 서로 다른 곳을 고치면 둘 다 남고,
     같은 곳을 고쳤으면 내 것이 이긴다.
   - 기기마다 따로 두는 것(LOCAL): 보는 사람·단계·펼침 상태 같은 화면 설정은 서버로 보내지 않는다. */

const ROOMQ = new URLSearchParams(location.search);
const ROOM = {
  id: ROOMQ.get("r") || "", token: ROOMQ.get("k") || "", memberId: "", isHost: false,
  version: 0, tick: 0, base: null, timer: null, push: null, busy: false, pendingApply: null, fails: 0,
  get active() { return !!(this.id && this.token); },
  link(token) { return `${location.origin}${location.pathname}?r=${encodeURIComponent(this.id)}&k=${encodeURIComponent(token)}`; },
};
// 서버로 보내지 않는 키(어느 깊이에 있어도). 화면 설정이라 기기마다 달라야 한다.
ROOM.LOCAL = new Set(["viewer", "step", "maxStep", "rag", "fo", "open", "pgView", "cpView", "discDraft", "actualIn", "reviewIn", "backPending", "ovIn", "edit"]);

const isObj = v => v && typeof v === "object" && !Array.isArray(v);
const same = (a, b) => { // 값이 같은가(객체는 키 순서와 상관없이, undefined 값은 없는 것과 같게). 순서만 다른데 다르다고 보면 두 기기가 서로 되받아 쓰는 일이 끝나지 않는다
  if (a === b) return true;
  if (Array.isArray(a)) return Array.isArray(b) && a.length === b.length && a.every((x, i) => same(x, b[i]));
  if (isObj(a) && isObj(b)) {
    const ka = Object.keys(a).filter(k => a[k] !== undefined), kb = Object.keys(b).filter(k => b[k] !== undefined);
    return ka.length === kb.length && ka.every(k => same(a[k], b[k]));
  }
  return false;
};
const clone = v => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)));
const ID_KEYS = ["item_id", "member_id", "id"];
const idKeyOf = arr => Array.isArray(arr) && arr.length && arr.every(isObj) ? ID_KEYS.find(k => arr.every(x => x[k] !== undefined)) : null;

/* 서버로 보낼 몫: LOCAL 키를 뺀 사본. 아직 불러오는 중(status: loading)인 칸은 '불러오는 중'이라고 그대로 보낸다(다른 기기가 같은 AI 호출을 또 하지 않게). */
function shareState(o) {
  if (Array.isArray(o)) return o.map(shareState);
  if (!isObj(o)) return o;
  const out = {};
  for (const [k, v] of Object.entries(o)) if (!ROOM.LOCAL.has(k)) out[k] = shareState(v);
  return out;
}

/* 3-way 합치기. 반환값이 새 값(mine과 theirs를 합친 것). base는 마지막으로 받은 값. */
function mergeState(base, mine, theirs) {
  if (same(mine, base)) return clone(theirs);   // 나는 안 고쳤다 → 서버 것
  if (same(theirs, base)) return clone(mine);   // 서버는 안 고쳤다 → 내 것
  if (isObj(mine) && isObj(theirs)) {
    const b = isObj(base) ? base : {};
    const out = {};
    for (const k of new Set([...Object.keys(mine), ...Object.keys(theirs)])) {
      const inM = k in mine, inT = k in theirs;
      if (inM && inT) out[k] = mergeState(b[k], mine[k], theirs[k]);
      else if (inM) { if (!(k in b) || !same(mine[k], b[k])) out[k] = clone(mine[k]); }      // 내가 새로 만들었거나 고쳤다(서버가 지웠어도 내 고침은 남김)
      else if (!(k in b) || !same(theirs[k], b[k])) out[k] = clone(theirs[k]);              // 서버가 새로 만들었거나 고쳤다(내가 지운 건 서버가 안 고쳤으면 지운 채로)
    }
    return out;
  }
  const kk = idKeyOf(mine);
  if (kk && idKeyOf(theirs) === kk) { // 번호 있는 목록(금융 항목 등)은 번호끼리 합친다. 순서는 서버 → 내가 새로 넣은 것
    const bm = new Map((Array.isArray(base) ? base : []).map(x => [x[kk], x]));
    const tm = new Map(theirs.map(x => [x[kk], x])), mm = new Map(mine.map(x => [x[kk], x]));
    const out = [];
    for (const t of theirs) out.push(mm.has(t[kk]) ? mergeState(bm.get(t[kk]), mm.get(t[kk]), t) : (bm.has(t[kk]) && same(bm.get(t[kk]), t) ? null : clone(t)));
    for (const m of mine) if (!tm.has(m[kk]) && !bm.has(m[kk])) out.push(clone(m));
    return out.filter(x => x !== null);
  }
  return clone(mine); // 그 밖에는 내 것
}

/* 합친 값을 지금 상태 객체에 그 자리에서 반영한다(LOCAL 키는 건드리지 않는다. 화면이 들고 있는 참조가 끊기지 않게). */
function assignState(target, merged) {
  for (const k of Object.keys(target)) if (!ROOM.LOCAL.has(k) && !(k in merged)) delete target[k];
  for (const [k, v] of Object.entries(merged)) {
    if (isObj(v) && isObj(target[k])) assignState(target[k], v);
    else if (!same(target[k], v)) target[k] = clone(v);
  }
}

const typing = () => { const a = document.activeElement; return !!a && (a.tagName === "TEXTAREA" || (a.tagName === "INPUT" && a.type !== "checkbox" && a.type !== "radio" && a.type !== "button")); };

/* ---- 서버와 맞추기 ---- */
/* 서버로 안 보내는 화면 설정(LOCAL)은 서버 상태에 없으니, 화면이 늘 있다고 보는 칸은 빈 값으로 채워 둔다(없으면 화면이 멈춘다). */
ROOM.ensureLocal = function (s) {
  s.ovIn = s.ovIn || {}; s.fo = s.fo || {}; s.rag = s.rag || {};
  for (const k of ["pgView", "cpView", "backPending"]) if (s[k] === undefined) s[k] = null;
  if (s.discDraft === undefined) s.discDraft = "";
};

ROOM.apply = function (state, version) { // 서버 상태를 내 상태와 합쳐 반영
  const s = R[room];
  const mine = shareState(s);
  const merged = this.base === null ? state : mergeState(this.base, mine, state);
  assignState(s, merged);
  s.viewer = this.memberId;
  this.ensureLocal(s);
  this.base = clone(state);
  this.version = version;
  return !same(merged, mine);
};

ROOM.afterSave = function () { // app.js save()가 부른다: 화면이 바뀔 때마다 조금 뒤에 서버로 보낸다
  if (!this.active || this.base === null) return;
  clearTimeout(this.push);
  this.push = setTimeout(() => this.flush(), 500);
};

ROOM.flush = async function () {
  if (this.busy || !R[room]) return;
  this.busy = true;
  try {
    for (let i = 0; i < 4; i++) {
      const mine = shareState(R[room]);
      if (same(mine, this.base)) break;
      const res = await api("/api/room/save", { room_id: this.id, token: this.token, base_version: this.version, state: mine });
      if (!res.conflict) { this.base = clone(mine); this.version = res.version; break; }
      if (this.apply(res.state, res.version)) render(); // 서버가 더 새로웠다 → 합치고 다시 보낸다
    }
    this.fails = 0;
  } catch (e) {
    this.fails++;
    if (this.fails === 3) toast("가족방과 연결이 불안정해요. 잠시 뒤 자동으로 다시 시도해요");
  }
  this.busy = false;
};

/* AI를 부르던 기기가 닫혀서 '불러오는 중'으로 남은 칸은 3분이 지나면 실패로 바꿔 다시 시도할 수 있게 한다(다른 가족 화면이 영원히 멈추지 않게). */
ROOM.STALE_MS = 180000;
ROOM.expireStale = function () {
  let n = 0;
  (function walk(o) {
    if (!o || typeof o !== "object") return;
    if (!Array.isArray(o) && o.status === "loading" && o.t0 && Date.now() - o.t0 > ROOM.STALE_MS) {
      o.status = "error"; o.error = { code: "stale", message: "AI가 끝내지 못했어요. 다시 시도해 주세요" }; n++; return;
    }
    for (const v of Object.values(o)) walk(v);
  })(R[room]);
  return n > 0;
};

ROOM.poll = async function () {
  if (!this.active || this.busy) return;
  if (R[room] && this.expireStale()) { render(); this.afterSave(); }
  try {
    const g = await api("/api/room/get", { room_id: this.id, token: this.token, since: this.version });
    this.fails = 0;
    if (g.state && g.version !== this.version) {
      if (typing()) { this.pendingApply = g; return; } // 입력 중이면 끝난 뒤에 반영(입력이 사라지지 않게)
      if (this.apply(g.state, g.version)) render();
    }
    if (this.pendingApply && !typing()) { const p = this.pendingApply; this.pendingApply = null; if (p.version !== this.version && this.apply(p.state, p.version)) render(); }
  } catch (e) { this.fails++; }
};

ROOM.boot = async function () { // 링크로 들어왔을 때(app.js 맨 끝에서 부른다)
  try {
    const g = await api("/api/room/get", { room_id: this.id, token: this.token });
    this.memberId = g.member_id; this.isHost = g.is_host;
    R = { custom: g.state }; room = "custom";
    R.custom.viewer = g.member_id; this.ensureLocal(R.custom);
    try { R.custom.step = +localStorage.getItem("oneheart.step." + this.id) || 0; } catch (e) { R.custom.step = 0; }
    try { R.custom.maxStep = +localStorage.getItem("oneheart.max." + this.id) || 0; } catch (e) { R.custom.maxStep = 0; }
    this.base = clone(shareState(g.state)); this.version = g.version;
    document.body.classList.add("remote");
    await startApp("custom");
    this.timer = setInterval(() => { this.poll(); if (this.isHost && ++this.tick % 4 === 0) this.refreshTokens(); }, 3000);
    this.refreshTokens();
  } catch (e) {
    $("#landing").hidden = true; $("#app").hidden = false;
    $("#main").innerHTML = `<div class="failbox"><b>가족방에 들어가지 못했어요</b>${esc(e.message || "링크를 다시 확인해 주세요")}<br>링크를 보내 준 가족에게 새 링크를 부탁해 보세요.</div>`;
  }
};

/* ---- 방장: 가족방 만들기 → 구성원 링크 ---- */
ROOM.tokens = null; ROOM.seen = [];
ROOM.linkFor = (id, token) => `${location.origin}${location.pathname}?r=${encodeURIComponent(id)}&k=${encodeURIComponent(token)}`;

ROOM.create = async function (s) { // '가족방 만들기'를 마친 직후: 서버에 방을 만들고 방장 링크로 옮겨 간다. 성공하면 true(페이지가 바뀐다)
  const host = s.fam.room.host_member_id;
  const ids = [host, ...s.fam.members.map(m => m.member_id).filter(x => x !== host)]; // 서버는 첫 번째를 방장으로 본다
  const res = await api("/api/room/create", { state: shareState(s), member_ids: ids });
  // 화면을 새로 불러오지 않고 방장 링크로 바꿔 끼운다(소개 화면이 잠깐 비치지 않게)
  ROOM.id = res.room_id; ROOM.token = res.tokens[host];
  history.replaceState(null, "", ROOM.linkFor(ROOM.id, ROOM.token));
  dropLocalCustom();
  await ROOM.boot();
  return true;
};

ROOM.refreshTokens = async function () { // 방장만: 구성원 링크와 누가 들어왔는지
  if (!this.active || !this.isHost) return;
  try {
    const r = await api("/api/room/tokens", { room_id: this.id, token: this.token });
    const changed = !same([r.tokens, r.seen], [this.tokens, this.seen]);
    this.tokens = r.tokens; this.seen = r.seen;
    if (changed && step === 0 && !typing()) render();
  } catch (e) { }
};

function roomCard() { // 1단계(가족방 만들기를 마친 화면)에 들어가는 안내: 방장은 구성원 링크, 가족은 '○○님으로 들어왔어요'(시안 19)
  if (!ROOM.active) return "";
  const f = F(), me = mem(ROOM.memberId);
  if (!ROOM.isHost) return `<div class="rm-me"><b>${esc(me.name)}님</b>으로 들어왔어요. 이 화면에서는 ${esc(me.name)}님이 입력하고 답해요. 가족이 입력한 내용은 몇 초마다 자동으로 반영돼요.</div>`;
  if (!ROOM.tokens) return `<div class="card"><div class="ct">가족에게 링크를 보내 주세요</div><p class="cs">링크를 불러오고 있어요</p></div>`;
  const joined = f.members.filter(m => ROOM.seen.includes(m.member_id)).length;
  const rows = f.members.map(m => {
    const mine = m.member_id === ROOM.memberId, on = ROOM.seen.includes(m.member_id);
    return `<div class="rm-link">${av(m.member_id)}<div class="rm-who"><b>${esc(m.name)} <span>· ${esc(m.role)}${mine ? " · 방장(나)" : ""}</span></b>${mine ? "<span>지금 보고 있는 화면이에요</span>" : ""}</div>
     <span class="rm-st ${on ? "on" : ""}">${on ? "들어왔어요" : "아직이에요"}</span>
     ${mine ? "<span></span>" : `<button class="btn sm" data-act="copy-link" data-mid="${esc(m.member_id)}">링크 복사</button>`}
     ${mine ? "" : `<div class="rm-url">${esc(ROOM.linkFor(ROOM.id, ROOM.tokens[m.member_id]))}</div>`}</div>`;
  }).join("");
  return `<div class="card"><div class="ct">가족에게 링크를 보내 주세요 <span class="cs">${f.members.length}명 중 ${joined}명 들어옴</span></div>
   <p class="cs" style="margin:0 0 6px">가족마다 한 개씩 보내 주세요. 링크를 열면 그 가족의 이름으로 바로 들어와요. 로그인은 필요 없어요.</p>${rows}
   <p class="rm-note">링크는 그 사람 전용이에요. 다른 사람에게 전달하면 그 사람 이름으로 들어가니, 가족 각자에게 따로 보내 주세요.</p></div>`;
}

if (ROOM.active) ROOM.boot(); // 링크로 들어왔으면 가족방을 불러와 시작한다
