const API_BASE = "";
const MANDATE_SESSION_KEY = "viseca.demo.mandateId";
const screen = document.querySelector("#screen");
const drawerRoot = document.querySelector("#drawer-root");
const toastRoot = document.querySelector("#toast-root");
const pageContext = document.querySelector("#page-context");
const pageTitles = {
  home: "Home",
  review: "Review policy",
  approvals: "Approvals",
  policy: "Policy",
  activity: "Activity",
};

let currentRoute = "home";
let activeDraft = null;
let answers = {};
let pendingIds = new Set();
let pendingStepUps = new Map();
let submittingStepUps = new Set();
let approvalTimer = null;
let currentPolicy = null;
let currentDecisionPayload = null;
let currentUsername = null;
let screenSerial = 0;
let drawerSerial = 0;
let drawerTrigger = null;

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

function validateRules(rules, field) {
  if (!Array.isArray(rules)) throw new Error(`${field} must be a list.`);
  rules.forEach((rule, index) => {
    if (!rule || typeof rule !== "object") throw new Error(`${field}[${index}] must be an object.`);
    requireString(rule.field, `${field}[${index}].field`);
    requireString(rule.operator, `${field}[${index}].operator`);
    requireString(rule.source_text, `${field}[${index}].source_text`);
    requireString(rule.plain_english, `${field}[${index}].plain_english`);
    if (!(typeof rule.value === "number" || typeof rule.value === "string" || (Array.isArray(rule.value) && rule.value.every((item) => typeof item === "string")))) throw new Error(`${field}[${index}].value has an unsupported type.`);
    if (rule.scope === "period" && (!Number.isInteger(rule.period_days) || rule.period_days < 1)) throw new Error(`${field}[${index}].period_days must be a positive integer for a period rule.`);
  });
}

