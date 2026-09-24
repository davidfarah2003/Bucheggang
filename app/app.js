const SAMPLE_DRAFT_URL = "../docs/samples/scen0002_draft.json";
const API_BASE = "";
const MANDATE_SESSION_KEY = "viseca.demo.mandateId";
const screen = document.querySelector("#screen");
const drawerRoot = document.querySelector("#drawer-root");
const toastRoot = document.querySelector("#toast-root");
const pageContext = document.querySelector("#page-context");
const pageTitles = {
  review: "Review request",
  approvals: "Approvals",
  policy: "My policy",
  activity: "Activity",
};

let currentRoute = "review";
let activeDraft = null;
let answers = {};
let pendingIds = new Set();
let submittingStepUps = new Set();
let approvalTimer = null;
let currentPolicy = null;

function esc(value) {
  if (value === null || value === undefined) throw new Error("A required display value is missing.");
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function pretty(value) {
  requireString(value, "display value");
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function money(value, currency) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) throw new Error("A monetary value is missing or invalid.");
  requireString(currency, "currency");
  return new Intl.NumberFormat("en-CH", { style: "currency", currency, maximumFractionDigits: 2 }).format(amount);
}

function showToast(message, tone = "") {
  const toast = document.createElement("div");
  toast.className = `toast ${tone ? `is-${tone}` : ""}`;
  toast.textContent = message;
  toastRoot.replaceChildren(toast);
  window.setTimeout(() => {
    if (toast.parentElement === toastRoot) toast.remove();
  }, 5000);
}

function dataError(title, error) {
  if (!(error instanceof Error)) throw new Error("The app received a non-Error failure value.");
  return `<div class="data-error" role="alert"><span class="error-mark" aria-hidden="true">!</span><div><strong>${esc(title)}</strong><p>${esc(error.message)}</p></div></div>`;
}

function requireString(value, field) {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${field} is missing or is not a non-empty string.`);
  return value;
}

function validateDraft(draft) {
  if (!draft || typeof draft !== "object") throw new Error("SCEN0002 draft must be a JSON object.");
  requireString(draft.draft_id, "draft_id");
  requireString(draft.hash, "hash");
  requireString(draft.instruction, "instruction");
  requireString(draft.uncertainty_policy, "uncertainty_policy");
  requireString(draft.created_at, "created_at");
  if (!["ask", "decline", "approve"].includes(draft.uncertainty_policy)) throw new Error(`uncertainty_policy ${draft.uncertainty_policy} is not supported.`);
  if (!Number.isInteger(draft.version)) throw new Error("version must be an integer.");
  if (!Array.isArray(draft.rules) || !Array.isArray(draft.examples) || !Array.isArray(draft.open_questions)) throw new Error("rules, examples and open_questions must be arrays.");
  draft.rules.forEach((rule, index) => {
    requireString(rule.field, `rules[${index}].field`);
    requireString(rule.operator, `rules[${index}].operator`);
    requireString(rule.source_text, `rules[${index}].source_text`);
    requireString(rule.plain_english, `rules[${index}].plain_english`);
    if (!(typeof rule.value === "number" || typeof rule.value === "string" || (Array.isArray(rule.value) && rule.value.every((item) => typeof item === "string")))) throw new Error(`rules[${index}].value has an unsupported type.`);
    if (rule.scope === "period" && (!Number.isInteger(rule.period_days) || rule.period_days < 1)) throw new Error(`rules[${index}].period_days must be a positive integer for a period rule.`);
  });
  draft.examples.forEach((example, index) => {
    requireString(example.description, `examples[${index}].description`);
    requireString(example.why, `examples[${index}].why`);
    if (!["approve", "decline", "step_up"].includes(example.expected)) throw new Error(`examples[${index}].expected has an unsupported outcome.`);
  });
  draft.open_questions.forEach((question, index) => {
    requireString(question.question, `open_questions[${index}].question`);
    if (!Array.isArray(question.options) || !question.options.length || !question.options.every((option) => typeof option === "string" && option.length)) throw new Error(`open_questions[${index}].options must be a non-empty string list.`);
    if (question.answer !== null && typeof question.answer !== "string") throw new Error(`open_questions[${index}].answer must be a string or null.`);
  });
  return draft;
}

async function readJson(response, label) {
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${label} returned HTTP ${response.status}${detail ? `: ${detail.slice(0, 240)}` : ""}`);
  }
  return response.status === 204 ? null : response.json();
}

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json" },
  });
  if (response.status === 409) {
    const detail = await response.text();
    const error = new Error(`The saved information changed before this action was accepted. Refresh and review it again.${detail ? ` ${detail.slice(0, 180)}` : ""}`);
    error.status = 409;
    throw error;
  }
  return readJson(response, path);
}

function mandateId() {
  return window.sessionStorage.getItem(MANDATE_SESSION_KEY);
}

function setActiveRoute(route) {
  if (!pageTitles[route]) {
    screen.innerHTML = dataError("Page could not be opened.", new Error(`Unknown app route: ${route}`));
    screen.setAttribute("aria-busy", "false");
    return;
  }
  currentRoute = route;
  if (window.location.hash !== `#${route}`) window.history.replaceState(null, "", `#${route}`);
  document.querySelectorAll("[data-route]").forEach((button) => {
    const active = button.dataset.route === route;
    button.classList.toggle("is-active", active);
    if (button.matches(".nav-item")) {
      if (active) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    }
  });
  pageContext.textContent = pageTitles[route];
  if (approvalTimer) window.clearInterval(approvalTimer);
  approvalTimer = null;
  drawerRoot.replaceChildren();
  screen.setAttribute("aria-busy", "true");
  renderRoute(route);
}

