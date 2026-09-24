"use strict";

const MANDATE_KEY = "viseca.demo.mandateId";
const screen = document.querySelector("#screen");
const overlayRoot = document.querySelector("#overlay-root");
const toastRoot = document.querySelector("#toast-root");
const examples = [
  "Find me a 27-inch USB-C monitor below CHF 400",
  "Book a train from Zürich to Milan tomorrow",
  "Find a birthday gift around CHF 80",
  "Get noise-cancelling headphones below CHF 300",
  "Buy EU 43 running shoes with at least 14-day returns",
];
const state = {
  user: null,
  route: "shop",
  walletTab: "needs",
  activityFilter: "all",
  draft: null,
  answers: {},
  mandate: null,
  pending: [],
  history: [],
  details: new Map(),
  detail: null,
  prompt: "",
  filters: { category: "monitor", budget: 400, brand: "Any", color: "Any", size: "", usbC: true },
  serial: 0,
  timer: null,
  exampleTimer: null,
  overlayTrigger: null,
  pendingTabFocus: null,
};

function text(value, label) {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${label} is missing.`);
  return value;
}

function esc(value) {
  if (value === null || value === undefined) throw new Error("A required display value is missing.");
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function money(value, currency = "CHF") {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error("The purchase amount is invalid.");
  return new Intl.NumberFormat("en-CH", { style: "currency", currency: text(currency, "currency"), maximumFractionDigits: 2 }).format(value);
}

function toast(message, tone = "error") {
  const item = document.createElement("div");
  item.className = `toast ${tone}`;
  item.setAttribute("role", "status");
  item.textContent = message;
  toastRoot.replaceChildren(item);
  window.setTimeout(() => { if (item.isConnected) item.remove(); }, 6000);
}

function setScreen(markup) {
  screen.innerHTML = markup;
  screen.setAttribute("aria-busy", "false");
}

function loading(message) {
  setScreen(`<div class="loading-state"><span class="spinner" aria-hidden="true"></span>${esc(message)}</div>`);
  screen.setAttribute("aria-busy", "true");
}

function errorPanel(title, error) {
  if (!(error instanceof Error)) throw new Error("A non-Error failure reached the Wallet.");
  return `<section class="error-panel" role="alert"><span aria-hidden="true">!</span><div><h2>${esc(title)}</h2><p>${esc(error.message)}</p><button type="button" data-action="reload">Try again</button></div></section>`;
}

function linkedDraftId() {
  const query = new URLSearchParams(window.location.search);
  const draft = query.get("draft");
  const draftId = query.get("draft_id");
  if (draft === "" || draftId === "") throw new Error("The spending-plan link has an empty draft ID.");
  if (draft && draftId && draft !== draftId) throw new Error("The draft and draft_id links refer to different spending plans.");
  return draft || draftId;
}

function clearDraftLink() {
  const url = new URL(window.location.href);
  url.searchParams.delete("draft");
  url.searchParams.delete("draft_id");
  window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  state.draft = null;
  state.answers = {};
  document.querySelector("#wallet-indicator").hidden = true;
}

function mandateId() { return window.sessionStorage.getItem(MANDATE_KEY); }

function validateDraft(draft) {
  if (!draft || typeof draft !== "object" || !Array.isArray(draft.rules) || !Array.isArray(draft.open_questions) || !Array.isArray(draft.examples)) throw new Error("The saved spending plan is incomplete.");
  text(draft.draft_id, "Draft ID");
  text(draft.hash, "Draft hash");
  text(draft.instruction, "Original request");
  if (!Number.isInteger(draft.version)) throw new Error("The saved spending plan has no valid version.");
  draft.rules.forEach((rule) => { text(rule.field, "Rule field"); text(rule.plain_english, "Rule description"); });
  draft.open_questions.forEach((question) => {
    text(question.question, "Question");
    if (!Array.isArray(question.options) || !Array.isArray(question.confirming_answers)) throw new Error("The saved spending plan has an invalid question.");
  });
  return draft;
}

function validateMandate(payload) {
  if (!payload || !payload.mandate || !payload.draft || !payload.effective_policy || !payload.state) throw new Error("The Wallet returned an incomplete permission.");
  const { mandate, draft, effective_policy, state: usage } = payload;
  text(mandate.mandate_id, "Permission ID");
  if (!["active", "revoked", "superseded", "expired"].includes(mandate.status)) throw new Error("The permission has an unknown status.");
  validateDraft(draft);
  if (!Array.isArray(effective_policy.rules) || !Array.isArray(usage.approvals) || usage.mandate_id !== mandate.mandate_id) throw new Error("The permission and its purchase state do not match.");
  effective_policy.rules.forEach((rule) => { text(rule.field, "Current rule field"); text(rule.plain_english, "Current rule description"); });
  return payload;
}

function validateDecision(payload) {
  if (!payload || !payload.decision || !payload.event || !payload.state_before || !payload.state_after) throw new Error("The transaction record is incomplete.");
  const { decision, event } = payload;
  text(decision.authorization_id, "Authorization ID");
  text(decision.customer_message, "Decision explanation");
  text(decision.decided_at, "Decision time");
  if (!Number.isFinite(new Date(decision.decided_at).getTime())) throw new Error("The decision time is invalid.");
  if (!["approve", "decline", "step_up"].includes(decision.decision) || !Array.isArray(decision.evidence) || !Array.isArray(decision.reason_codes)) throw new Error("The transaction has an unsupported outcome.");
  if (!event.authorization || !event.authorization.merchant || !Array.isArray(event.authorization.items)) throw new Error("The transaction has no purchase details.");
  text(event.authorization.merchant.merchant_name, "Merchant name");
  decision.evidence.forEach((check) => {
    text(check.name, "Check name");
    text(check.source, "Check source");
    if (!["pass", "fail", "uncertain"].includes(check.result) || typeof check.note !== "string") throw new Error("The transaction contains an invalid check.");
  });
  return payload;
}

function normalRoute(route) {
  if (route === "home") { state.walletTab = "active"; return "wallet"; }
  if (route === "approvals") { state.walletTab = "needs"; return "wallet"; }
  if (route === "policy") { state.walletTab = "rules"; return "wallet"; }
  return route;
}

function navigate(route, { keepScroll = false } = {}) {
  route = normalRoute(route);
  if (!["shop", "wallet", "activity", "review"].includes(route)) {
    setScreen(errorPanel("This page is unavailable", new Error(`Unknown page: ${route}`)));
    return;
  }
  state.route = route;
  state.serial += 1;
  window.clearInterval(state.timer);
  window.clearTimeout(state.exampleTimer);
  state.timer = null;
  state.exampleTimer = null;
  closeOverlay();
  if (window.location.hash !== `#${route}`) window.history.replaceState(null, "", `#${route}`);
  document.querySelectorAll(".nav-button").forEach((button) => {
    const selected = button.dataset.route === (route === "review" ? "wallet" : route);
    button.classList.toggle("is-active", selected);
    if (selected) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  if (!keepScroll) window.scrollTo(0, 0);
  void render();
}

async function render() {
  const serial = state.serial;
  if (!state.user) { renderLogin(); return; }
  try {
    if (state.route === "shop") await renderShop(serial);
    else if (state.route === "wallet") await renderWallet(serial);
    else if (state.route === "review") await renderReview(serial);
    else await renderActivity(serial);
  } catch (error) {
    if (serial !== state.serial) return;
    if (error.status === 401) {
      state.user = null;
      state.mandate = null;
      state.pending = [];
      window.sessionStorage.removeItem(MANDATE_KEY);
      renderLogin();
      toast(error.message);
      return;
    }
    setScreen(`<div class="page-title"><h1>${esc(state.route === "review" ? "Review spending permission" : state.route)}</h1></div>${errorPanel("This screen could not be loaded", error)}`);
  }
}

function renderLogin() {
  setScreen(`<section class="login-view"><span class="section-kicker">LOCAL DEMO ACCOUNT</span><h1>Welcome to your Wallet.</h1><p>Sign in to review spending permissions sent by your shopping agent. This demo uses a local username, not a Viseca account.</p><label for="username">Username</label><input id="username" maxlength="80" autocomplete="username" placeholder="Your name" /><button class="primary-button" type="button" data-action="login">Continue</button></section>`);
}

async function initialize() {
  try {
    const session = await walletApi.session();
    state.user = text(session.username, "Session username");
    const hash = window.location.hash.slice(1);
    navigate(hash || (linkedDraftId() ? "review" : "shop"));
  } catch (error) {
    if (error.status === 401) { renderLogin(); return; }
    setScreen(errorPanel("Your session could not be checked", error));
  }
}

function startExamples() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  let index = 0, position = 0, erasing = false;
  function tick() {
    const composer = document.querySelector("#shop-prompt");
    const example = document.querySelector("#animated-example");
    if (!composer || !example || document.activeElement === composer || composer.value) return;
    const current = examples[index];
    example.textContent = current.slice(0, position);
    if (!erasing && position < current.length) { position += 1; state.exampleTimer = window.setTimeout(tick, 44); }
    else if (!erasing) { erasing = true; state.exampleTimer = window.setTimeout(tick, 1900); }
    else if (position > 0) { position -= 1; state.exampleTimer = window.setTimeout(tick, 22); }
    else { erasing = false; index = (index + 1) % examples.length; state.exampleTimer = window.setTimeout(tick, 350); }
  }
  tick();
}

function filterRequest() {
  const { category, budget, brand, color, size, usbC } = state.filters;
  if (!Number.isInteger(budget) || budget < 100 || budget > 1000) throw new Error("Choose a budget from CHF 100 to CHF 1,000.");
  const base = category === "monitor" ? `Find me a 27-inch monitor below CHF ${budget}` : `Find me running shoes below CHF ${budget}`;
  const details = category === "monitor"
    ? [usbC ? "with USB-C" : null, brand !== "Any" ? `from ${brand}` : null]
    : [brand !== "Any" ? `from ${brand}` : null, color !== "Any" ? `in ${color.toLowerCase()}` : null, size ? `in EU size ${size}` : null];
  return `${base}${details.filter(Boolean).length ? `, ${details.filter(Boolean).join(", ")}` : ""}.`;
}

function openFilters() {
  const f = state.filters;
  openOverlay(`<div class="filter-sheet"><span class="section-kicker">SHOPPING REQUEST</span><h2>Refine your search</h2><p class="calm-copy">These controls create a request for your shopping agent. The Wallet will separately show any enforceable spending rules before you authorize them.</p>
    <div class="filter-category" role="group" aria-label="Product example"><button type="button" data-action="filter-category" data-category="monitor" class="${f.category === "monitor" ? "selected" : ""}" aria-pressed="${f.category === "monitor"}">Monitor</button><button type="button" data-action="filter-category" data-category="shoes" class="${f.category === "shoes" ? "selected" : ""}" aria-pressed="${f.category === "shoes"}">Running shoes</button></div>
    <label class="filter-field" for="filter-budget"><span>Spend below</span><strong id="budget-value">CHF ${f.budget}</strong></label><input type="range" class="budget-slider" id="filter-budget" min="100" max="1000" step="10" value="${f.budget}" /><div class="budget-ends"><span>CHF 100</span><span>CHF 1,000</span></div>
    <label class="filter-field" for="filter-brand">Brand <select id="filter-brand"><option>Any</option>${(f.category === "monitor" ? ["Dell", "LG", "BenQ"] : ["On", "Nike", "Adidas"]).map((brand) => `<option ${f.brand === brand ? "selected" : ""}>${brand}</option>`).join("")}</select></label>
    ${f.category === "monitor" ? `<div class="filter-field"><span>Screen size</span><strong>27 inch</strong></div><label class="filter-field" for="filter-usbc"><span>USB-C connection</span><input type="checkbox" id="filter-usbc" ${f.usbC ? "checked" : ""} /></label>` : `<label class="filter-field" for="filter-color">Colour <select id="filter-color">${["Any", "Black", "White", "Blue", "Green"].map((color) => `<option ${f.color === color ? "selected" : ""}>${color}</option>`).join("")}</select></label><label class="filter-field" for="filter-size">EU size <select id="filter-size"><option value="">Choose size</option>${[41, 42, 43, 44].map((size) => `<option ${f.size === String(size) ? "selected" : ""}>${size}</option>`).join("")}</select></label>`}
    <div class="filter-preview"><span class="section-kicker">REQUEST TO COPY</span><p id="filter-preview-text">${esc(filterRequest())}</p></div><p class="calm-copy">Using this request replaces the current composer text. You can edit it before copying.</p><button type="button" class="primary-button filter-apply" data-action="apply-filters">Use this request</button></div>`, "Refine your search");
}

function purchaseCap(rules) {
  const caps = rules.filter((rule) => rule.field === "authorization.billing_amount_chf" && rule.scope === "purchase" && ["<", "<="].includes(rule.operator) && typeof rule.value === "number");
  if (!caps.length) return null;
  const amount = Math.min(...caps.map((rule) => rule.value));
  return { amount, strict: caps.some((rule) => rule.value === amount && rule.operator === "<") };
}

function productName(draft) {
  const product = draft.rules.find((rule) => rule.field === "facts.product_type" && rule.operator === "=" && typeof rule.value === "string");
  return product ? product.value : draft.instruction;
}

async function renderShop(serial) {
  loading("Preparing Shop…");
  let plan = null;
  if (linkedDraftId()) plan = validateDraft(await walletApi.draft(linkedDraftId()));
  if (serial !== state.serial) return;
  const cap = plan && purchaseCap(plan.rules);
  setScreen(`<section class="shop-view"><div class="shop-intro"><h1>What can I<br />get for you?</h1><div class="orbit" aria-hidden="true"><span class="orbit-ring one"></span><span class="orbit-ring two"></span><span class="orbit-core">✓</span><span class="orbit-dot"></span></div></div>
    <div class="composer"><label for="shop-prompt" class="sr-only">Your shopping request</label><textarea id="shop-prompt" rows="2" placeholder="Ask Viseca to buy something…">${esc(state.prompt)}</textarea><div class="prompt-example" ${state.prompt.trim() ? "hidden" : ""}><span>FOR EXAMPLE</span><button type="button" data-action="use-example" id="animated-example">${esc(examples[0])}</button></div><button class="send-button" type="button" data-action="copy-prompt" aria-label="Copy request for your shopping agent" ${state.prompt.trim() ? "" : "disabled"}>Copy</button></div>
    <button type="button" class="filter-trigger" data-action="open-filters">Refine request with product filters <span aria-hidden="true">⌄</span></button>
    <p class="agent-state">Shopping agent <span>· connect an external agent</span></p><p class="external-agent">No shopping model is connected inside this demo. Copy your request to an MCP-compatible agent. The agent can send you a Wallet review link.</p>
    ${plan ? `<section class="shop-plan"><span class="section-kicker">PLAN SAVED BY YOUR AGENT</span><h2>${esc(productName(plan))}</h2><p>${cap ? `${cap.strict ? "Below" : "Up to"} ${esc(money(cap.amount))}` : "Review the saved limits"}</p><button type="button" class="text-button" data-route="review">Review in Wallet <span aria-hidden="true">→</span></button></section>` : ""}
  </section>`);
  startExamples();
}

function walletTabs() {
  return `<div class="wallet-tabs" role="tablist" aria-label="Wallet sections">${[
    ["needs", "Needs you"], ["active", "Active"], ["rules", "Rules"],
  ].map(([id, label]) => `<button type="button" role="tab" aria-selected="${state.walletTab === id}" tabindex="${state.walletTab === id ? 0 : -1}" class="${state.walletTab === id ? "selected" : ""}" data-action="wallet-tab" data-tab="${id}">${label}</button>`).join("")}</div>`;
}

async function renderWallet(serial) {
  loading("Loading Wallet…");
  let markup;
  if (state.walletTab === "needs") markup = await needsContent(serial);
  else if (state.walletTab === "active") markup = await activeContent(serial);
  else markup = await rulesContent(serial);
  if (serial !== state.serial) return;
  setScreen(`<section class="wallet-view"><div class="page-title"><h1>Wallet</h1></div>${walletTabs()}${markup}</section>`);
  if (state.pendingTabFocus === "wallet") {
    screen.querySelector('.wallet-tabs [aria-selected="true"]').focus();
    state.pendingTabFocus = null;
  }
  if (state.walletTab === "needs" && mandateId()) state.timer = window.setInterval(() => { void refreshPending(); }, 2000);
}

async function needsContent(serial) {
  const id = mandateId();
  if (id) state.mandate = validateMandate(await walletApi.mandate(id));
  const [draft, pending] = await Promise.all([
    linkedDraftId() ? walletApi.draft(linkedDraftId()).then(validateDraft) : Promise.resolve(null),
    id ? walletApi.pending() : Promise.resolve([]),
  ]);
  if (serial !== state.serial) return "";
  if (!Array.isArray(pending)) throw new Error("The Wallet did not return a list of pending purchases.");
  state.pending = pending;
  state.draft = draft;
  document.querySelector("#wallet-indicator").hidden = !(draft || pending.length);
  return `<div class="wallet-section"><h2 id="needs-heading">${draft || pending.length ? `${(draft ? 1 : 0) + pending.length} thing${(draft ? 1 : 0) + pending.length === 1 ? " needs" : "s need"} you` : "You're all caught up"}</h2>
    ${draft ? `<button type="button" class="need-card" data-route="review"><span class="section-kicker">SPENDING REQUEST</span><strong>Review shopping plan</strong><span>${esc(productName(draft))}${purchaseCap(draft.rules) ? ` · ${esc(money(purchaseCap(draft.rules).amount))}` : ""}</span><b aria-hidden="true">›</b></button>` : ""}
    <div id="pending-list">${pending.map(pendingCard).join("")}</div>
    ${draft || pending.length ? "" : `<p class="calm-copy">Spending requests and purchases that need a decision will appear here.</p>`}</div>`;
}

function pendingCard(item) {
  text(item.authorization_id, "Pending purchase ID");
  text(item.expires_at, "Pending purchase deadline");
  if (!item.event?.authorization?.merchant || !item.decision || !Array.isArray(item.decision.evidence)) throw new Error("A pending purchase is incomplete.");
  const auth = item.event.authorization;
  const merchant = text(auth.merchant.merchant_name, "Pending merchant");
  const remaining = new Date(item.expires_at).getTime() - Date.now();
  if (!Number.isFinite(remaining)) throw new Error("A pending purchase has an invalid deadline.");
  const issue = item.decision.evidence.find((check) => check.result === "uncertain" || check.result === "fail");
  return `<button type="button" class="need-card uncertain-card" data-action="open-pending" data-id="${esc(item.authorization_id)}"><span class="section-kicker">PURCHASE REVIEW · ${remaining > 0 ? `${Math.floor(remaining / 60000)}m ${String(Math.floor(remaining / 1000) % 60).padStart(2, "0")}s left` : "Deadline reached"}</span><strong>One detail needs a decision</strong><span>${esc(merchant)} · ${esc(money(auth.billing_amount_chf, auth.currency))}</span><small>${esc(issue?.note || item.decision.customer_message)}</small><b aria-hidden="true">›</b></button>`;
}

async function refreshPending() {
  if (state.route !== "wallet" || state.walletTab !== "needs" || !mandateId()) return;
  const container = document.querySelector("#pending-list");
  if (!container) return;
  try {
    const pending = await walletApi.pending();
    if (!Array.isArray(pending)) throw new Error("Pending purchases must be a list.");
    if (!container.isConnected) return;
    state.pending = pending;
    container.innerHTML = pending.map(pendingCard).join("");
    const openAnswer = overlayRoot.querySelector('[data-action="resolve"]');
    if (openAnswer) {
      const current = pending.find((item) => item.authorization_id === openAnswer.dataset.id);
      if (!current || new Date(current.expires_at).getTime() <= Date.now()) {
        overlayRoot.querySelectorAll('[data-action="resolve"]').forEach((button) => { button.disabled = true; });
        const deadline = overlayRoot.querySelector("#pending-deadline");
        if (deadline) deadline.textContent = "This decision window has closed. Refresh Wallet for the final outcome.";
      }
    }
    const count = pending.length + (state.draft ? 1 : 0);
    document.querySelector("#needs-heading").textContent = count ? `${count} thing${count === 1 ? " needs" : "s need"} you` : "You're all caught up";
    document.querySelector("#wallet-indicator").hidden = !count;
  } catch (error) {
    if (container.isConnected) container.innerHTML = errorPanel("Pending purchases could not be refreshed", error);
  }
}

function ruleGroup(rule) {
  if (rule.field.startsWith("authorization.billing_amount") || rule.field === "state.approvals_count") return "Spending";
  if (rule.field.startsWith("facts.") || rule.field.startsWith("items.")) return "Products and extras";
  if (rule.field.startsWith("authorization.merchant.") || rule.field.startsWith("history.merchant")) return "Merchants";
  return "Other checks";
}

function ruleGroups(rules) {
  const groups = new Map();
  rules.forEach((rule) => {
    const name = ruleGroup(rule);
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(rule);
  });
  return ["Spending", "Products and extras", "Merchants", "Other checks"].filter((name) => groups.has(name)).map((name) => `<section class="rule-group"><h3>${esc(name)}</h3>${groups.get(name).map((rule) => `<div class="rule-item"><span class="rule-check" aria-hidden="true">✓</span><span>${esc(rule.plain_english)}</span></div>`).join("")}</section>`).join("");
}

async function activeContent(serial) {
  const id = mandateId();
  if (!id) return `<div class="wallet-section"><h2>No active spending permission</h2><p class="calm-copy">An external shopping agent can send you a spending plan. Your Wallet will ask you to approve it.</p><button type="button" class="outline-button" data-route="shop">Go to Shop</button></div>`;
  const payload = validateMandate(await walletApi.mandate(id));
  if (serial !== state.serial) return "";
  state.mandate = payload;
  const { mandate, draft, effective_policy, state: usage } = payload;
  const cap = purchaseCap(effective_policy.rules);
  return `<div class="wallet-section"><h2>Spending permission</h2><section class="permission-card"><span class="section-kicker">${esc(mandate.status.toUpperCase())}</span><h3>${esc(productName(draft))}</h3><strong>${cap ? esc(money(cap.amount)) : "No per-purchase amount limit"}</strong><p>${cap ? cap.strict ? "Each purchase must stay below this amount." : "Maximum per purchase." : "Review the confirmed rules before your agent shops."}</p><div class="permission-stats"><span>Approved purchases</span><b>${usage.approvals.length}</b><span>Approved spend</span><b>${esc(money(usage.approvals.reduce((sum, entry) => sum + entry.amount_chf, 0)))}</b></div></section><p class="calm-copy">${mandate.status === "active" ? "Only the rules you confirmed grant purchasing authority." : `This permission is ${esc(mandate.status)} and cannot authorize new purchases.`}</p><button type="button" class="text-button" data-action="wallet-tab" data-tab="rules">View current rules <span aria-hidden="true">→</span></button></div>`;
}

async function rulesContent(serial) {
  const id = mandateId();
  if (!id) return `<div class="wallet-section"><h2>Rules for your permissions</h2><p class="calm-copy">You have no confirmed permission to inspect. Account-wide defaults are not available in this demo.</p></div>`;
  const payload = validateMandate(await walletApi.mandate(id));
  if (serial !== state.serial) return "";
  state.mandate = payload;
  const { mandate, effective_policy } = payload;
  return `<div class="wallet-section"><h2>Rules for this permission</h2><p class="calm-copy">These limits belong to the spending permission you confirmed. Account-wide defaults are not available in this demo.</p>${ruleGroups(effective_policy.rules)}<section class="rule-group"><h3>Missing information</h3><p>${esc(effective_policy.uncertainty_policy === "ask" ? "Ask me before buying" : effective_policy.uncertainty_policy === "decline" ? "Decline the purchase" : "Use the confirmed uncertainty setting")}</p></section><section class="rule-group"><h3>Security</h3><p>Purchase decisions and unfamiliar evidence are checked by the Wallet backend. Your agent cannot change these confirmed rules.</p></section><div class="rule-actions"><button type="button" class="outline-button" data-action="open-tighten" ${mandate.status !== "active" || effective_policy.uncertainty_policy === "decline" ? "disabled" : ""}>Decline uncertain purchases</button><button type="button" class="danger-link" data-action="open-revoke" ${mandate.status !== "active" ? "disabled" : ""}>Revoke this permission</button></div></div>`;
}

async function renderReview(serial) {
  loading("Loading saved spending plan…");
  const id = text(linkedDraftId(), "Draft link");
  const draft = validateDraft(await walletApi.draft(id));
  if (serial !== state.serial) return;
  if (state.draft?.draft_id !== id || state.draft.version !== draft.version || state.draft.hash !== draft.hash) state.answers = {};
  state.draft = draft;
  const cap = purchaseCap(draft.rules);
  const questions = draft.open_questions;
  const ready = questions.every((question) => question.confirming_answers.includes(state.answers[question.question] ?? question.answer));
  const needsRevision = questions.some((question) => {
    const answer = state.answers[question.question] ?? question.answer;
    return answer && !question.confirming_answers.includes(answer);
  });
  setScreen(`<section class="review-view"><button class="back-button" type="button" data-route="wallet">‹ Wallet</button><div class="page-title"><h1>Review spending permission</h1></div><p class="review-subtitle">Your Wallet loaded the plan saved by your shopping agent. Only you can authorize it.</p><section class="review-summary"><span class="section-kicker">YOUR AGENT MAY BUY</span><h2>${esc(productName(draft))}</h2><strong>${cap ? esc(money(cap.amount)) : "No per-purchase cap"}</strong><small>${cap ? cap.strict ? "SPEND MUST STAY BELOW THIS AMOUNT" : "MAXIMUM PER PURCHASE" : "REVIEW ALL RULES BEFORE AUTHORIZING"}</small></section><section class="review-rules"><h2>The limits you'll authorize</h2>${ruleGroups(draft.rules)}<details><summary>Original request</summary><p>${esc(draft.instruction)}</p></details><details><summary>Examples from the agent</summary>${draft.examples.map((example) => `<p><strong>${esc(example.expected)}</strong> · ${esc(example.description)}. ${esc(example.why)}</p>`).join("")}</details></section>
    ${questions.length ? `<section class="questions"><h2>Confirm these details</h2>${questions.map((question) => { const selected = state.answers[question.question] ?? question.answer; return `<div class="question"><strong>${esc(question.question)}</strong><div class="choices">${question.options.map((option) => `<button type="button" class="${selected === option ? "selected" : ""}" aria-pressed="${selected === option}" data-action="answer-question" data-question="${esc(question.question)}" data-answer="${esc(option)}">${esc(option)}</button>`).join("")}</div></div>`; }).join("")}${needsRevision ? `<p class="uncertainty-note">Your selection requires a revised plan from the shopping agent before authorization.</p>` : ""}</section>` : ""}<div class="review-spacer"></div><div class="review-actions"><button type="button" class="outline-button" data-action="open-reject">Reject</button><button type="button" class="primary-button" data-action="confirm" ${ready ? "" : "disabled"}>Authorize agent</button></div></section>`);
}

function activityTabs() {
  return `<div class="activity-tabs" role="tablist" aria-label="Filter decisions">${[["all", "All"], ["purchases", "Purchases"], ["blocked", "Blocked"]].map(([id, label]) => `<button type="button" role="tab" tabindex="${state.activityFilter === id ? 0 : -1}" aria-selected="${state.activityFilter === id}" class="${state.activityFilter === id ? "selected" : ""}" data-action="activity-filter" data-filter="${id}">${label}</button>`).join("")}</div>`;
}

function activityRows() {
  const filtered = state.history.filter(({ decision }) => state.activityFilter === "all" || (state.activityFilter === "purchases" ? decision.decision === "approve" : decision.decision === "decline"));
  if (!filtered.length) return `<section class="wallet-empty"><h2>No ${state.activityFilter === "all" ? "decisions" : state.activityFilter} yet</h2><p>Decisions for this permission will appear here after the backend records them.</p></section>`;
  let lastDay = "";
  return filtered.map(({ decision }) => {
    const payload = state.details.get(decision.authorization_id);
    if (!payload) throw new Error(`Transaction ${decision.authorization_id} has no details.`);
    const auth = payload.event.authorization;
    const day = new Date(decision.decided_at).toLocaleDateString("en-GB", { day: "numeric", month: "long", timeZone: "UTC" }) + " · UTC";
    const heading = day === lastDay ? "" : `<h2 class="date-group">${esc(day)}</h2>`;
    lastDay = day;
    const merchant = text(auth.merchant.merchant_name, "Merchant");
    const item = auth.items.map((entry) => text(entry.item_name, "Item")).join(" + ");
    const label = decision.decision === "approve" ? decision.reason_codes.includes("customer_confirmation") ? "Approved after review" : "Approved" : decision.decision === "decline" ? "Blocked" : "Needs a decision";
    const kind = decision.decision === "approve" ? "approved" : decision.decision === "decline" ? "blocked" : "uncertain";
    return `${heading}<button type="button" class="activity-card" data-action="open-detail" data-id="${esc(decision.authorization_id)}"><span class="activity-card-top"><span class="outcome-icon ${kind}" aria-hidden="true">${decision.decision === "approve" ? "✓" : decision.decision === "decline" ? "×" : "?"}</span><strong>${esc(merchant)}</strong><b>${esc(money(auth.billing_amount_chf, auth.currency))}</b></span><span class="activity-product">${esc(item)}</span><span class="activity-card-bottom"><span class="${kind}">${esc(label)}</span><time datetime="${esc(decision.decided_at)}">${esc(new Date(decision.decided_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" }))}</time></span></button>`;
  }).join("");
}

async function renderActivity(serial) {
  const id = mandateId();
  if (!id) { setScreen(`<section class="activity-view"><div class="page-title"><h1>Activity</h1></div><p class="calm-copy">No confirmed permission is selected. Recorded purchase decisions will appear here.</p></section>`); return; }
  loading("Loading recorded decisions…");
  await walletApi.mandate(id);
  const history = await walletApi.history(id);
  if (!Array.isArray(history)) throw new Error("The Wallet did not return a decision history.");
  history.forEach((entry) => {
    if (!entry?.decision || !entry.state_after) throw new Error("A history entry is incomplete.");
    text(entry.decision.authorization_id, "History authorization ID");
  });
  const details = await Promise.all(history.map(({ decision }) => walletApi.decision(decision.authorization_id).then(validateDecision)));
  if (serial !== state.serial) return;
  state.history = [...history].reverse();
  state.details = new Map(details.map((detail) => [detail.decision.authorization_id, detail]));
  setScreen(`<section class="activity-view"><div class="page-title"><h1>Activity</h1></div>${activityTabs()}<div id="activity-list">${activityRows()}</div><p class="activity-disclaimer">Recorded purchase decisions for the selected permission. Permission changes are not in this history.</p></section>`);
}

function openOverlay(body, title) {
  if (!overlayRoot.childElementCount) state.overlayTrigger = document.activeElement;
  overlayRoot.innerHTML = `<div class="overlay-backdrop" data-action="close-overlay"><section class="overlay" role="dialog" aria-modal="true" aria-label="${esc(title)}" tabindex="-1"><button type="button" class="overlay-close" data-action="close-overlay" aria-label="Close">×</button>${body}</section></div>`;
  overlayRoot.querySelector(".overlay").focus();
}

function closeOverlay() {
  if (!overlayRoot.childElementCount) return;
  overlayRoot.replaceChildren();
}

function openPending(id) {
  const item = state.pending.find((entry) => entry.authorization_id === id);
  if (!item) throw new Error("This purchase is no longer waiting for your decision.");
  const auth = item.event.authorization;
  const issue = item.decision.evidence.filter((check) => check.result !== "pass");
  const remaining = new Date(item.expires_at).getTime() - Date.now();
  openOverlay(`<span class="section-kicker amber-text">VISECA NEEDS YOU</span><h2>One detail needs a decision</h2><p class="overlay-intro">${esc(item.decision.customer_message)}</p><div class="purchase-highlight"><span>${esc(auth.merchant.merchant_name)}</span><strong>${esc(money(auth.billing_amount_chf, auth.currency))}</strong><p>${esc(auth.items.map((entry) => text(entry.item_name, "Item")).join(" + "))}</p></div><h3>Why you're seeing this</h3><div class="evidence-list">${issue.map((check) => `<div class="evidence-card ${check.result}"><span>${check.result === "fail" ? "×" : "?"}</span><div><strong>${esc(check.name.replaceAll("_", " "))}</strong><p>${esc(check.note)}</p><small>Source: ${esc(check.source)}</small></div></div>`).join("")}</div><p class="calm-copy">This answer applies only to this purchase. It does not change your confirmed limits.</p><p id="pending-deadline" class="calm-copy">${remaining > 0 ? `Decision window: ${Math.floor(remaining / 60000)}m ${String(Math.floor(remaining / 1000) % 60).padStart(2, "0")}s left` : "The decision window has closed."}</p><div class="overlay-actions"><button class="outline-button" type="button" data-action="resolve" data-id="${esc(id)}" data-decision="decline" ${remaining <= 0 ? "disabled" : ""}>Don't buy</button><button class="primary-button" type="button" data-action="resolve" data-id="${esc(id)}" data-decision="approve" ${remaining <= 0 ? "disabled" : ""}>Buy anyway</button></div>${remaining <= 0 ? `<p class="uncertainty-note">The decision window has closed. Refresh Wallet for the final result.</p>` : ""}`, "Purchase review");
}

function openDetail(payload) {
  state.detail = validateDecision(payload);
  const { decision, event } = payload;
  const auth = event.authorization;
  const failed = decision.evidence.filter((check) => check.result === "fail");
  const uncertain = decision.evidence.filter((check) => check.result === "uncertain");
  const outcome = decision.decision === "approve" ? "Approved" : decision.decision === "decline" ? "Blocked" : "Needs a decision";
  openOverlay(`<span class="section-kicker">TRANSACTION</span><h2>${decision.decision === "decline" ? "Why was this blocked?" : "Why was this purchase " + outcome.toLowerCase() + "?"}</h2><div class="purchase-highlight"><span>${esc(auth.merchant.merchant_name)}</span><strong>${esc(money(auth.billing_amount_chf, auth.currency))}</strong><p>${esc(auth.items.map((entry) => text(entry.item_name, "Item")).join(" + "))}</p></div><p class="overlay-intro">${esc(decision.customer_message)}</p>${failed.length || uncertain.length ? `<div class="evidence-list">${[...failed, ...uncertain].slice(0, 4).map((check) => `<div class="evidence-card ${check.result}"><span>${check.result === "fail" ? "×" : "?"}</span><div><strong>${esc(check.name.replaceAll("_", " "))}</strong><p>${esc(check.note)}</p></div></div>`).join("")}</div>` : ""}<button type="button" class="text-button" data-action="inspector" data-tab="summary">View technical details <span aria-hidden="true">→</span></button>`, "Transaction explanation");
}

function inspector(tab) {
  if (!state.detail) throw new Error("The transaction details are not loaded.");
  if (!["summary", "checks", "record"].includes(tab)) throw new Error("Unknown inspector section.");
  const { decision, event, state_before, state_after } = state.detail;
  const status = decision.decision === "approve" ? "Approved" : decision.decision === "decline" ? "Blocked" : "Needs a decision";
  const content = tab === "summary"
    ? `<div class="inspector-outcome ${decision.decision}"><span>${esc(status.toUpperCase())}</span><h3>${esc(decision.customer_message)}</h3></div><h3>How the decision was made</h3><p>${esc(decision.explanation)}</p><p class="check-count">${decision.evidence.filter((check) => check.result === "pass").length} passed · ${decision.evidence.filter((check) => check.result === "fail").length} failed · ${decision.evidence.filter((check) => check.result === "uncertain").length} unknown</p>`
    : tab === "checks"
      ? `<div class="evidence-list">${decision.evidence.map((check) => `<div class="evidence-card ${check.result}"><span>${check.result === "pass" ? "✓" : check.result === "fail" ? "×" : "?"}</span><div><strong>${esc(check.name.replaceAll("_", " "))}</strong><p>${esc(check.note)}</p><small>${check.value === null ? "Value unknown" : `Value: ${esc(check.value)}`} · Source: ${esc(check.source)}</small></div></div>`).join("")}</div>`
      : `<div class="record-grid"><span>Authorization</span><strong>${esc(decision.authorization_id)}</strong><span>Engine</span><strong>${esc(decision.engine_version)}</strong><span>Version</span><strong>${esc(decision.mandate_version)}</strong><span>Time</span><strong>${esc(decision.elapsed_ms)} ms</strong></div><details><summary>Original payment event and merchant text</summary><p class="calm-copy">Merchant-provided item details are untrusted evidence. They cannot grant spending authority.</p><pre>${esc(JSON.stringify(event, null, 2))}</pre></details><details><summary>Decision and state</summary><pre>${esc(JSON.stringify({ decision, state_before, state_after }, null, 2))}</pre></details>`;
  openOverlay(`<span class="section-kicker">ADVANCED DETAILS</span><h2>Decision details</h2><p class="overlay-intro">${esc(event.authorization.merchant.merchant_name)} · ${esc(money(event.authorization.billing_amount_chf, event.authorization.currency))}</p><div class="inspector-tabs" role="tablist" aria-label="Decision sections">${["summary", "checks", "record"].map((name) => `<button type="button" role="tab" aria-selected="${tab === name}" tabindex="${tab === name ? 0 : -1}" data-action="inspector" data-tab="${name}" class="${tab === name ? "selected" : ""}">${name[0].toUpperCase() + name.slice(1)}</button>`).join("")}</div><div class="inspector-body" role="tabpanel" tabindex="0">${content}</div>`, "Decision details");
}

function confirmDialog(title, message, action, label) {
  openOverlay(`<span class="section-kicker">VISECA WALLET</span><h2>${esc(title)}</h2><p class="overlay-intro">${esc(message)}</p><div class="overlay-actions"><button type="button" class="outline-button" data-action="close-overlay">Cancel</button><button type="button" class="primary-button" data-action="${esc(action)}">${esc(label)}</button></div>`, title);
}

async function performConfirm() {
  const draft = state.draft;
  if (!draft) throw new Error("The spending plan is not loaded.");
  const answers = Object.fromEntries(draft.open_questions.map((question) => [question.question, state.answers[question.question] ?? question.answer]));
  if (draft.open_questions.some((question) => !question.confirming_answers.includes(answers[question.question]))) throw new Error("Answer every question with a confirming choice before authorizing.");
  const mandate = await walletApi.confirm(draft.draft_id, draft.version, draft.hash, answers);
  text(mandate?.mandate_id, "Confirmed permission ID");
  window.sessionStorage.setItem(MANDATE_KEY, mandate.mandate_id);
  clearDraftLink();
  state.walletTab = "active";
  setScreen(`<section class="confirmed-state" role="status"><span aria-hidden="true">✓</span><h1>Agent authorized</h1><p>Your spending limits are active. Return to your shopping agent to continue.</p></section>`);
  const serial = state.serial;
  window.setTimeout(() => { if (serial === state.serial && state.route === "review") navigate("wallet"); }, 750);
}

async function performReject() {
  const draft = state.draft;
  if (!draft) throw new Error("The spending plan is not loaded.");
  await walletApi.reject(draft.draft_id, draft.version, draft.hash, "Rejected in the customer Wallet.");
  clearDraftLink();
  closeOverlay();
  state.walletTab = "needs";
  navigate("wallet");
  toast("The spending request was rejected.", "success");
}

async function performResolution(button) {
  const id = text(button.dataset.id, "Pending purchase ID");
  const pending = state.pending.find((item) => item.authorization_id === id);
  if (!pending) throw new Error("This purchase is no longer pending.");
  if (new Date(pending.expires_at).getTime() <= Date.now()) throw new Error("The decision window has closed. Refresh Wallet for the final outcome.");
  const decision = button.dataset.decision;
  if (!["approve", "decline"].includes(decision)) throw new Error("Choose whether to buy or decline.");
  await walletApi.answer(id, decision);
  closeOverlay();
  toast(decision === "approve" ? "Your answer was accepted for this purchase." : "Your decline was accepted for this purchase.", "success");
  await refreshPending();
}

async function performTighten() {
  const mandate = state.mandate?.mandate;
  if (!mandate || mandate.status !== "active") throw new Error("No active permission is available to tighten.");
  await walletApi.tighten(mandate.mandate_id);
  closeOverlay();
  navigate("wallet");
  toast("Uncertain purchases will now be declined.", "success");
}

async function performRevoke() {
  const mandate = state.mandate?.mandate;
  if (!mandate || mandate.status !== "active") throw new Error("No active permission is available to revoke.");
  await walletApi.revoke(mandate.mandate_id);
  closeOverlay();
  navigate("wallet");
  toast("The spending permission was revoked.", "success");
}

document.addEventListener("click", async (event) => {
  const route = event.target.closest("[data-route]");
  if (route) { navigate(route.dataset.route); return; }
  const button = event.target.closest("[data-action]");
  if (!button || button.disabled) return;
  const action = button.dataset.action;
  try {
    if (action === "close-overlay") {
      if (button === event.target || button.classList.contains("overlay-close") || event.target.classList.contains("overlay-backdrop")) closeOverlay();
      return;
    }
    if (action === "wallet-tab") { state.walletTab = button.dataset.tab; navigate("wallet", { keepScroll: true }); return; }
    if (action === "activity-filter") { state.activityFilter = button.dataset.filter; document.querySelector("#activity-list").innerHTML = activityRows(); document.querySelectorAll(".activity-tabs [role=tab]").forEach((tab) => { const active = tab === button; tab.classList.toggle("selected", active); tab.setAttribute("aria-selected", String(active)); tab.tabIndex = active ? 0 : -1; }); return; }
    if (action === "use-example") { const composer = document.querySelector("#shop-prompt"); composer.value = button.textContent; state.prompt = composer.value; composer.focus(); composer.dispatchEvent(new Event("input", { bubbles: true })); return; }
    if (action === "open-filters") { openFilters(); return; }
    if (action === "filter-category") {
      state.filters.category = button.dataset.category;
      state.filters.budget = button.dataset.category === "monitor" ? 400 : 200;
      state.filters.brand = "Any";
      state.filters.color = "Any";
      state.filters.size = "";
      openFilters();
      return;
    }
    if (action === "apply-filters") { state.prompt = filterRequest(); closeOverlay(); navigate("shop"); return; }
    if (action === "account") { openOverlay(`<span class="section-kicker">LOCAL DEMO ACCOUNT</span><h2>${esc(state.user || "Sign in")}</h2><p class="calm-copy">This demo uses a local username and session cookie. It is not a Viseca banking login.</p>${state.user ? `<button type="button" class="outline-button" data-action="logout">Sign out</button>` : `<button type="button" class="outline-button" data-action="close-overlay">Close</button>`}`, "Account"); return; }
    if (action === "open-pending") { openPending(button.dataset.id); return; }
    if (action === "inspector") { inspector(button.dataset.tab); return; }
    if (action === "open-reject") { confirmDialog("Reject this spending plan?", "Your agent will not receive authority from this request.", "reject", "Reject request"); return; }
    if (action === "open-tighten") { confirmDialog("Decline uncertain purchases?", "Future purchases with missing evidence will be declined instead of asking you.", "tighten", "Decline uncertainty"); return; }
    if (action === "open-revoke") { confirmDialog("Revoke this permission?", "Your shopping agent will no longer be able to use it.", "revoke", "Revoke permission"); return; }
    if (action === "answer-question") { state.answers[button.dataset.question] = button.dataset.answer; await renderReview(state.serial); return; }
    if (action === "open-detail") { const detail = state.details.get(button.dataset.id) || validateDecision(await walletApi.decision(button.dataset.id)); openDetail(detail); return; }
    if (action === "reload") { void render(); return; }
    button.disabled = true;
    if (action === "login") {
      const username = text(document.querySelector("#username").value.trim(), "Username");
      const session = await walletApi.login(username);
      state.user = text(session.username, "Session username");
      navigate(linkedDraftId() ? "review" : "shop");
    } else if (action === "logout") {
      await walletApi.logout();
      window.sessionStorage.removeItem(MANDATE_KEY);
      window.clearInterval(state.timer);
      window.clearTimeout(state.exampleTimer);
      state.serial += 1;
      state.user = null;
      state.mandate = null;
      state.pending = [];
      state.details.clear();
      closeOverlay();
      renderLogin();
    } else if (action === "confirm") await performConfirm();
    else if (action === "reject") await performReject();
    else if (action === "resolve") await performResolution(button);
    else if (action === "tighten") await performTighten();
    else if (action === "revoke") await performRevoke();
    else if (action === "copy-prompt") {
      const prompt = text(document.querySelector("#shop-prompt").value.trim(), "Shopping request");
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard access requires a secure browser connection. Select the request and copy it manually.");
      await navigator.clipboard.writeText(prompt);
      button.disabled = false;
      toast("Request copied. Paste it into your connected shopping agent.", "success");
    }
  } catch (error) {
    if (error.status === 409 && state.route === "review") { state.draft = null; state.answers = {}; void render(); }
    toast(error.message);
    if (button.isConnected) button.disabled = false;
  }
});

document.addEventListener("input", (event) => {
  if (event.target.id === "filter-budget") {
    state.filters.budget = Number(event.target.value);
    document.querySelector("#budget-value").textContent = `CHF ${state.filters.budget}`;
    document.querySelector("#filter-preview-text").textContent = filterRequest();
    return;
  }
  if (event.target.id !== "shop-prompt") return;
  state.prompt = event.target.value;
  const send = document.querySelector(".send-button");
  if (send) send.disabled = !state.prompt.trim();
  if (state.exampleTimer) window.clearTimeout(state.exampleTimer);
  const example = document.querySelector(".prompt-example");
  if (example) example.hidden = Boolean(state.prompt);
});

document.addEventListener("change", (event) => {
  const fields = { "filter-brand": "brand", "filter-color": "color", "filter-size": "size", "filter-usbc": "usbC" };
  const field = fields[event.target.id];
  if (!field) return;
  state.filters[field] = field === "usbC" ? event.target.checked : event.target.value;
  document.querySelector("#filter-preview-text").textContent = filterRequest();
});

document.addEventListener("focusin", (event) => {
  if (event.target.id === "shop-prompt") window.clearTimeout(state.exampleTimer);
});

document.addEventListener("focusout", (event) => {
  if (event.target.id === "shop-prompt" && !event.target.value) startExamples();
});

new MutationObserver(() => {
  const dialog = overlayRoot.querySelector("[role=dialog]");
  document.querySelector(".app-shell").inert = Boolean(dialog);
  document.body.classList.toggle("dialog-open", Boolean(dialog));
  if (dialog && !dialog.contains(document.activeElement)) dialog.focus();
  if (!dialog && state.overlayTrigger?.isConnected) {
    state.overlayTrigger.focus();
    state.overlayTrigger = null;
  }
}).observe(overlayRoot, { childList: true });

window.addEventListener("keydown", (event) => {
  const dialog = overlayRoot.querySelector("[role=dialog]");
  if (event.key === "Escape" && dialog) { closeOverlay(); return; }
  if (dialog && event.key === "Tab") {
    const focusable = [...dialog.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), summary, [tabindex="0"]')].filter((node) => node.getClientRects().length);
    if (!focusable.length) { event.preventDefault(); dialog.focus(); return; }
    const first = focusable[0], last = focusable.at(-1);
    if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
  if (event.target.matches('[role="tab"]') && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
    event.preventDefault();
    const tabs = [...event.target.closest('[role="tablist"]').querySelectorAll('[role="tab"]')];
    const index = tabs.indexOf(event.target);
    const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    const group = event.target.closest('[role="tablist"]');
    if (group.classList.contains("wallet-tabs")) state.pendingTabFocus = "wallet";
    tabs[next].click();
    if (!group.classList.contains("wallet-tabs")) {
      window.queueMicrotask(() => document.querySelector('.inspector-tabs [aria-selected="true"], .activity-tabs [aria-selected="true"]')?.focus());
    }
  }
  if (event.key === "Enter" && event.target.id === "username") {
    event.preventDefault();
    document.querySelector('[data-action="login"]').click();
  }
});

window.addEventListener("hashchange", () => navigate(window.location.hash.slice(1) || (linkedDraftId() ? "review" : "shop")));
initialize();