function validateDraft(draft) {
  if (!draft || typeof draft !== "object") throw new Error("The policy draft must be a JSON object.");
  requireString(draft.draft_id, "draft_id");
  requireString(draft.hash, "hash");
  requireString(draft.instruction, "instruction");
  requireString(draft.uncertainty_policy, "uncertainty_policy");
  requireString(draft.created_at, "created_at");
  if (!["ask", "decline", "approve"].includes(draft.uncertainty_policy)) throw new Error(`uncertainty_policy ${draft.uncertainty_policy} is not supported.`);
  if (!Number.isInteger(draft.version)) throw new Error("version must be an integer.");
  validateRules(draft.rules, "rules");
  if (!Array.isArray(draft.examples) || !Array.isArray(draft.open_questions)) throw new Error("examples and open_questions must be arrays.");
  draft.examples.forEach((example, index) => {
    requireString(example.description, `examples[${index}].description`);
    requireString(example.why, `examples[${index}].why`);
    if (!["approve", "decline", "step_up"].includes(example.expected)) throw new Error(`examples[${index}].expected has an unsupported outcome.`);
  });
  draft.open_questions.forEach((question, index) => {
    requireString(question.question, `open_questions[${index}].question`);
    if (!Array.isArray(question.options) || !question.options.length || !question.options.every((option) => typeof option === "string" && option.length)) throw new Error(`open_questions[${index}].options must be a non-empty string list.`);
    if (!Array.isArray(question.confirming_answers) || !question.confirming_answers.every((answer) => typeof answer === "string" && question.options.includes(answer))) throw new Error(`open_questions[${index}].confirming_answers must be a subset of options.`);
    if (question.answer !== null && typeof question.answer !== "string") throw new Error(`open_questions[${index}].answer must be a string or null.`);
    if (question.answer !== null && !question.options.includes(question.answer)) throw new Error(`open_questions[${index}].answer must be one of the listed options.`);
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
    credentials: "same-origin",
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

function linkedDraftId() {
  const query = new URLSearchParams(window.location.search);
  const draft = query.get("draft");
  const draftId = query.get("draft_id");
  if (draft && draftId && draft !== draftId) throw new Error("The draft and draft_id links refer to different policies.");
  return draft || draftId;
}

function showSession(username) {
  currentUsername = requireString(username, "Session.username");
  document.querySelector("#profile-name").textContent = currentUsername;
  const initials = currentUsername.slice(0, 2).toUpperCase();
  document.querySelector("#profile-avatar").textContent = initials;
  const topAvatar = document.querySelector("#top-avatar");
  topAvatar.textContent = initials;
  topAvatar.setAttribute("aria-label", currentUsername);
  document.querySelectorAll('[data-action="logout"]').forEach((button) => { button.hidden = false; });
}

function renderLogin() {
  currentUsername = null;
  if (approvalTimer) window.clearInterval(approvalTimer);
  approvalTimer = null;
  pageContext.textContent = "Demo sign in";
  document.querySelectorAll('[data-action="logout"]').forEach((button) => { button.hidden = true; });
  setScreen(`${heading("LOCAL DEMO ACCOUNT", "Sign in to your wallet.", "Enter a local username to review the policy your shopping agent proposed.")}
    <section class="card card-pad login-card"><label class="field-label" for="demo-username">Username<input id="demo-username" autocomplete="username" maxlength="80" required placeholder="Your name" /></label>
    <p class="helper-text">This demo uses a local username. It does not connect to your Viseca login.</p>
    <button class="button button-primary" type="button" data-action="login">Continue</button></section>`);
}

async function initialize() {
  try {
    const response = await fetch("/session", { credentials: "same-origin" });
    if (response.status === 401) {
      window.sessionStorage.removeItem(MANDATE_SESSION_KEY);
      renderLogin();
      return;
    }
    const session = await readJson(response, "GET /session");
    showSession(session.username);
    setActiveRoute(window.location.hash.slice(1) || (Boolean(linkedDraftId()) ? "review" : "home"));
  } catch (error) {
    setScreen(dataError("Your session could not be checked.", error));
  }
}

async function login() {
  const username = requireString(document.querySelector("#demo-username").value, "Username");
  const session = await api("/session", { method: "POST", body: JSON.stringify({ username }) });
  showSession(session.username);
  setActiveRoute(window.location.hash.slice(1) || (linkedDraftId() ? "review" : "home"));
}

async function logout() {
  await api("/session", { method: "DELETE" });
  window.sessionStorage.removeItem(MANDATE_SESSION_KEY);
  activeDraft = null;
  currentPolicy = null;
  currentDecisionPayload = null;
  answers = {};
  renderLogin();
}

function setActiveRoute(route) {
  if (!currentUsername) {
    renderLogin();
    return;
  }
  if (!pageTitles[route]) {
    screen.innerHTML = dataError("Page could not be opened.", new Error(`Unknown app route: ${route}`));
    screen.setAttribute("aria-busy", "false");
    return;
  }
  currentRoute = route;
  screenSerial += 1;
  drawerSerial += 1;
  currentDecisionPayload = null;
  if (window.location.hash !== `#${route}`) window.history.replaceState(null, "", `#${route}`);
  document.querySelectorAll("[data-route]").forEach((button) => {
    const active = button.dataset.route === route || (route === "review" && button.dataset.route === "home");
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

function ruleRows(rules = []) {
  const labels = {
    "authorization.billing_amount_chf": "Maximum purchase",
    "authorization.merchant.merchant_category": "Merchant",
    "facts.product_type": "Product",
    "facts.size": "Size",
    "facts.return_days": "Returns",
    "state.approvals_count": "Prior approved purchases",
  };
  return rules.map((rule) => {
    const label = labels[rule.field] || pretty(rule.field.split(".").at(-1));
    const comparison = rule.operator === "=" ? "" : rule.operator === "<=" ? "≤ " : rule.operator === ">=" ? "≥ " : `${rule.operator} `;
    const rawValue = Array.isArray(rule.value) ? rule.value.join(", ") : String(rule.value);
    const value = `${comparison}${rule.currency ? `${rule.currency} ` : ""}${rawValue.replaceAll("_", " ")}${rule.field === "facts.return_days" ? " days" : ""}`;
    return `<div class="permission-row"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
  }).join("");
}

function reviewSummary(draft) {
  const cap = draft.rules.filter((rule) => rule.scope === "purchase" && rule.field === "authorization.billing_amount_chf" && ["<", "<="].includes(rule.operator) && typeof rule.value === "number");
  const limit = cap.length ? Math.min(...cap.map((rule) => rule.value)) : null;
  const strictLimit = cap.some((rule) => rule.value === limit && rule.operator === "<");
  const product = draft.rules.find((rule) => rule.field === "facts.product_type" && rule.operator === "=");
  const size = draft.rules.find((rule) => rule.field === "facts.size" && rule.operator === "=");
  const summary = product ? String(product.value).replaceAll("_", " ") : draft.instruction;
  const specifics = size ? ` · ${String(size.value).replaceAll("_", " ")}` : "";
  const featured = new Set([product, size, ...cap].filter(Boolean));
  const rest = draft.rules.filter((rule) => !featured.has(rule));
  return `<section class="review-permission" aria-label="Proposed agent permission"><span class="review-permission-label">Agent permission</span><strong>${esc(summary)}${esc(specifics)}</strong><div class="review-permission-limit"><span>${limit === null ? "No per-purchase cap in this proposal" : esc(money(limit, "CHF"))}</span>${limit === null ? "" : `<small>${strictLimit ? "Strictly below this amount" : "Maximum per purchase"}</small>`}</div></section>
    ${rest.length ? `<div class="permission-list">${ruleRows(rest)}</div>` : ""}`;
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
    const needsRevision = selected && !question.confirming_answers.includes(selected);
    return `<div class="question-item"><div class="question-text"><span class="question-number">${index + 1}</span><span>${esc(question.question)}</span></div>
      <div class="choice-row" role="group" aria-label="${esc(question.question)}">
        ${question.options.map((option) => `<button class="choice-button ${selected === option ? "is-selected" : ""}" type="button" data-action="answer" data-question="${esc(question.question)}" data-value="${esc(option)}" aria-pressed="${selected === option}">${esc(answerLabel(option))}</button>`).join("")}
      </div>
      ${needsRevision ? `<p class="revision-note">This choice needs a revised policy before you can confirm.</p>` : ""}
    </div>`;
  }).join("");
}

function showExamples() {
  if (!activeDraft) throw new Error("There is no loaded policy draft to inspect.");
  drawerSerial += 1;
  drawerRoot.innerHTML = `<div class="drawer-backdrop" data-action="close-drawer"><aside class="drawer" role="dialog" aria-modal="true" aria-label="Policy examples" tabindex="-1"><div class="drawer-header"><h2>Test this policy</h2><button class="close-button" type="button" aria-label="Close examples" data-action="close-drawer">×</button></div><div class="example-grid">${exampleCards(activeDraft.examples)}</div></aside></div>`;
  drawerRoot.querySelector(".drawer").focus();
}

function showRuleDetails() {
  const rules = currentRoute === "policy" ? currentPolicy?.effective_policy.rules : activeDraft?.rules;
  if (!rules) throw new Error("Policy rules have not been loaded.");
  drawerSerial += 1;
  drawerRoot.innerHTML = `<div class="drawer-backdrop" data-action="close-drawer"><aside class="drawer" role="dialog" aria-modal="true" aria-label="Policy rule details" tabindex="-1"><div class="drawer-header"><h2>Rule details</h2><button class="close-button" type="button" aria-label="Close rule details" data-action="close-drawer">×</button></div>${rules.map((rule) => `<section class="drawer-section"><h3>${esc(rule.plain_english)}</h3><p class="section-subtitle">From your request: <mark>${esc(rule.source_text)}</mark></p><small>${esc(rule.field)} ${esc(rule.operator)} ${esc(Array.isArray(rule.value) ? rule.value.join(", ") : rule.value)}</small></section>`).join("")}</aside></div>`;
  drawerRoot.querySelector(".drawer").focus();
}

async function loadDraft() {
  const draftId = linkedDraftId();
  requireString(draftId, "URL query parameter draft or draft_id");
  return api(`/drafts/${encodeURIComponent(draftId)}`);
}

async function renderReview() {
  const serial = ++screenSerial;
  try {
    const selectedAnswers = { ...answers };
    const draft = validateDraft(await loadDraft());
    if (serial !== screenSerial || currentRoute !== "review") return;
    activeDraft = draft;
    answers = {};
    draft.open_questions.forEach((question) => {
      if (question.answer !== null && question.answer !== undefined) answers[question.question] = question.answer;
    });
    Object.keys(selectedAnswers).forEach((question) => {
      if (draft.open_questions.some((item) => item.question === question)) answers[question] = selectedAnswers[question];
    });
    const unanswered = draft.open_questions.filter((question) => !answers[question.question]).length;
    const needsRevision = draft.open_questions.filter((question) => answers[question.question] && !question.confirming_answers.includes(answers[question.question])).length;
    setScreen(`${heading("WALLET", "New agent permission", "You approve these limits.")}
      <div class="review-layout">
        <section class="review-card">
          ${reviewSummary(draft)}
          <details class="request-details"><summary>Original request</summary><p>${esc(draft.instruction)}</p></details>
          <div class="review-links"><button type="button" data-action="show-rule-details">All rules · v${esc(draft.version)}</button><button type="button" data-action="show-examples">Test this policy</button></div>
        </section>
        ${draft.open_questions.length ? `<section class="review-card"><div class="section-head"><h2 class="section-title">${draft.open_questions.length} detail${draft.open_questions.length === 1 ? "" : "s"} to confirm</h2><span class="small-meta">${unanswered ? `${unanswered} unanswered` : needsRevision ? "Needs revision" : "Ready"}</span></div><div class="question-list">${questionCards(draft.open_questions)}</div></section>` : ""}
        <div class="review-actions">${needsRevision ? "" : `<span class="actions-note">Only this Wallet can authorize the saved policy.</span>`}<div class="button-row"><button type="button" class="button button-quiet" data-action="reject-draft">Reject</button><button type="button" class="button button-primary" data-action="confirm-draft" ${unanswered || needsRevision ? "disabled" : ""}>Authorize agent</button></div></div>
      </div>`);
  } catch (error) {
    if (serial === screenSerial && currentRoute === "review") setScreen(`${heading("POLICY REQUEST", "Make sure it feels right.", "Review the policy saved by your shopping agent.")}${dataError("The policy draft could not be loaded.", error)}`);
    else showToast(`A previous policy load failed: ${error.message}`, "error");
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
  if (!Array.isArray(decision.evidence)) throw new Error(`StepUp ${stepUp.authorization_id} has no decision evidence.`);
  const labels = {
    "authorization.billing_amount_chf": "Amount", "facts.product_type": "Product", "facts.size": "Size", "facts.return_days": "Return window",
    "authorization.merchant.merchant_category": "Merchant", "state.approvals_count": "Purchase count",
  };
  const checks = [...decision.evidence];
  const priority = { fail: 0, uncertain: 1, pass: 2 };
  checks.forEach((check) => {
    requireString(check.name, "StepUp Check.name");
    if (!Object.hasOwn(priority, check.result)) throw new Error(`StepUp check result ${check.result} is unsupported.`);
  });
  checks.sort((a, b) => priority[a.result] - priority[b.result]);
  const preview = checks.slice(0, 4).map((check) => {
    const field = check.name.startsWith("rule ") ? check.name.slice(5).split(" ")[0] : check.name;
    const label = labels[field] || pretty(field.split(".").at(-1));
    const status = check.result === "pass" ? "Passed" : check.result === "fail" ? "Failed" : "Unknown";
    return `<li><span class="approval-check-mark ${esc(check.result)}" aria-hidden="true">${check.result === "pass" ? "✓" : check.result === "fail" ? "×" : "?"}</span><span>${esc(label)}</span><strong>${status}</strong></li>`;
  }).join("");
  return `<article class="approval-card">
    <div class="approval-topline"><span>${esc(remaining)}</span><span>Needs your decision</span></div>
    <div class="approval-purchase"><span>${esc(merchant.merchant_name)}</span><strong>${esc(money(amount, "CHF"))}</strong><p>${esc(purchase)}</p></div>
    <div class="approval-checks"><h2>Checked against your wallet</h2><ul>${preview}</ul><p>${esc(decision.customer_message)}</p><button class="section-link" type="button" data-action="show-step-up-details" data-id="${esc(stepUp.authorization_id)}">Why?</button></div>
    <p class="approval-binding">Your answer applies only to this exact purchase.</p>
    <div class="approval-actions"><button class="button button-secondary" type="button" data-action="answer-step-up" data-id="${esc(stepUp.authorization_id)}" data-decision="decline" ${left <= 0 || submittingStepUps.has(stepUp.authorization_id) ? "disabled" : ""}>Decline</button><button class="button button-primary" type="button" data-action="answer-step-up" data-id="${esc(stepUp.authorization_id)}" data-decision="approve" ${left <= 0 || submittingStepUps.has(stepUp.authorization_id) ? "disabled" : ""}>Approve once</button></div>
  </article>`;
}

function showStepUpDetails(id) {
  const stepUp = pendingStepUps.get(id);
  if (!stepUp) throw new Error(`Pending purchase ${id} is no longer available.`);
  if (!Array.isArray(stepUp.decision.evidence)) throw new Error(`StepUp ${id} has no evidence list.`);
  drawerSerial += 1;
  const checks = stepUp.decision.evidence.map((check, index) => {
    requireString(check.name, `StepUp.evidence[${index}].name`);
    requireString(check.source, `StepUp.evidence[${index}].source`);
    return `<div class="check-row"><span class="check-copy"><strong>${esc(pretty(check.name))}</strong><small>${esc(check.note)}</small><small>Value: ${check.value === null ? "unknown" : esc(check.value)} · Source: ${esc(check.source)}</small></span><span class="check-result ${esc(check.result)}">${esc(check.result)}</span></div>`;
  }).join("");
  const details = stepUp.event.authorization.items.map((item) => esc(item.item_details)).join("\n");
  drawerRoot.innerHTML = `<div class="drawer-backdrop" data-action="close-drawer"><aside class="drawer" role="dialog" aria-modal="true" aria-label="Why this purchase needs approval" tabindex="-1"><div class="drawer-header"><div><h2>Why we paused</h2><p>${esc(stepUp.authorization_id)}</p></div><button class="close-button" type="button" aria-label="Close details" data-action="close-drawer">×</button></div><section class="drawer-section"><p>${esc(stepUp.decision.customer_message)}</p></section><section class="drawer-section"><h3>Wallet checks</h3>${checks}</section><details class="drawer-section"><summary>Merchant-supplied text · untrusted</summary><div class="event-copy">${details}</div></details><details class="drawer-section"><summary>Raw authorization event</summary><pre class="event-json">${esc(JSON.stringify(stepUp.event, null, 2))}</pre></details></aside></div>`;
  drawerRoot.querySelector(".drawer").focus();
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
    pendingStepUps = new Map(requests.map((item) => [item.authorization_id, item]));
    document.querySelector("#approval-count").textContent = requests.length ? String(requests.length) : "0";
    container.innerHTML = requests.length ? `<div class="list-stack">${requests.map(stepUpCard).join("")}</div>` : `<section class="wallet-empty"><h2>No approvals waiting</h2><p>Purchases that need your decision will appear here.</p></section>`;
    if (errorContainer) errorContainer.innerHTML = removed.length ? expiredNote(removed.length) : "";
  } catch (error) {
    if (!container.isConnected) {
      showToast(`A previous approval refresh failed: ${error.message}`, "error");
      return;
    }
    document.querySelector("#approval-count").textContent = "—";
    container.replaceChildren();
    if (errorContainer) errorContainer.innerHTML = dataError("Pending approvals could not be refreshed.", error);
    else container.innerHTML = dataError("Pending approvals could not be loaded.", error);
  }
}

async function renderApprovals() {
  setScreen(`${heading("PURCHASE CHECKS", "Approvals", "Review each purchase before it expires.")}
    <div class="approvals-layout"><div id="approvals-error"></div><div id="approvals-list"><div class="loading-panel"><span class="spinner" aria-hidden="true"></span><span>Checking for pending purchases…</span></div></div></div>`);
  const container = document.querySelector("#approvals-list");
  await loadApprovals();
  if (container.isConnected && currentRoute === "approvals") approvalTimer = window.setInterval(() => loadApprovals(), 2000);
}

function noMandate() {
  const hasDraft = Boolean(linkedDraftId());
  return `<section class="wallet-empty"><h2>No agent wallet yet</h2><p>Your shopping agent can send a policy draft for you to review. Only your confirmation activates it.</p>${hasDraft ? `<button class="button button-primary" type="button" data-route="review">Review policy</button>` : ""}</section>`;
}

function formatRuleValue(rule) {
  const value = Array.isArray(rule.value) ? rule.value.join(", ") : rule.value;
  return `${esc(rule.operator)} ${rule.currency ? `${esc(rule.currency)} ` : ""}${esc(value)}`;
}

function ruleViews(rules = []) {
  return rules.map((rule) => `<div class="rule-view-row"><div><strong>${esc(rule.plain_english)}</strong><small>From your request: ${esc(rule.source_text)}</small></div><span class="rule-value">${formatRuleValue(rule)}</span></div>`).join("");
}

function getPayloadParts(payload) {
  if (!payload || !payload.mandate || !payload.draft || !payload.effective_policy || !payload.state) throw new Error("GET /mandates/{mandate_id} must return { mandate, draft, effective_policy, state }.");
  requireString(payload.mandate.mandate_id, "Mandate.mandate_id");
  requireString(payload.mandate.status, "Mandate.status");
  if (!["active", "revoked", "expired", "superseded"].includes(payload.mandate.status)) throw new Error(`Mandate.status ${payload.mandate.status} is not supported.`);
  requireString(payload.mandate.confirmed_at, "Mandate.confirmed_at");
  if (!Number.isFinite(new Date(payload.mandate.confirmed_at).getTime())) throw new Error("Mandate.confirmed_at is not a valid timestamp.");
  if (!Number.isInteger(payload.mandate.version)) throw new Error("Mandate.version must be an integer.");
  validateDraft(payload.draft);
  validateRules(payload.effective_policy.rules, "effective_policy.rules");
  if (!["ask", "decline", "approve"].includes(payload.effective_policy.uncertainty_policy)) throw new Error("effective_policy.uncertainty_policy is unsupported.");
  if (payload.state.mandate_id !== payload.mandate.mandate_id) throw new Error("MandateState.mandate_id does not match Mandate.mandate_id.");
  if (!Array.isArray(payload.state.approvals)) throw new Error("MandateState.approvals must be a list.");
  payload.state.approvals.forEach((approval, index) => {
    requireString(approval.authorization_id, `state.approvals[${index}].authorization_id`);
    requireString(approval.timestamp, `state.approvals[${index}].timestamp`);
    if (!Number.isFinite(new Date(approval.timestamp).getTime())) throw new Error(`state.approvals[${index}].timestamp is invalid.`);
    if (typeof approval.amount_chf !== "number" || !Number.isFinite(approval.amount_chf)) throw new Error(`state.approvals[${index}].amount_chf is invalid.`);
  });
  return { mandate: payload.mandate, draft: payload.draft, effective_policy: payload.effective_policy, state: payload.state };
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

async function renderHome() {
  const serial = ++screenSerial;
  const id = mandateId();
  if (!id) {
    if (Boolean(linkedDraftId())) {
      setActiveRoute("review");
      return;
    }
    setScreen(`${heading("YOUR WALLET", "Agent wallet", "Your agent needs a policy you have confirmed.")}${noMandate()}`);
    return;
  }
  setScreen(`${heading("YOUR WALLET", "Agent wallet", "Your current permissions and recent purchases.")}<div class="loading-panel"><span class="spinner" aria-hidden="true"></span><span>Loading wallet…</span></div>`);
  try {
    const [payload, entries] = await Promise.all([
      api(`/mandates/${encodeURIComponent(id)}`),
      api(`/mandates/${encodeURIComponent(id)}/decisions`),
    ]);
    const { mandate, draft, effective_policy, state } = getPayloadParts(payload);
    if (!Array.isArray(entries)) throw new Error("GET /mandates/{mandate_id}/decisions must return a list.");
    if (serial !== screenSerial || currentRoute !== "home") return;
    const caps = effective_policy.rules.filter((rule) => rule.field === "authorization.billing_amount_chf" && rule.scope === "purchase" && ["<", "<="].includes(rule.operator) && typeof rule.value === "number");
    const limit = caps.length ? Math.min(...caps.map((rule) => rule.value)) : null;
    const product = effective_policy.rules.find((rule) => rule.field === "facts.product_type");
    const size = effective_policy.rules.find((rule) => rule.field === "facts.size");
    const merchant = effective_policy.rules.find((rule) => rule.field === "authorization.merchant.merchant_category");
    const returns = effective_policy.rules.find((rule) => rule.field === "facts.return_days");
    const description = product ? String(product.value).replaceAll("_", " ") : draft.instruction;
    const details = [size ? `Size ${size.value}` : null, merchant ? String(merchant.value).replaceAll("_", " ") : null, returns ? `Returns ${returns.operator} ${returns.value} days` : null].filter((value) => value !== null);
    const spend = state.approvals.reduce((sum, approval) => sum + approval.amount_chf, 0);
    const recent = [...entries].reverse().slice(0, 3);
    recent.forEach((entry, index) => {
      if (!entry || !entry.decision || !entry.state_after) throw new Error(`History entry ${index} must include decision and state_after.`);
      requireString(entry.decision.customer_message, `Decision ${index}.customer_message`);
      requireString(entry.decision.authorization_id, `Decision ${index}.authorization_id`);
      outcomePill(entry.decision.decision);
    });
    const active = mandate.status === "active";
    setScreen(`${heading("YOUR WALLET", "Agent wallet", "Your agent's current purchase limits.")}
      <div class="wallet-layout">
        <section class="wallet-surface" aria-label="Agent wallet permissions"><div class="wallet-surface-top"><span>Maximum purchase</span><span class="wallet-status ${active ? "is-active" : ""}"><i aria-hidden="true"></i>${esc(pretty(mandate.status))}</span></div>
          <strong class="wallet-limit ${limit === null ? "is-unset" : ""}">${limit === null ? "No purchase cap" : esc(money(limit, "CHF"))}</strong>
          <div class="wallet-permissions"><strong>${esc(description)}</strong>${details.length ? `<p>${details.map(esc).join(" · ")}</p>` : ""}</div>
          <div class="wallet-spend"><span>Approved spend</span><strong>${esc(money(spend, "CHF"))}</strong><span>Approved purchases</span><strong>${state.approvals.length}</strong></div>
        </section>
        <section class="wallet-activity"><div class="section-head"><h2>Recent activity</h2><button class="section-link" type="button" data-route="activity">View all</button></div>
          ${recent.length ? `<div class="activity-rows">${recent.map((entry) => `<button class="activity-row" type="button" data-action="open-decision" data-id="${esc(entry.decision.authorization_id)}"><span class="activity-outcome" aria-label="${esc(pretty(entry.decision.decision))}">${entry.decision.decision === "approve" ? "✓" : entry.decision.decision === "decline" ? "×" : "?"}</span><span><strong>${esc(pretty(entry.decision.decision))}</strong><small>${esc(entry.decision.customer_message)}</small></span><span aria-hidden="true">›</span></button>`).join("")}</div>` : `<p class="wallet-empty-inline">No purchases yet. Decisions will appear here when your agent tries to buy something.</p>`}
        </section>
      </div>`);
  } catch (error) {
    if (serial === screenSerial && currentRoute === "home") setScreen(`${heading("YOUR WALLET", "Agent wallet", "Your current permissions and recent purchases.")}${dataError("Your wallet could not be loaded.", error)}`);
    else showToast(`A previous wallet load failed: ${error.message}`, "error");
  }
}

async function renderPolicy() {
  const serial = ++screenSerial;
  const id = mandateId();
  if (!id) {
    setScreen(`${heading("YOUR WALLET", "Your policy, in your hands.", "See what your shopping agent can do and narrow the rules whenever you like.")}${noMandate()}`);
    return;
  }
  setScreen(`${heading("YOUR WALLET", "Your policy, in your hands.", "See what your shopping agent can do and narrow the rules whenever you like.")}<div class="loading-panel"><span class="spinner" aria-hidden="true"></span><span>Loading your mandate…</span></div>`);
  try {
    const { mandate, draft, effective_policy, state } = getPayloadParts(await api(`/mandates/${encodeURIComponent(id)}`));
    if (serial !== screenSerial || currentRoute !== "policy") return;
    currentPolicy = { mandate, draft, effective_policy, state };
    const approvals = state.approvals;
    const isActive = mandate.status === "active";
    const approvedSpend = approvals.reduce((sum, approval) => sum + approval.amount_chf, 0);
    setScreen(`${heading("YOUR WALLET", "Agent permissions", "Confirmed ${esc(new Date(mandate.confirmed_at).toLocaleDateString())} · version ${esc(mandate.version)}", `<span class="wallet-status ${isActive ? "is-active" : ""}"><i aria-hidden="true"></i>${esc(pretty(mandate.status))}</span>`)}
      <div class="policy-layout">
        <section class="policy-surface"><div class="permission-list">${ruleRows(effective_policy.rules)}<div class="permission-row"><span>Uncertainty</span><strong>${esc(pretty(effective_policy.uncertainty_policy))}</strong></div></div><button class="section-link" type="button" data-action="show-rule-details">Rule details</button></section>
        <div class="policy-summary"><span>Approved spend</span><strong>${esc(money(approvedSpend, "CHF"))}</strong><span>Purchases approved</span><strong>${approvals.length}</strong></div>
        <section class="policy-controls"><h2>Change permissions</h2><button class="button button-secondary" type="button" data-action="open-tighten" ${isActive && effective_policy.uncertainty_policy !== "decline" ? "" : "disabled"}>Decline uncertain purchases</button><button class="policy-revoke" type="button" data-action="revoke-mandate" ${isActive ? "" : "disabled"}>Revoke access</button><p>New rule limits are unavailable while the simulator rejects rule additions.</p></section>
      </div>`);
  } catch (error) {
    if (serial === screenSerial && currentRoute === "policy") setScreen(`${heading("YOUR WALLET", "Your policy, in your hands.", "See what your shopping agent can do and narrow the rules whenever you like.")}${dataError("Your mandate could not be loaded.", error)}`);
    else showToast(`A previous mandate load failed: ${error.message}`, "error");
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
  const serial = ++screenSerial;
  const id = mandateId();
  if (!id) {
    setScreen(`${heading("PURCHASE HISTORY", "Activity", "Your agent's purchase decisions.")}${noMandate()}`);
    return;
  }
  setScreen(`${heading("PURCHASE HISTORY", "Activity", "Your agent's purchase decisions.")}<div class="loading-panel"><span class="spinner" aria-hidden="true"></span><span>Loading recent decisions…</span></div>`);
  try {
    const decisions = await api(`/mandates/${encodeURIComponent(id)}/decisions`);
    if (serial !== screenSerial || currentRoute !== "activity") return;
    if (!Array.isArray(decisions)) throw new Error("GET /mandates/{mandate_id}/decisions must return a list.");
    if (!decisions.length) {
      setScreen(`${heading("PURCHASE HISTORY", "Activity", "Your agent's purchase decisions.")}<section class="wallet-empty"><h2>No purchases yet</h2><p>Your agent's purchase decisions will appear here.</p></section>`);
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
    setScreen(`${heading("PURCHASE HISTORY", "Activity", "Select a purchase to see its decision.")}
      <section class="history-list"><div class="section-head"><h2>${decisions.length} decision${decisions.length === 1 ? "" : "s"}</h2></div><div class="activity-rows">${[...decisions].reverse().map((entry) => {
      const decision = entry.decision;
      const label = decision.decision === "approve" ? "Approved" : decision.decision === "decline" ? "Blocked" : "Needs you";
      const symbol = decision.decision === "approve" ? "✓" : decision.decision === "decline" ? "×" : "?";
      return `<button class="activity-row history-row" type="button" data-action="open-decision" data-id="${esc(decision.authorization_id)}"><span class="activity-outcome" aria-hidden="true">${symbol}</span><span><strong>${label}</strong><small>${esc(decision.customer_message)}</small></span><time class="activity-time" datetime="${esc(decision.decided_at)}">${esc(timeLabel(decision.decided_at))}</time></button>`;
      }).join("")}</div></section>`);
  } catch (error) {
    if (serial === screenSerial && currentRoute === "activity") setScreen(`${heading("PURCHASE HISTORY", "Activity", "Your agent's purchase decisions.")}${dataError("Purchase history could not be loaded.", error)}`);
    else showToast(`A previous history load failed: ${error.message}`, "error");
  }
}

function renderCustomerDecision(payload) {
  const { decision, event } = payload;
  const auth = event.authorization;
  const merchant = requireString(auth.merchant.merchant_name, "Decision merchant");
  const item = requireString(auth.items[0].item_name, "Decision item name");
  const outcome = decision.decision === "approve" ? "Approved" : decision.decision === "decline" ? "Blocked" : "Needs you";
  const alerts = decision.evidence.filter((check) => check.result !== "pass").slice(0, 3);
  drawerRoot.innerHTML = `<div class="drawer-backdrop" data-action="close-drawer"><aside class="drawer decision-drawer" role="dialog" aria-modal="true" aria-label="Purchase decision" tabindex="-1">
    <div class="drawer-header"><div><span class="eyebrow">PURCHASE DECISION</span><h2>${outcome}</h2></div><button class="close-button" type="button" aria-label="Close decision" data-action="close-drawer">×</button></div>
    <div class="decision-purchase"><strong>${esc(money(auth.billing_amount_chf, "CHF"))}</strong><p>${esc(merchant)} · ${esc(item)}</p></div>
    <p class="decision-message">${esc(decision.customer_message)}</p>
    ${alerts.length ? `<div class="decision-alerts">${alerts.map((check) => `<div><span aria-hidden="true">${check.result === "fail" ? "×" : "?"}</span><span>${esc(pretty(check.name))}</span></div>`).join("")}</div>` : ""}
    <button class="button button-secondary" type="button" data-action="inspect-decision">Inspect decision</button>
  </aside></div>`;
  drawerRoot.querySelector(".drawer").focus();
}

function renderDebugger(payload, tab = "decision") {
  const tabs = ["decision", "policy", "evidence", "state", "security", "raw"];
  if (!tabs.includes(tab)) throw new Error(`Unknown debugger tab: ${tab}`);
  const { decision, event, state_before, state_after } = payload;
  const auth = event.authorization;
  const securityReasons = new Set(["injected_instructions", "unrequested_item", "protection_plan", "gift_card", "subscription", "duplicate_order", "velocity", "new_device", "unfamiliar_merchant", "lookalike_merchant", "country_blocked"]);
  const securityCodes = decision.reason_codes.filter((code) => securityReasons.has(code));
  const checkRows = decision.evidence.map((check) => `<div class="debug-row"><span><strong>${esc(pretty(check.name))}</strong><small>${esc(check.note)}</small></span><span class="debug-result ${esc(check.result)}">${esc(check.result)}</span></div>`).join("");
  const sections = {
    decision: `<div class="debug-metadata"><span>Outcome</span><strong>${esc(pretty(decision.decision))}</strong><span>Latency</span><strong>${esc(decision.elapsed_ms)} ms</strong><span>Policy</span><strong>v${esc(decision.mandate_version)}</strong><span>Receipt</span><strong>${esc(decision.authorization_id)}</strong></div><h3>Rule evaluation</h3>${checkRows}`,
    policy: `<p class="debug-copy">${esc(event.mandate.instruction)}</p><h3>Confirmed rules</h3>${event.mandate.hard_rules.map((rule) => `<div class="debug-row"><span>${esc(rule.field)}</span><strong>${esc(rule.operator)} ${esc(Array.isArray(rule.value) ? rule.value.join(", ") : rule.value)}</strong></div>`).join("")}`,
    evidence: `<h3>Evidence and provenance</h3>${decision.evidence.map((check) => `<div class="debug-row"><span><strong>${esc(pretty(check.name))}</strong><small>${esc(check.note)}</small><small>Value: ${check.value === null ? "unknown" : esc(check.value)}</small></span><strong>${esc(check.source)}</strong></div>`).join("")}`,
    state: `<h3>State before</h3><pre class="event-json">${esc(JSON.stringify(state_before, null, 2))}</pre><h3>State after</h3><pre class="event-json">${esc(JSON.stringify(state_after, null, 2))}</pre>`,
    security: `<h3>Authorized intent</h3><p class="debug-copy">${esc(event.mandate.instruction)}</p><h3>Proposed purchase</h3><p class="debug-copy">${esc(auth.items.map((item) => item.item_name).join(" + "))} · ${esc(money(auth.billing_amount_chf, "CHF"))}</p><h3>Security signals</h3><p class="debug-copy">${esc(securityCodes.length ? securityCodes.map(pretty).join(", ") : "No security-specific reason code recorded")}</p><details><summary>Merchant-supplied text · untrusted</summary>${auth.items.filter((item) => item.item_details).map((item) => `<p class="event-copy">${esc(item.item_details.slice(0, 120))}${item.item_details.length > 120 ? "…" : ""}</p>`).join("")}</details>`,
    raw: `<h3>Raw records</h3><details><summary>Authorization Event</summary><pre class="event-json">${esc(JSON.stringify(event, null, 2))}</pre></details><details><summary>Decision</summary><pre class="event-json">${esc(JSON.stringify(decision, null, 2))}</pre></details><details><summary>State</summary><pre class="event-json">${esc(JSON.stringify({ before: state_before, after: state_after }, null, 2))}</pre></details>`,
  };
  drawerRoot.innerHTML = `<div class="drawer-backdrop" data-action="close-drawer"><aside class="drawer debugger-drawer" role="dialog" aria-modal="true" aria-label="Decision inspector" tabindex="-1">
    <div class="drawer-header"><div><span class="eyebrow">INSPECTOR</span><h2>Decision inspector</h2><p>${esc(auth.merchant.merchant_name)} · ${esc(money(auth.billing_amount_chf, "CHF"))}</p></div><button class="close-button" type="button" aria-label="Close inspector" data-action="close-drawer">×</button></div>
    <nav class="debug-tabs" role="tablist" aria-label="Inspector sections">${tabs.map((name) => `<button type="button" role="tab" id="inspector-tab-${name}" aria-controls="inspector-panel" aria-selected="${name === tab}" tabindex="${name === tab ? "0" : "-1"}" data-action="debug-tab" data-tab="${name}" ${name === tab ? 'aria-current="page"' : ""}>${esc(pretty(name))}</button>`).join("")}</nav>
    <div class="debug-content" id="inspector-panel" role="tabpanel" aria-labelledby="inspector-tab-${tab}" tabindex="0">${sections[tab]}</div>
  </aside></div>`;
  drawerRoot.querySelector(".drawer").focus();
}

async function openDecision(id) {
  const serial = ++drawerSerial;
  drawerRoot.innerHTML = `<div class="drawer-backdrop" data-action="close-drawer"><aside class="drawer" role="dialog" aria-modal="true" aria-label="Decision evidence"><div class="loading-panel"><span class="spinner" aria-hidden="true"></span><span>Loading decision evidence…</span></div></aside></div>`;
  try {
    const payload = await api(`/decisions/${encodeURIComponent(id)}`);
    if (serial !== drawerSerial) return;
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
    event.authorization.items.forEach((item, index) => {
      if (typeof item.item_details !== "string") throw new Error(`Event.authorization.items[${index}].item_details must be a string.`);
    });
    decision.evidence.forEach((check, index) => {
      requireString(check.name, `Decision.evidence[${index}].name`);
      requireString(check.source, `Decision.evidence[${index}].source`);
      if (typeof check.note !== "string" || !["pass", "fail", "uncertain"].includes(check.result) || !("value" in check)) throw new Error(`Decision.evidence[${index}] is invalid.`);
    });
    currentDecisionPayload = payload;
    renderCustomerDecision(payload);
  } catch (error) {
    if (serial === drawerSerial) drawerRoot.innerHTML = `<div class="drawer-backdrop" data-action="close-drawer"><aside class="drawer" role="dialog" aria-modal="true" aria-label="Decision evidence"><div class="drawer-header"><div><span class="eyebrow"><i class="eyebrow-mark"></i>DECISION RECORD</span><h2>Evidence unavailable</h2></div><button class="close-button" type="button" aria-label="Close evidence" data-action="close-drawer">×</button></div>${dataError("The decision record could not be loaded.", error)}</aside></div>`;
    else showToast(`A previous decision load failed: ${error.message}`, "error");
  }
}

async function renderRoute(route) {
  if (route === "home") return renderHome();
  if (route === "review") return renderReview();
  if (route === "approvals") return renderApprovals();
  if (route === "policy") return renderPolicy();
  if (route === "activity") return renderActivity();
  throw new Error(`Unknown app route: ${route}`);
}

function modal(title, body, primaryLabel, action, danger = false) {
  drawerSerial += 1;
  drawerRoot.innerHTML = `<div class="drawer-backdrop" data-action="close-drawer"><section class="drawer" role="dialog" aria-modal="true" aria-label="${esc(title)}" style="height:auto;max-height:min(90vh,700px);align-self:center;margin:auto 18px;overflow:auto;border-radius:17px"><div class="drawer-header"><div><span class="eyebrow"><i class="eyebrow-mark"></i>YOUR WALLET</span><h2>${esc(title)}</h2></div><button class="close-button" type="button" aria-label="Close" data-action="close-drawer">×</button></div><div>${body}</div><div class="button-row" style="justify-content:flex-end;margin-top:18px"><button class="button button-secondary" type="button" data-action="close-drawer">Cancel</button><button class="button ${danger ? "button-danger" : "button-primary"}" type="button" data-action="${esc(action)}">${esc(primaryLabel)}</button></div></section></div>`;
  drawerRoot.querySelector("[role=dialog]").focus();
}

function openTighten() {
  if (!currentPolicy || currentPolicy.mandate.status !== "active") throw new Error("Only an active mandate can be tightened.");
  if (currentPolicy.effective_policy.uncertainty_policy === "decline") throw new Error("This mandate already declines uncertain purchases.");
  modal("Decline uncertain purchases?", `<p class="section-subtitle">Purchases with missing information will be declined instead of sent to you for approval. This affects future purchases.</p>`, "Decline uncertainty", "submit-tighten");
}

function openRevoke() {
  modal("Revoke this mandate?", `<p class="section-subtitle">The shopping agent will no longer be able to use this mandate. This action cannot be undone in the app.</p>`, "Revoke mandate", "confirm-revoke", true);
}

async function confirmDraft() {
  if (!activeDraft) throw new Error("There is no loaded draft to confirm.");
  const missing = activeDraft.open_questions.filter((question) => !(answers[question.question] ?? question.answer));
  if (missing.length) throw new Error("Answer every open question before confirming this draft.");
  const needsRevision = activeDraft.open_questions.some((question) => !question.confirming_answers.includes(answers[question.question] ?? question.answer));
  if (needsRevision) throw new Error("A selected answer needs a revised policy. Ask your shopping agent to update the draft before confirming.");
  const body = {
    version: activeDraft.version,
    hash: activeDraft.hash,
    answers: Object.fromEntries(activeDraft.open_questions.map((question) => [question.question, answers[question.question] ?? question.answer])),
  };
  try {
    const mandate = await api(`/drafts/${encodeURIComponent(activeDraft.draft_id)}/confirm`, { method: "POST", body: JSON.stringify(body) });
    requireString(mandate && mandate.mandate_id, "Policy confirmation response mandate_id");
    window.sessionStorage.setItem(MANDATE_SESSION_KEY, mandate.mandate_id);
    setScreen(`<section class="authorization-complete" role="status"><span class="complete-mark" aria-hidden="true">✓</span><p>Viseca Wallet</p><h1>Agent authorized</h1><span>Policy v${esc(activeDraft.version)} · your limits are active</span></section>`);
    const serial = screenSerial;
    window.setTimeout(() => {
      if (serial === screenSerial && currentRoute === "review") setActiveRoute("home");
    }, 850);
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
  const pending = pendingStepUps.get(id);
  if (!pending) throw new Error(`Purchase ${id} is no longer pending.`);
  const answer = {
    authorization_id: id,
    decision,
    customer_message: decision === "approve" ? "Customer approved the purchase in the app." : "Customer declined the purchase in the app.",
    answered_at: new Date().toISOString(),
  };
  await api(`/step-ups/${encodeURIComponent(id)}/answer`, { method: "POST", body: JSON.stringify(answer) });
  const merchant = requireString(pending.event.authorization.merchant.merchant_name, "Pending purchase merchant");
  showToast(`${decision === "approve" ? "Approved" : "Declined"} for this purchase: ${money(pending.event.authorization.billing_amount_chf, "CHF")} at ${merchant}.`, "success");
  await loadApprovals();
}

async function submitTighten() {
  if (!currentPolicy) throw new Error("The current mandate has not been loaded.");
  if (currentPolicy.mandate.status !== "active") throw new Error("Only an active mandate can be tightened.");
  if (currentPolicy.effective_policy.uncertainty_policy === "decline") throw new Error("This mandate already declines uncertain purchases.");
  await api(`/mandates/${encodeURIComponent(currentPolicy.mandate.mandate_id)}/tighten`, { method: "POST", body: JSON.stringify({ uncertainty_policy: "decline" }) });
  drawerRoot.replaceChildren();
  showToast("Uncertain purchases will now be declined.", "success");
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
  if (!drawerRoot.childElementCount) drawerTrigger = button;
  try {
    if (action === "login") {
      button.disabled = true;
      await login();
    } else if (action === "logout") {
      button.disabled = true;
      await logout();
    } else if (action === "answer") {
      answers[button.dataset.question] = button.dataset.value;
      await renderReview();
    } else if (action === "confirm-draft") {
      button.disabled = true;
      await confirmDraft();
    } else if (action === "reject-draft") {
      await rejectDraft();
    } else if (action === "confirm-reject") {
      if (!activeDraft) throw new Error("There is no loaded draft to reject.");
      try {
        await api(`/drafts/${encodeURIComponent(activeDraft.draft_id)}/reject`, { method: "POST", body: JSON.stringify({ version: activeDraft.version, hash: activeDraft.hash, reason: "Rejected in the customer app." }) });
        drawerRoot.replaceChildren();
        showToast("The policy request was rejected.", "success");
        await renderReview();
      } catch (error) {
        if (error.status !== 409) throw error;
        drawerRoot.replaceChildren();
        activeDraft = null;
        answers = {};
        showToast("The draft changed. Reloading the latest version for you.", "error");
        await renderReview();
      }
    } else if (action === "show-step-up-details") {
      showStepUpDetails(button.dataset.id);
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
    } else if (action === "inspect-decision") {
      if (!currentDecisionPayload) throw new Error("The decision record is not loaded.");
      renderDebugger(currentDecisionPayload);
    } else if (action === "debug-tab") {
      if (!currentDecisionPayload) throw new Error("The decision record is not loaded.");
      renderDebugger(currentDecisionPayload, button.dataset.tab);
      drawerRoot.querySelector(`[data-tab="${button.dataset.tab}"]`).focus();
    } else if (action === "close-drawer") {
      if (event.target === button || button === event.target.closest(".close-button") || event.target.classList.contains("drawer-backdrop")) {
        drawerSerial += 1;
        currentDecisionPayload = null;
        drawerRoot.replaceChildren();
      }
    } else if (action === "open-tighten") {
      openTighten();
    } else if (action === "revoke-mandate") {
      openRevoke();
    } else if (action === "submit-tighten") {
      button.disabled = true;
      await submitTighten();
    } else if (action === "confirm-revoke") {
      button.disabled = true;
      await revokeMandate();
    } else if (action === "show-rule-details") {
      showRuleDetails();
    } else if (action === "show-examples") {
      showExamples();
    }
  } catch (error) {
    showToast(error.message, "error");
    if (button.isConnected) button.disabled = false;
  }
});

new MutationObserver(() => {
  const dialog = drawerRoot.querySelector('[role="dialog"]');
  document.querySelector(".app-frame").inert = Boolean(dialog);
  document.querySelector(".mobile-nav").inert = Boolean(dialog);
  document.body.classList.toggle("dialog-open", Boolean(dialog));
  if (dialog) {
    dialog.tabIndex = -1;
    if (!dialog.contains(document.activeElement)) dialog.focus();
  } else if (drawerTrigger?.isConnected) {
    drawerTrigger.focus();
    drawerTrigger = null;
  }
}).observe(drawerRoot, { childList: true });

window.addEventListener("hashchange", () => setActiveRoute(window.location.hash.slice(1)));
window.addEventListener("keydown", (event) => {
  const dialog = drawerRoot.querySelector('[role="dialog"]');
  if (dialog && event.key === "Tab") {
    const focusable = [...dialog.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), summary, [tabindex="0"]')].filter((node) => node.tabIndex >= 0 && node.getClientRects().length);
    const first = focusable[0];
    const last = focusable.at(-1);
    if (!first) {
      event.preventDefault();
      dialog.focus();
    } else if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
  if (event.target.matches('[role="tab"]') && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
    event.preventDefault();
    const tabs = [...event.target.closest('[role="tablist"]').querySelectorAll('[role="tab"]')];
    const index = tabs.indexOf(event.target);
    const target = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    tabs[target].click();
  }
  if (event.key === "Enter" && event.target.id === "demo-username") {
    event.preventDefault();
    document.querySelector('[data-action="login"]').click();
  }
  if (event.key === "Escape" && drawerRoot.childElementCount) {
    drawerSerial += 1;
    currentDecisionPayload = null;
    drawerRoot.replaceChildren();
  }
});

initialize();