function setScreen(markup) {
  screen.innerHTML = markup;
  screen.setAttribute("aria-busy", "false");
}

function heading(eyebrow, title, description, action = "") {
  return `<div class="page-heading"><div><span class="eyebrow"><i class="eyebrow-mark"></i>${esc(eyebrow)}</span><h1>${esc(title)}</h1><p>${esc(description)}</p></div>${action ? `<div class="heading-actions">${action}</div>` : ""}</div>`;
}

function symbolFor(field) {
  if (field.includes("amount") || field.includes("subtotal")) return "CHF";
  if (field.includes("merchant")) return "⌂";
  if (field.includes("return")) return "↺";
  if (field.includes("size")) return "↕";
  if (field.includes("product") || field.includes("items")) return "◇";
  return "✓";
}

function ruleRows(rules = []) {
  return rules.map((rule) => `<div class="rule-row">
    <span class="rule-icon" aria-hidden="true">${esc(symbolFor(rule.field))}</span>
    <span class="rule-copy"><strong>${esc(rule.plain_english)}</strong><small>From your request: <mark>${esc(rule.source_text)}</mark></small></span>
    <span class="rule-tag">MUST HOLD</span>
  </div>`).join("");
}

function exampleCards(examples = []) {
  const groups = new Map();
  examples.forEach((example) => {
    const key = example.expected;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(example);
  });
  const symbols = { approve: "✓", decline: "×", step_up: "?" };
  return [...groups.entries()].map(([outcome, items]) => `<div class="example-card">
    <span class="example-symbol ${esc(outcome)}" aria-hidden="true">${esc(symbols[outcome])}</span>
    <div><strong>${esc(pretty(outcome))}${items.length > 1 ? `<span class="example-count">${items.length}</span>` : ""}</strong>
      ${items.map((item) => `<p>${esc(item.description)} <span>${esc(item.why)}</span></p>`).join("")}
    </div>
  </div>`).join("");
}

function answerLabel(value) {
  const labels = { ask: "Ask me", "ask me": "Ask me", decline: "Decline", yes: "Yes" };
  return Object.hasOwn(labels, value) ? labels[value] : value;
}

function questionCards(questions = []) {
  return questions.map((question, index) => {
    const selected = answers[question.question] === undefined ? question.answer : answers[question.question];
    return `<div class="question-item"><div class="question-text"><span class="question-number">${index + 1}</span><span>${esc(question.question)}</span></div>
      <div class="choice-row" role="group" aria-label="${esc(question.question)}">
        ${question.options.map((option) => `<button class="choice-button ${selected === option ? "is-selected" : ""}" type="button" data-action="answer" data-question="${esc(question.question)}" data-value="${esc(option)}" aria-pressed="${selected === option}">${esc(answerLabel(option))}</button>`).join("")}
      </div>
    </div>`;
  }).join("");
}

function summaryCard(ruleCount, questionCount) {
  return `<section class="card side-summary">
    <div class="summary-top"><span class="eyebrow"><i class="eyebrow-mark"></i>YOUR CONTROL</span><h3>Your rules, your call.</h3><p>The shopping agent can work within these limits. Only you can approve an exception.</p></div>
    <div class="summary-body">
      <div class="summary-row"><span>Rules to protect you</span><strong>${ruleCount} checks</strong></div>
      <div class="summary-row"><span>Questions for you</span><strong>${questionCount} to answer</strong></div>
      <div class="summary-row"><span>Card details shared</span><strong>No</strong></div>
    </div>
  </section>
  <section class="learn-card"><span class="learn-icon" aria-hidden="true">i</span><strong>Why am I seeing this?</strong><p>Your shopping agent suggested a policy. Review the exact saved version here before it can make a purchase.</p><button type="button" data-action="show-policy-note">How confirmation works <span aria-hidden="true">→</span></button></section>`;
}

async function loadDraft() {
  const response = await fetch(SAMPLE_DRAFT_URL, { cache: "no-store" });
  return readJson(response, "SCEN0002 draft sample");
}

async function renderReview() {
  try {
    const selectedAnswers = { ...answers };
    const draft = validateDraft(await loadDraft());
    activeDraft = draft;
    answers = {};
    draft.open_questions.forEach((question) => {
      if (question.answer !== null && question.answer !== undefined) answers[question.question] = question.answer;
    });
    Object.keys(selectedAnswers).forEach((question) => {
      if (draft.open_questions.some((item) => item.question === question)) answers[question] = selectedAnswers[question];
    });
    const unanswered = draft.open_questions.filter((question) => !answers[question.question]).length;
    document.querySelector("#review-count").textContent = unanswered ? String(unanswered) : "✓";
    const request = draft.instruction;
    setScreen(`${heading("POLICY REQUEST", "Make sure it feels right.", "Review what your shopping agent plans to follow. Every limit below comes from your request.")}
      <div class="content-grid">
        <div class="main-column">
          <section class="hero-card">
            <div class="hero-topline"><span class="status-chip"><i class="chip-dot"></i>Waiting for your review</span><span class="small-meta">Draft version ${esc(draft.version)}</span></div>
            <div class="hero-copy"><h2>A clearer plan. A safer way to shop.</h2><p>Read the saved policy in your own words. The agent only gets permission after you confirm this exact version.</p></div>
            <div class="instruction-quote"><strong>Your request</strong><br />“${esc(request)}”</div>
          </section>
          <section class="card card-pad">
            <div class="section-head"><div><h2 class="section-title">The rules you asked for</h2><div class="section-subtitle">Each check stays attached to the words you used.</div></div><span class="rule-tag">${draft.rules.length} RULES</span></div>
            <div class="rules-list">${ruleRows(draft.rules)}</div>
          </section>
          <section class="card card-pad">
            <div class="section-head"><div><h2 class="section-title">Try a few examples</h2><div class="section-subtitle">See what these rules would allow.</div></div><span class="small-meta">From your policy draft</span></div>
            <div class="example-grid">${exampleCards(draft.examples)}</div>
          </section>
          ${draft.open_questions.length ? `<section class="card card-pad"><div class="section-head"><div><h2 class="section-title">A couple of choices need you</h2><div class="section-subtitle">Your answers become part of this policy.</div></div><span class="status-chip"><i class="chip-dot"></i>${unanswered ? `${unanswered} unanswered` : "Complete"}</span></div><div class="question-list">${questionCards(draft.open_questions)}</div></section>` : ""}
          <div class="confirm-actions"><span class="actions-note"><i class="mini-lock" aria-hidden="true"></i>Confirmation applies to version ${esc(draft.version)} only.</span><div class="button-row"><button type="button" class="button button-secondary" data-action="reject-draft">Reject</button><button type="button" class="button button-primary" data-action="confirm-draft" ${unanswered ? "disabled" : ""}>Confirm policy <span class="button-arrow" aria-hidden="true">→</span></button></div></div>
        </div>
        <aside class="side-column">${summaryCard(draft.rules.length, unanswered)}</aside>
      </div>`);
  } catch (error) {
    setScreen(`${heading("POLICY REQUEST", "Make sure it feels right.", "Review the policy saved by your shopping agent.")}${dataError("The policy draft could not be loaded.", error)}`);
  }
}

function stepUpCard(stepUp) {
  requireString(stepUp.authorization_id, "StepUp.authorization_id");
  requireString(stepUp.expires_at, `StepUp ${stepUp.authorization_id}.expires_at`);
  if (!stepUp.event || !stepUp.event.authorization || !stepUp.event.authorization.merchant || !stepUp.decision) throw new Error(`StepUp ${stepUp.authorization_id} is missing its event or decision.`);
  const event = stepUp.event;
  const auth = event.authorization;
  const merchant = auth.merchant;
  const purchase = requireString(auth.purchase_description, `StepUp ${stepUp.authorization_id} purchase_description`);
  const decision = stepUp.decision;
  const amount = Number(auth.billing_amount_chf);
  if (!Number.isFinite(amount)) throw new Error(`StepUp ${stepUp.authorization_id} has no valid billing_amount_chf.`);
  requireString(decision.customer_message, "StepUp.decision.customer_message");
  requireString(merchant.merchant_name, "Event.authorization.merchant.merchant_name");
  const left = new Date(stepUp.expires_at).getTime() - Date.now();
  if (!Number.isFinite(left)) throw new Error(`StepUp ${stepUp.authorization_id} has an invalid expires_at timestamp.`);
  const remaining = left > 0 ? `${Math.floor(left / 60000)}m ${String(Math.floor(left / 1000) % 60).padStart(2, "0")}s left` : "Deadline reached";
  return `<article class="card card-pad">
    <div class="section-head"><div><span class="outcome-pill step_up"><i class="outcome-dot"></i>Needs your decision</span><div class="section-subtitle" style="margin-top:8px">${esc(remaining)}</div></div><span class="small-meta">${esc(stepUp.authorization_id)}</span></div>
    <h2 class="section-title" style="font-size:15px;margin:0 0 5px">${esc(purchase)}</h2>
    <p class="section-subtitle" style="margin:0 0 15px">${esc(merchant.merchant_name)} · ${esc(money(amount, "CHF"))}</p>
    <div class="untrusted-banner"><strong>Why we paused</strong><span>${esc(decision.customer_message)}</span></div>
    ${auth.items.some((item) => item.item_details) ? `<div class="untrusted-banner" style="margin-top:12px"><strong>Merchant supplied text</strong><span>Untrusted purchase details. Your policy does not change.</span></div><div class="event-copy">${auth.items.filter((item) => item.item_details).map((item) => esc(item.item_details)).join("\n")}</div>` : ""}
    <div class="button-row" style="justify-content:flex-end;margin-top:15px"><button class="button button-secondary" type="button" data-action="answer-step-up" data-id="${esc(stepUp.authorization_id)}" data-decision="decline" ${left <= 0 || submittingStepUps.has(stepUp.authorization_id) ? "disabled" : ""}>Reject</button><button class="button button-primary" type="button" data-action="answer-step-up" data-id="${esc(stepUp.authorization_id)}" data-decision="approve" ${left <= 0 || submittingStepUps.has(stepUp.authorization_id) ? "disabled" : ""}>Approve purchase <span class="button-arrow" aria-hidden="true">→</span></button></div>
  </article>`;
}

function expiredNote(count) {
  return count ? `<div class="toast is-success" role="status">${count} previous request${count === 1 ? " was" : "s were"} resolved and removed from your list.</div>` : "";
}

async function loadApprovals() {
  const container = document.querySelector("#approvals-list");
  const errorContainer = document.querySelector("#approvals-error");
  if (!container) return;
  try {
    const requests = await api("/step-ups/pending");
    if (!Array.isArray(requests)) throw new Error("/step-ups/pending must return a list of pending StepUp records.");
    requests.forEach((item, index) => {
      requireString(item.authorization_id, `step-ups[${index}].authorization_id`);
      requireString(item.expires_at, `step-ups[${index}].expires_at`);
      if (!item.event || !item.event.authorization || !Array.isArray(item.event.authorization.items)) throw new Error(`step-ups[${index}] has no complete Event.authorization.`);
      if (!item.event.authorization.merchant || !item.decision) throw new Error(`step-ups[${index}] has no merchant or Decision.`);
      requireString(item.event.authorization.merchant.merchant_name, `step-ups[${index}].event.authorization.merchant.merchant_name`);
      requireString(item.decision.customer_message, `step-ups[${index}].decision.customer_message`);
      if (!Number.isFinite(new Date(item.expires_at).getTime())) throw new Error(`step-ups[${index}].expires_at is invalid.`);
    });
    if (!container.isConnected) return;
    const ids = new Set(requests.map((item) => item.authorization_id));
    const removed = [...pendingIds].filter((id) => !ids.has(id));
    pendingIds = ids;
    document.querySelector("#approval-count").textContent = requests.length ? String(requests.length) : "0";
    container.innerHTML = requests.length ? `<div class="list-stack">${requests.map(stepUpCard).join("")}</div>` : `<section class="card empty-state"><div><div class="empty-mark" aria-hidden="true">✓</div><h3>You’re all caught up</h3><p>When a purchase needs your decision, it will appear here with the reason and its deadline.</p></div></section>`;
    if (errorContainer) errorContainer.innerHTML = removed.length ? expiredNote(removed.length) : "";
  } catch (error) {
    if (!container.isConnected) return;
    document.querySelector("#approval-count").textContent = "—";
    container.replaceChildren();
    if (errorContainer) errorContainer.innerHTML = dataError("Pending approvals could not be refreshed.", error);
    else container.innerHTML = dataError("Pending approvals could not be loaded.", error);
  }
}

async function renderApprovals() {
  setScreen(`${heading("PURCHASE CHECKS", "A pause is a chance to choose.", "Review a specific purchase and the reason it needs your attention.")}
    <div class="main-column"><div id="approvals-error"></div><div id="approvals-list"><div class="loading-panel"><span class="spinner" aria-hidden="true"></span><span>Checking for pending approvals…</span></div></div></div>`);
  await loadApprovals();
  if (currentRoute === "approvals") approvalTimer = window.setInterval(() => loadApprovals(), 2000);
}

function noMandate() {
  return `<section class="card empty-state"><div><div class="empty-mark" aria-hidden="true">◇</div><h3>Confirm a policy to continue</h3><p>Your active mandate will appear here after you review and confirm a policy request.</p><button class="button button-primary button-small" type="button" data-route="review" style="margin-top:14px">Review request <span class="button-arrow" aria-hidden="true">→</span></button></div></section>`;
}

function formatRuleValue(rule) {
  const value = Array.isArray(rule.value) ? rule.value.join(", ") : rule.value;
  return `${esc(rule.operator)} ${rule.currency ? `${esc(rule.currency)} ` : ""}${esc(value)}`;
}

function ruleViews(rules = []) {
  return rules.map((rule) => `<div class="rule-view-row"><div><strong>${esc(rule.plain_english)}</strong><small>From your request: ${esc(rule.source_text)}</small></div><span class="rule-value">${formatRuleValue(rule)}</span></div>`).join("");
}

function getPayloadParts(payload) {
  if (!payload || !payload.mandate || !payload.draft || !payload.state) throw new Error("GET /mandates/{mandate_id} must return { mandate, draft, state }.");
  requireString(payload.mandate.mandate_id, "Mandate.mandate_id");
  requireString(payload.mandate.status, "Mandate.status");
  if (!["active", "revoked", "expired"].includes(payload.mandate.status)) throw new Error(`Mandate.status ${payload.mandate.status} is not supported.`);
  requireString(payload.mandate.confirmed_at, "Mandate.confirmed_at");
  if (!Number.isFinite(new Date(payload.mandate.confirmed_at).getTime())) throw new Error("Mandate.confirmed_at is not a valid timestamp.");
  if (!Number.isInteger(payload.mandate.version)) throw new Error("Mandate.version must be an integer.");
  validateDraft(payload.draft);
  if (payload.state.mandate_id !== payload.mandate.mandate_id) throw new Error("MandateState.mandate_id does not match Mandate.mandate_id.");
  if (!Array.isArray(payload.state.approvals)) throw new Error("MandateState.approvals must be a list.");
  payload.state.approvals.forEach((approval, index) => {
    requireString(approval.authorization_id, `state.approvals[${index}].authorization_id`);
    requireString(approval.timestamp, `state.approvals[${index}].timestamp`);
    if (!Number.isFinite(new Date(approval.timestamp).getTime())) throw new Error(`state.approvals[${index}].timestamp is invalid.`);
    if (typeof approval.amount_chf !== "number" || !Number.isFinite(approval.amount_chf)) throw new Error(`state.approvals[${index}].amount_chf is invalid.`);
  });
  return { mandate: payload.mandate, draft: payload.draft, state: payload.state };
}

function periodSpendRules(rules = []) {
  return rules.filter((rule) => rule.scope === "period" && rule.field === "authorization.billing_amount_chf");
}

function spendMetrics(approvals, rules) {
  const periodRules = periodSpendRules(rules);
  if (!approvals.length) return `<div class="metric-grid"><div class="metric-card"><div class="metric-label">Approved purchases</div><div class="metric-value">0</div><div class="metric-foot">This mandate</div></div><div class="metric-card"><div class="metric-label">Spend so far</div><div class="metric-value">CHF 0</div><div class="metric-foot">No accepted approvals yet</div></div></div>`;
  if (!periodRules.length) {
    const total = approvals.reduce((sum, item) => sum + Number(item.amount_chf), 0);
    return `<div class="metric-grid"><div class="metric-card"><div class="metric-label">Approved purchases</div><div class="metric-value">${approvals.length}</div><div class="metric-foot">This mandate</div></div><div class="metric-card"><div class="metric-label">Approved spend</div><div class="metric-value">${esc(money(total, "CHF"))}</div><div class="metric-foot">This mandate · no rolling window set</div></div></div>`;
  }
  return `<div class="metric-grid">${periodRules.map((rule) => {
    const timestamps = approvals.map((item) => new Date(item.timestamp).getTime());
    const simulatedNow = Math.max(...timestamps);
    const cutoff = simulatedNow - rule.period_days * 86400000;
    const recent = approvals.filter((item) => new Date(item.timestamp).getTime() >= cutoff);
    const total = recent.reduce((sum, item) => sum + Number(item.amount_chf), 0);
    return `<div class="metric-card"><div class="metric-label">Spend · last ${esc(rule.period_days)} days</div><div class="metric-value">${esc(money(total, "CHF"))}</div><div class="metric-foot">${recent.length} approved purchases · as of ${esc(timeLabel(simulatedNow))}</div></div>`;
  }).join("")}</div>`;
}

async function renderPolicy() {
  const id = mandateId();
  if (!id) {
    setScreen(`${heading("YOUR WALLET", "Your policy, in your hands.", "See what your shopping agent can do and narrow the rules whenever you like.")}${noMandate()}`);
    return;
  }
  setScreen(`${heading("YOUR WALLET", "Your policy, in your hands.", "See what your shopping agent can do and narrow the rules whenever you like.")}<div class="loading-panel"><span class="spinner" aria-hidden="true"></span><span>Loading your mandate…</span></div>`);
  try {
    const { mandate, draft, state } = getPayloadParts(await api(`/mandates/${encodeURIComponent(id)}`));
    currentPolicy = { mandate, draft, state };
    const approvals = state.approvals;
    const isActive = mandate.status === "active";
    setScreen(`${heading("YOUR WALLET", "Your policy, in your hands.", "See what your shopping agent can do and narrow the rules whenever you like.", `<span class="outcome-pill ${isActive ? "approve" : "decline"}"><i class="outcome-dot"></i>${esc(pretty(mandate.status))}</span>`)}
      <div class="content-grid"><div class="main-column">
        <section class="card card-pad"><div class="section-head"><div><h2 class="section-title">Spend and purchase activity</h2><div class="section-subtitle">Counts include accepted approvals only.</div></div></div>${spendMetrics(approvals, draft.rules)}</section>
        <section class="card card-pad"><div class="section-head"><div><h2 class="section-title">Your rules</h2><div class="section-subtitle">The agent follows every one of these limits while the mandate is active.</div></div></div><div class="rule-view">${ruleViews(draft.rules)}</div><div class="policy-actions"><button class="button button-secondary button-small" type="button" data-action="open-tighten" ${isActive ? "" : "disabled"}>Tighten a rule</button><button class="button button-danger button-small" type="button" data-action="revoke-mandate" ${isActive ? "" : "disabled"}>Revoke mandate</button></div></section>
      </div><aside class="side-column"><section class="card side-summary"><div class="summary-top"><span class="eyebrow"><i class="eyebrow-mark"></i>MANDATE</span><h3>${esc(mandate.status === "active" ? "Active and protected" : pretty(mandate.status))}</h3><p>Confirmed ${esc(new Date(mandate.confirmed_at).toLocaleDateString())} · version ${esc(mandate.version)}</p></div><div class="summary-body"><div class="summary-row"><span>Mandate ID</span><strong>${esc(mandate.mandate_id)}</strong></div><div class="summary-row"><span>Policy version</span><strong>${esc(mandate.version)}</strong></div><div class="summary-row"><span>Uncertainty</span><strong>${esc(pretty(draft.uncertainty_policy))}</strong></div></div></section><section class="learn-card"><span class="learn-icon" aria-hidden="true">↗</span><strong>Keep your policy current</strong><p>You can always add a stricter limit or stop the mandate. The shopping agent cannot loosen these rules.</p></section></aside></div>`);
  } catch (error) {
    setScreen(`${heading("YOUR WALLET", "Your policy, in your hands.", "See what your shopping agent can do and narrow the rules whenever you like.")}${dataError("Your mandate could not be loaded.", error)}`);
  }
}

function outcomePill(outcome) {
  if (!["approve", "decline", "step_up"].includes(outcome)) throw new Error(`Decision outcome ${outcome} is not supported.`);
  const value = outcome;
  return `<span class="outcome-pill ${esc(value)}"><i class="outcome-dot"></i>${esc(pretty(value))}</span>`;
}

function timeLabel(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) throw new Error(`Invalid timestamp: ${value}`);
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

async function renderActivity() {
  const id = mandateId();
  if (!id) {
    setScreen(`${heading("YOUR ACTIVITY", "Every decision, clearly explained.", "See what happened and open the evidence behind any decision.")}${noMandate()}`);
    return;
  }
  setScreen(`${heading("YOUR ACTIVITY", "Every decision, clearly explained.", "See what happened and open the evidence behind any decision.")}<div class="loading-panel"><span class="spinner" aria-hidden="true"></span><span>Loading recent decisions…</span></div>`);
  try {
    const decisions = await api(`/mandates/${encodeURIComponent(id)}/decisions`);
    if (!Array.isArray(decisions)) throw new Error("GET /mandates/{mandate_id}/decisions must return a list.");
    if (!decisions.length) {
      setScreen(`${heading("YOUR ACTIVITY", "Every decision, clearly explained.", "See what happened and open the evidence behind any decision.")}<section class="card empty-state"><div><div class="empty-mark" aria-hidden="true">◷</div><h3>No purchases yet</h3><p>When the agent submits a purchase, its decision and evidence will appear here.</p></div></section>`);
      return;
    }
    decisions.forEach((entry, index) => {
      if (!entry || !entry.decision || !entry.state_after) throw new Error(`History entry ${index} must include decision and state_after.`);
      const decision = entry.decision;
      requireString(decision.authorization_id, "Decision.authorization_id");
      outcomePill(decision.decision);
      requireString(decision.customer_message, `Decision ${decision.authorization_id}.customer_message`);
      requireString(decision.explanation, `Decision ${decision.authorization_id}.explanation`);
      requireString(decision.engine_version, `Decision ${decision.authorization_id}.engine_version`);
      requireString(decision.decided_at, `Decision ${decision.authorization_id}.decided_at`);
      if (!Array.isArray(decision.reason_codes) || !Array.isArray(decision.evidence)) throw new Error(`Decision ${decision.authorization_id} must include reason_codes and evidence lists.`);
    });
    setScreen(`${heading("YOUR ACTIVITY", "Every decision, clearly explained.", "Open any purchase to see the checks, evidence, and state that shaped the result." )}
      <section class="card card-pad"><div class="section-head"><div><h2 class="section-title">Purchase history</h2><div class="section-subtitle">${decisions.length} decision${decisions.length === 1 ? "" : "s"} for this mandate</div></div></div><div class="list-stack">${[...decisions].reverse().map((entry) => {
      const decision = entry.decision;
      return `<button class="list-row" type="button" data-action="open-decision" data-id="${esc(decision.authorization_id)}"><span class="list-row-main"><span class="list-row-title">${esc(decision.authorization_id)} ${outcomePill(decision.decision)}</span><span class="list-row-sub">${esc(decision.customer_message)}</span></span><span class="list-row-end">${esc(timeLabel(decision.decided_at))}<br /><span aria-hidden="true">↗</span></span></button>`;
      }).join("")}</div></section>`);
  } catch (error) {
    setScreen(`${heading("YOUR ACTIVITY", "Every decision, clearly explained.", "See what happened and open the evidence behind any decision.")}${dataError("Purchase history could not be loaded.", error)}`);
  }
}

async function openDecision(id) {
  drawerRoot.innerHTML = `<div class="drawer-backdrop" data-action="close-drawer"><aside class="drawer" role="dialog" aria-modal="true" aria-label="Decision evidence"><div class="loading-panel"><span class="spinner" aria-hidden="true"></span><span>Loading decision evidence…</span></div></aside></div>`;
  try {
    const payload = await api(`/decisions/${encodeURIComponent(id)}`);
    if (!payload || !payload.decision || !payload.event || !("state_before" in payload) || !("state_after" in payload)) throw new Error("GET /decisions/{authorization_id} must return decision, event, state_before and state_after.");
    const decision = payload.decision;
    const event = payload.event;
    requireString(decision.authorization_id, "Decision.authorization_id");
    outcomePill(decision.decision);
    requireString(decision.customer_message, "Decision.customer_message");
    requireString(decision.explanation, "Decision.explanation");
    requireString(decision.engine_version, "Decision.engine_version");
    requireString(decision.decided_at, "Decision.decided_at");
    if (!Array.isArray(decision.reason_codes) || !Array.isArray(decision.evidence)) throw new Error("Decision.reason_codes and Decision.evidence must be arrays.");
    if (!event.authorization || !Array.isArray(event.authorization.items)) throw new Error("Event.authorization.items must be a list.");
    const itemDetails = event.authorization.items.map((item, index) => {
      if (typeof item.item_details !== "string") throw new Error(`Event.authorization.items[${index}].item_details must be a string.`);
      return item.item_details;
    });
    const checks = decision.evidence.map((check, index) => {
      requireString(check.name, `Decision.evidence[${index}].name`);
      requireString(check.result, `Decision.evidence[${index}].result`);
      requireString(check.source, `Decision.evidence[${index}].source`);
      if (typeof check.note !== "string") throw new Error(`Decision.evidence[${index}].note must be a string.`);
      if (!["pass", "fail", "uncertain"].includes(check.result)) throw new Error(`Decision.evidence[${index}].result is unsupported.`);
      if (!("value" in check)) throw new Error(`Decision.evidence[${index}].value is missing.`);
      return `<div class="check-row"><span class="check-copy"><strong>${esc(pretty(check.name))}</strong><small>${esc(check.note)}</small><small>Value: ${check.value === null ? "unknown" : esc(check.value)} · Source: ${esc(check.source)}</small></span><span class="check-result ${esc(check.result)}">${esc(check.result)}</span></div>`;
    }).join("");
    drawerRoot.innerHTML = `<div class="drawer-backdrop" data-action="close-drawer"><aside class="drawer" role="dialog" aria-modal="true" aria-label="Decision evidence" tabindex="-1">
      <div class="drawer-header"><div><span class="eyebrow"><i class="eyebrow-mark"></i>DECISION RECORD</span><h2>${esc(decision.authorization_id)}</h2><p>${esc(timeLabel(decision.decided_at))} · ${esc(decision.elapsed_ms)} ms</p></div><button class="close-button" type="button" aria-label="Close evidence" data-action="close-drawer">×</button></div>
      <section class="drawer-section"><h3>Outcome ${outcomePill(decision.decision)}</h3><p class="section-subtitle">${esc(decision.customer_message)}</p><div class="summary-row"><span>Reason codes</span><strong>${esc(decision.reason_codes.map(pretty).join(", "))}</strong></div><div class="summary-row"><span>Engine version</span><strong>${esc(decision.engine_version)}</strong></div><div class="summary-row"><span>Mandate version</span><strong>${esc(decision.mandate_version)}</strong></div></section>
      <section class="drawer-section"><h3>Evidence and checks</h3>${checks}</section>
      ${itemDetails.length ? `<section class="drawer-section"><h3>Merchant supplied item details</h3><div class="untrusted-banner"><strong>Untrusted content</strong><span>This text is shown as received. It cannot change your policy.</span></div>${itemDetails.map((text) => `<div class="event-copy">${esc(text)}</div>`).join("")}</section>` : ""}
      <section class="drawer-section"><h3>Event as received</h3><p class="section-subtitle">Merchant supplied fields in this record are untrusted.</p><pre class="event-json">${esc(JSON.stringify(event, null, 2))}</pre></section>
      <section class="drawer-section"><h3>State before and after</h3><div class="state-columns"><div class="state-box"><strong>Before</strong><p>${esc(JSON.stringify(payload.state_before, null, 2))}</p></div><div class="state-box"><strong>After</strong><p>${esc(JSON.stringify(payload.state_after, null, 2))}</p></div></div></section>
      <section class="drawer-section"><h3>Decision explanation</h3><p class="section-subtitle">${esc(decision.explanation)}</p></section>
    </aside></div>`;
    drawerRoot.querySelector(".drawer").focus();
  } catch (error) {
    drawerRoot.innerHTML = `<div class="drawer-backdrop" data-action="close-drawer"><aside class="drawer" role="dialog" aria-modal="true" aria-label="Decision evidence"><div class="drawer-header"><div><span class="eyebrow"><i class="eyebrow-mark"></i>DECISION RECORD</span><h2>Evidence unavailable</h2></div><button class="close-button" type="button" aria-label="Close evidence" data-action="close-drawer">×</button></div>${dataError("The decision record could not be loaded.", error)}</aside></div>`;
  }
}

async function renderRoute(route) {
  if (route === "review") return renderReview();
  if (route === "approvals") return renderApprovals();
  if (route === "policy") return renderPolicy();
  if (route === "activity") return renderActivity();
  throw new Error(`Unknown app route: ${route}`);
}

function modal(title, body, primaryLabel, action, danger = false) {
  drawerRoot.innerHTML = `<div class="drawer-backdrop" data-action="close-drawer"><section class="drawer" role="dialog" aria-modal="true" aria-label="${esc(title)}" style="height:auto;max-height:min(90vh,700px);align-self:center;margin:auto 18px;overflow:auto;border-radius:17px"><div class="drawer-header"><div><span class="eyebrow"><i class="eyebrow-mark"></i>YOUR WALLET</span><h2>${esc(title)}</h2></div><button class="close-button" type="button" aria-label="Close" data-action="close-drawer">×</button></div><div>${body}</div><div class="button-row" style="justify-content:flex-end;margin-top:18px"><button class="button button-secondary" type="button" data-action="close-drawer">Cancel</button><button class="button ${danger ? "button-danger" : "button-primary"}" type="button" data-action="${esc(action)}">${esc(primaryLabel)}</button></div></section></div>`;
  drawerRoot.querySelector("[role=dialog]").focus();
}

function openTighten() {
  if (!currentPolicy || currentPolicy.mandate.status !== "active") throw new Error("Only an active mandate can be tightened.");
  modal("Make this policy stricter", `<p class="section-subtitle">Add one restriction to the policy you confirmed. You can set another one after this change is saved.</p>
    <label class="field-label" style="margin-top:16px">New per-purchase limit in CHF<input id="tighten-cap" inputmode="decimal" type="number" min="1" step="1" placeholder="e.g. 150" /><small class="helper-text">This limit will be added to your existing rules.</small></label>
    <div class="toggle-row"><span class="toggle-copy"><strong>Decline when details are uncertain</strong><small>Replace “ask me” with a stricter default.</small></span><button class="toggle-switch" type="button" role="switch" aria-checked="false" data-action="toggle-uncertainty" aria-label="Decline when details are uncertain"></button></div>`, "Apply tightening", "submit-tighten");
}

function openRevoke() {
  modal("Revoke this mandate?", `<p class="section-subtitle">The shopping agent will no longer be able to use this mandate. This action cannot be undone in the app.</p>`, "Revoke mandate", "confirm-revoke", true);
}

async function confirmDraft() {
  if (!activeDraft) throw new Error("There is no loaded draft to confirm.");
  const missing = activeDraft.open_questions.filter((question) => !(answers[question.question] ?? question.answer));
  if (missing.length) throw new Error("Answer every open question before confirming this draft.");
  const body = {
    version: activeDraft.version,
    hash: activeDraft.hash,
    answers: Object.fromEntries(activeDraft.open_questions.map((question) => [question.question, answers[question.question] ?? question.answer])),
  };
  try {
    const mandate = await api(`/drafts/${encodeURIComponent(activeDraft.draft_id)}/confirm`, { method: "POST", body: JSON.stringify(body) });
    requireString(mandate && mandate.mandate_id, "Policy confirmation response mandate_id");
    window.sessionStorage.setItem(MANDATE_SESSION_KEY, mandate.mandate_id);
    showToast("Your policy is confirmed. The mandate is now active.", "success");
    setActiveRoute("policy");
  } catch (error) {
    if (error.status === 409) {
      showToast("The draft changed. Reloading the latest version for you.", "error");
      activeDraft = null;
      answers = {};
      await renderReview();
      return;
    }
    throw error;
  }
}

async function rejectDraft() {
  if (!activeDraft) throw new Error("There is no loaded draft to reject.");
  modal("Reject this policy request?", `<p class="section-subtitle">The shopping agent will not receive a mandate from this draft. You can review another request later.</p>`, "Reject request", "confirm-reject", true);
}

async function answerStepUp(id, decision) {
  const label = decision === "approve" ? "approve" : "reject";
  const answer = {
    authorization_id: id,
    decision,
    customer_message: decision === "approve" ? "Customer approved the purchase in the app." : "Customer declined the purchase in the app.",
    answered_at: new Date().toISOString(),
  };
  await api(`/step-ups/${encodeURIComponent(id)}/answer`, { method: "POST", body: JSON.stringify(answer) });
  showToast(`Purchase ${label}d. The runner has received your answer.`, "success");
  await loadApprovals();
}

function switchForUncertainty() {
  const switchEl = drawerRoot.querySelector("[data-action=toggle-uncertainty]");
  switchEl.setAttribute("aria-checked", switchEl.getAttribute("aria-checked") === "true" ? "false" : "true");
}

async function submitTighten() {
  if (!currentPolicy) throw new Error("The current mandate has not been loaded.");
  if (currentPolicy.mandate.status !== "active") throw new Error("Only an active mandate can be tightened.");
  const switchEl = drawerRoot.querySelector("[data-action=toggle-uncertainty]");
  const capText = drawerRoot.querySelector("#tighten-cap").value.trim();
  if (switchEl.getAttribute("aria-checked") === "true" && capText) throw new Error("Choose either the purchase cap or the stricter uncertainty setting. Save one change at a time.");
  if (switchEl.getAttribute("aria-checked") === "true") {
    if (currentPolicy.draft.uncertainty_policy === "decline") throw new Error("This mandate already declines uncertain purchases.");
    await api(`/mandates/${encodeURIComponent(currentPolicy.mandate.mandate_id)}/tighten`, { method: "POST", body: JSON.stringify({ uncertainty_policy: "decline" }) });
  } else {
    const input = drawerRoot.querySelector("#tighten-cap");
    const cap = Number(input.value);
    if (!Number.isFinite(cap) || cap <= 0) throw new Error("Enter a positive CHF purchase limit or turn on the stricter uncertainty setting.");
    const existingCaps = currentPolicy.draft.rules.filter((rule) => rule.field === "authorization.billing_amount_chf" && rule.scope === "purchase" && rule.operator === "<=").map((rule) => Number(rule.value));
    if (existingCaps.some((value) => !Number.isFinite(value))) throw new Error("The current purchase limit is invalid.");
    if (existingCaps.length && cap >= Math.min(...existingCaps)) throw new Error(`Enter a limit below the current CHF ${Math.min(...existingCaps)} cap.`);
    const rule = {
      field: "authorization.billing_amount_chf",
      operator: "<=",
      value: cap,
      currency: "CHF",
      scope: "purchase",
      source_text: `customer added a CHF ${cap} purchase limit`,
      plain_english: `The total charged amount must be CHF ${cap} or less.`,
    };
    await api(`/mandates/${encodeURIComponent(currentPolicy.mandate.mandate_id)}/tighten`, { method: "POST", body: JSON.stringify({ rules: [rule] }) });
  }
  drawerRoot.replaceChildren();
  showToast("Your policy was tightened.", "success");
  await renderPolicy();
}

async function revokeMandate() {
  if (!currentPolicy) throw new Error("The current mandate has not been loaded.");
  if (currentPolicy.mandate.status !== "active") throw new Error("Only an active mandate can be revoked.");
  await api(`/mandates/${encodeURIComponent(currentPolicy.mandate.mandate_id)}/revoke`, { method: "POST" });
  drawerRoot.replaceChildren();
  showToast("The mandate has been revoked.", "success");
  await renderPolicy();
}

document.addEventListener("click", async (event) => {
  const routeButton = event.target.closest("[data-route]");
  if (routeButton) {
    setActiveRoute(routeButton.dataset.route);
    return;
  }
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const action = button.dataset.action;
  try {
    if (action === "answer") {
      answers[button.dataset.question] = button.dataset.value;
      await renderReview();
    } else if (action === "confirm-draft") {
      button.disabled = true;
      await confirmDraft();
    } else if (action === "reject-draft") {
      await rejectDraft();
    } else if (action === "confirm-reject") {
      await api(`/drafts/${encodeURIComponent(activeDraft.draft_id)}/reject`, { method: "POST", body: JSON.stringify({ reason: "Rejected in the customer app." }) });
      drawerRoot.replaceChildren();
      showToast("The policy request was rejected.", "success");
      await renderReview();
    } else if (action === "answer-step-up") {
      button.disabled = true;
      submittingStepUps.add(button.dataset.id);
      try {
        await answerStepUp(button.dataset.id, button.dataset.decision);
      } finally {
        submittingStepUps.delete(button.dataset.id);
      }
    } else if (action === "open-decision") {
      await openDecision(button.dataset.id);
    } else if (action === "close-drawer") {
      if (event.target === button || button === event.target.closest(".close-button") || event.target.classList.contains("drawer-backdrop")) drawerRoot.replaceChildren();
    } else if (action === "open-tighten") {
      openTighten();
    } else if (action === "revoke-mandate") {
      openRevoke();
    } else if (action === "toggle-uncertainty") {
      switchForUncertainty();
    } else if (action === "submit-tighten") {
      button.disabled = true;
      await submitTighten();
    } else if (action === "confirm-revoke") {
      button.disabled = true;
      await revokeMandate();
    } else if (action === "show-policy-note") {
      showToast("The policy comes from the backend’s saved draft. The shopping agent cannot confirm or change it here.");
    }
  } catch (error) {
    showToast(error.message, "error");
    if (button.isConnected) button.disabled = false;
  }
});

window.addEventListener("hashchange", () => setActiveRoute(window.location.hash.slice(1)));
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && drawerRoot.childElementCount) drawerRoot.replaceChildren();
});

const initialRoute = window.location.hash.slice(1) || "review";
setActiveRoute(initialRoute);
