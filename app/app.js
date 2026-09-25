"use strict";

const MANDATE_KEY = "viseca.demo.mandateId";
const MANDATE_OWNER_KEY = "viseca.demo.mandateOwner";
class DraftLinkError extends Error {}
class PurchaseLinkError extends Error {}
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const screen = document.querySelector("#screen");
const overlayRoot = document.querySelector("#overlay-root");
const toastRoot = document.querySelector("#toast-root");
const globalControls = {
  purchase_amount: { label: "Maximum per purchase (CHF)", field: "authorization.billing_amount_chf", operator: "<=", scope: "purchase", currency: "CHF" },
  rolling_amount: { label: "Rolling spending cap (CHF)", field: "authorization.billing_amount_chf", operator: "<=", scope: "period", currency: "CHF" },
  rolling_count: { label: "Rolling purchase count", field: "state.approvals_count", operator: "<", scope: "period" },
};
const examples = [
  "Find a 27-inch USB-C monitor below CHF 400 with excellent colour accuracy",
  "Find a morning train from Zürich to Milan with a window seat",
  "Find a compact blue birthday gift around CHF 80",
  "Get foldable black noise-cancelling headphones below CHF 300",
  "Find blue EU 43 running shoes with at least 14-day returns",
  "Find a round walnut dining table below CHF 700",
];
const state = {
  user: null,
  accountId: null,
  authMode: "login",
  route: "shop",
  walletTab: "needs",
  activityFilter: "all",
  draft: null,
  ownedDrafts: [],
  answers: {},
  mandate: null,
  ownedMandates: [],
  globalPolicy: null,
  stagedGlobalRules: null,
  globalConflict: false,
  agents: [],
  pairing: null,
  pairings: null,
  pairingCode: null,
  pairCode: null,
  pairLinkError: null,
  pending: [],
  history: [],
  details: new Map(),
  detail: null,
  prompt: "",
  extraDetails: "",
  serial: 0,
  pendingSerial: 0,
  detailSerial: 0,
  timer: null,
  pairTimer: null,
  exampleTimer: null,
  overlayTrigger: null,
  pendingTabFocus: null,
};

function text(value, label) {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${label} is missing.`);
  return value;
}

function validTime(value, label) {
  const time = new Date(text(value, label)).getTime();
  if (!Number.isFinite(time)) throw new Error(`${label} is invalid.`);
  return time;
}

function validateSession(payload) {
  const accountId = text(payload?.account_id, "Account ID");
  if (!/^[0-9a-f]{32}$/.test(accountId)) throw new Error("The account ID is invalid.");
  return { accountId, username: text(payload.username, "Session username") };
}

function validateScopes(scopes) {
  if (!Array.isArray(scopes) || scopes.length !== 2 || new Set(scopes).size !== 2 || !scopes.includes("policy:propose") || !scopes.includes("policy:read")) throw new Error("The agent requests unsupported access.");
  return scopes;
}

function validatePairing(payload) {
  if (!payload || Object.hasOwn(payload, "agent_token")) throw new Error("The agent connection response is invalid.");
  text(payload.agent_label, "Agent name");
  validateScopes(payload.scopes);
  validTime(payload.expires_at, "Connection expiry");
  return payload;
}

function validateAgentList(payload) {
  if (!Array.isArray(payload)) throw new Error("The Wallet did not return a list of connected agents.");
  const seen = new Set();
  return payload.map((agent) => {
    if (!agent || Object.hasOwn(agent, "agent_token")) throw new Error("An agent record contains a credential or is incomplete.");
    const id = text(agent.agent_id, "Agent ID");
    if (seen.has(id)) throw new Error(`Agent ${id} appears twice.`);
    seen.add(id);
    text(agent.agent_label, "Agent name");
    validateScopes(agent.scopes);
    validTime(agent.created_at, "Agent connection time");
    if (agent.last_used_at !== null) validTime(agent.last_used_at, "Agent last use");
    if (agent.revoked_at !== null) validTime(agent.revoked_at, "Agent revocation time");
    return agent;
  });
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

function hasDraftLink() {
  const query = new URLSearchParams(window.location.search);
  return query.has("draft") || query.has("draft_id");
}

function linkedDraftId() {
  const query = new URLSearchParams(window.location.search);
  const draft = query.get("draft");
  const draftId = query.get("draft_id");
  if (draft === "" || draftId === "") throw new DraftLinkError("The spending-plan link has an empty draft ID.");
  if (draft && draftId && draft !== draftId) throw new DraftLinkError("The draft and draft_id links refer to different spending plans.");
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

function hasPairLink() {
  return new URLSearchParams(window.location.search).has("pair");
}

function capturePairLink() {
  const url = new URL(window.location.href);
  if (!url.searchParams.has("pair")) return;
  const codes = url.searchParams.getAll("pair");
  state.pairLinkError = codes.length !== 1 || !codes[0]?.trim() || hasDraftLink() || hasPurchaseLink() ? "Use one pairing code only." : null;
  state.pairCode = state.pairLinkError ? null : codes[0].trim();
  for (const name of ["pair", "draft", "draft_id", "authorization_id"]) url.searchParams.delete(name);
  url.hash = "pair";
  window.history.replaceState(null, "", url.pathname + url.search + url.hash);
}

function pairingCode() {
  return text(state.pairCode, "Agent connection code");
}

function clearPairLink() {
  const url = new URL(window.location.href);
  url.searchParams.delete("pair");
  window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  state.pairCode = null;
  state.pairLinkError = null;
  state.pairing = null;
  state.pairingCode = null;
}

function hasPurchaseLink() {
  return new URLSearchParams(window.location.search).has("authorization_id");
}

function linkedPurchaseId() {
  const query = new URLSearchParams(window.location.search);
  const ids = query.getAll("authorization_id");
  if (ids.length !== 1 || !ids[0]?.trim() || hasDraftLink() || hasPairLink()) throw new PurchaseLinkError("The purchase link must contain one pending purchase ID and no other Wallet link.");
  return ids[0];
}

function clearPurchaseLink() {
  const url = new URL(window.location.href);
  for (const name of ["authorization_id", "draft", "draft_id", "pair"]) url.searchParams.delete(name);
  window.history.replaceState(null, "", url.pathname + url.search + url.hash);
}

function requestedRoute(hash = window.location.hash.slice(1)) {
  if (hasPurchaseLink()) return "purchase";
  if (hasPairLink()) return "pair";
  if (hasDraftLink()) return "review";
  return hash || "shop";
}

function mandateId() {
  const owner = window.sessionStorage.getItem(MANDATE_OWNER_KEY);
  if (owner && owner !== state.accountId) return null;
  return window.sessionStorage.getItem(MANDATE_KEY);
}

function validateDraft(draft) {
  if (!draft || typeof draft !== "object" || !Array.isArray(draft.rules) || !Array.isArray(draft.open_questions) || !Array.isArray(draft.examples)) throw new Error("The saved spending plan is incomplete.");
  text(draft.draft_id, "Draft ID");
  if (text(draft.created_for, "Draft owner") !== state.accountId) throw new Error("The spending request belongs to another account.");
  text(draft.hash, "Draft hash");
  text(draft.instruction, "Original request");
  if (!Number.isInteger(draft.version)) throw new Error("The saved spending plan has no valid version.");
  const hashVersion = Object.hasOwn(draft, "hash_version") ? draft.hash_version : 1;
  const cases = Object.hasOwn(draft, "boundary_cases") ? draft.boundary_cases : [];
  if (![1, 2].includes(hashVersion) || !Array.isArray(cases)) throw new Error("The saved spending plan has invalid boundary cases.");
  if ((hashVersion === 1 && cases.length) || (hashVersion === 2 && !cases.length)) throw new Error("The saved spending plan has an invalid hash version.");
  cases.forEach((item) => {
    text(item.description, "Boundary case description");
    if (!["approve", "decline", "step_up"].includes(item.expected)) throw new Error("A boundary case has an unsupported expected outcome.");
  });
  draft.rules.forEach((rule) => { text(rule.field, "Rule field"); text(rule.plain_english, "Rule description"); });
  draft.open_questions.forEach((question) => {
    text(question.question, "Question");
    if (!Array.isArray(question.options) || !Array.isArray(question.confirming_answers)) throw new Error("The saved spending plan has an invalid question.");
  });
  return { ...draft, hash_version: hashVersion, boundary_cases: cases };
}

function validateBoundaryResults(payload, draft) {
  if (!payload || !Array.isArray(payload.results)) throw new Error("The Wallet did not return computed boundary results.");
  if (text(payload.draft_id, "Boundary result draft ID") !== draft.draft_id || payload.version !== draft.version || text(payload.hash, "Boundary result hash") !== draft.hash) throw new Error("The computed boundary results do not match the saved spending plan.");
  validTime(payload.evaluated_at, "Boundary evaluation time");
  if (!["proposal", "revision", "confirmation"].includes(payload.phase)) throw new Error("The boundary evaluation has an unknown phase.");
  text(payload.engine_version, "Boundary engine version");
  if (payload.results.length !== draft.boundary_cases.length) throw new Error("The computed boundary results do not cover every authored case.");
  payload.results.forEach((item, index) => {
    const authored = draft.boundary_cases[index];
    if (!item || item.case_index !== index || text(item.description, "Boundary result description") !== authored.description || item.expected !== authored.expected) throw new Error("A computed boundary result does not match its authored case.");
    if (!["approve", "decline", "step_up"].includes(item.observed)) throw new Error("A computed boundary result has an unsupported outcome.");
    if (item.observed !== item.expected) throw new Error("A computed boundary result differs from the authored expected outcome.");
    if (!Array.isArray(item.reason_codes)) throw new Error("A computed boundary result has no reason codes.");
    item.reason_codes.forEach((code) => text(code, "Boundary reason code"));
    if (!/^[0-9a-f]{64}$/.test(text(item.case_input_hash, "Boundary case input hash"))) throw new Error("A computed boundary result has an invalid case-input hash.");
  });
  return payload;
}

function validateDraftList(items) {
  if (!Array.isArray(items)) throw new Error("The Wallet did not return a list of spending requests.");
  const seen = new Set();
  return items.map((item) => {
    const id = text(item?.draft_id, "Spending request ID");
    if (seen.has(id)) throw new Error(`The spending request ${id} appears twice.`);
    seen.add(id);
    if (!Number.isInteger(item.version) || !Number.isInteger(item.open_questions) || item.open_questions < 0) throw new Error("A spending request has invalid counts or version.");
    text(item.hash, "Spending request hash");
    text(item.instruction, "Spending request");
    if (!["proposed", "confirming", "confirmed", "rejected"].includes(item.state) || !["ask", "decline", "approve"].includes(item.uncertainty_policy)) throw new Error("A spending request has an unknown state.");
    if (!Array.isArray(item.plain_english)) throw new Error("A spending request has no rule summaries.");
    item.plain_english.forEach((rule) => text(rule, "Rule summary"));
    if (!Number.isFinite(new Date(text(item.created_at, "Request time")).getTime())) throw new Error("A spending request has an invalid time.");
    if (item.state === "confirmed") text(item.mandate_id, "Confirmed permission ID");
    else if (item.mandate_id !== null) throw new Error("An unconfirmed request has a permission ID.");
    return item;
  });
}

function validateMandateList(items) {
  if (!Array.isArray(items)) throw new Error("The Wallet did not return a list of spending permissions.");
  const seen = new Set();
  return items.map((item) => {
    const id = text(item?.mandate_id, "Permission ID");
    if (seen.has(id)) throw new Error(`The permission ${id} appears twice.`);
    seen.add(id);
    text(item.draft_id, "Confirmed request ID");
    text(item.hash, "Permission hash");
    text(item.instruction, "Permission request");
    if (!Number.isInteger(item.version) || !Number.isInteger(item.approvals_count) || item.approvals_count < 0 || !Number.isInteger(item.pending_step_ups) || item.pending_step_ups < 0) throw new Error("A permission has invalid counts or version.");
    if (!["active", "revoked", "superseded", "expired"].includes(item.status)) throw new Error("A permission has an unknown status.");
    if (!Number.isFinite(new Date(text(item.confirmed_at, "Confirmation time")).getTime())) throw new Error("A permission has an invalid confirmation time.");
    if (!Number.isInteger(item.global_policy_version) || item.global_policy_version < 0) throw new Error("A permission has no valid account-wide rule version.");
    text(item.global_policy_hash, "Permission account-wide rule hash");
    return item;
  });
}

function validateGlobalPolicy(payload) {
  if (!payload || payload.customer !== state.accountId || !Number.isInteger(payload.version) || payload.version < 0 || !Array.isArray(payload.rules)) throw new Error("The account-wide rule record is incomplete or belongs to another customer.");
  text(payload.hash, "Account-wide rule hash");
  payload.rules.forEach((rule) => { text(rule.field, "Account-wide rule field"); text(rule.plain_english, "Account-wide rule description"); });
  if (payload.updated_at !== null && !Number.isFinite(new Date(text(payload.updated_at, "Account-wide rule update time")).getTime())) throw new Error("The account-wide rule update time is invalid.");
  if (payload.version === 0 && (payload.rules.length || payload.updated_at !== null)) throw new Error("The empty account-wide rule record is inconsistent.");
  return payload;
}

function validateMandate(payload) {
  if (!payload || !payload.mandate || !payload.draft || !payload.effective_policy || !payload.state) throw new Error("The Wallet returned an incomplete permission.");
  const { mandate, draft, effective_policy, state: usage } = payload;
  if (!Number.isInteger(payload.global_policy_version) || payload.global_policy_version < 0) throw new Error("The permission has no valid account-wide rule version.");
  text(payload.global_policy_hash, "Permission account-wide rule hash");
  text(mandate.mandate_id, "Permission ID");
  if (!["active", "revoked", "superseded", "expired"].includes(mandate.status)) throw new Error("The permission has an unknown status.");
  validateDraft(draft);
  if (!Array.isArray(effective_policy.rules) || !Array.isArray(usage.approvals) || usage.mandate_id !== mandate.mandate_id) throw new Error("The permission and its purchase state do not match.");
  effective_policy.rules.forEach((rule) => { text(rule.field, "Current rule field"); text(rule.plain_english, "Current rule description"); });
  window.sessionStorage.setItem(MANDATE_OWNER_KEY, text(state.accountId, "Current account ID"));
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
  if (event.authorization.authorization_id !== decision.authorization_id) throw new Error("The purchase event and decision refer to different authorizations.");
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
  if (!["shop", "wallet", "activity", "review", "purchase", "pair", "agents"].includes(route)) {
    setScreen(errorPanel("This page is unavailable", new Error(`Unknown page: ${route}`)));
    return;
  }
  if (state.route === "pair" && route !== "pair") clearPairLink();
  if (state.route === "purchase" && route !== "purchase") clearPurchaseLink();
  state.route = route;
  state.serial += 1;
  state.pendingSerial += 1;
  state.detailSerial += 1;
  window.clearTimeout(state.timer);
  window.clearInterval(state.pairTimer);
  window.clearTimeout(state.exampleTimer);
  state.timer = null;
  state.pairTimer = null;
  state.exampleTimer = null;
  state.pairing = null;
  state.pairingCode = null;
  closeOverlay();
  if (window.location.hash !== `#${route}`) window.history.replaceState(null, "", `#${route}`);
  document.querySelectorAll(".nav-button").forEach((button) => {
    const selected = button.dataset.route === (["review", "purchase", "pair", "agents"].includes(route) ? "wallet" : route);
    button.classList.toggle("is-active", selected);
    if (selected) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  if (!keepScroll) window.scrollTo(0, 0);
  return render();
}

function sessionExpired(error) {
  state.serial += 1;
  state.pendingSerial += 1;
  window.clearTimeout(state.timer);
  window.clearInterval(state.pairTimer);
  window.clearTimeout(state.exampleTimer);
  state.detailSerial += 1;
  state.timer = null;
  state.pairTimer = null;
  state.user = null;
  state.accountId = null;
  state.authMode = "login";
  state.mandate = null;
  state.ownedMandates = [];
  state.globalPolicy = null;
  state.stagedGlobalRules = null;
  state.globalConflict = false;
  state.agents = [];
  state.pairing = null;
  state.pairingCode = null;
  state.pending = [];
  state.draft = null;
  state.ownedDrafts = [];
  state.answers = {};
  state.details.clear();
  state.history = [];
  state.detail = null;
  state.prompt = "";
  state.extraDetails = "";
  closeOverlay();
  state.overlayTrigger = null;
  document.querySelector("#wallet-indicator").hidden = true;
  renderLogin();
  toast(error.message);
}

async function render() {
  const serial = state.serial;
  if (!state.user) { renderLogin(); return; }
  try {
    if (state.route === "shop") await renderShop(serial);
    else if (state.route === "wallet") await renderWallet(serial);
    else if (state.route === "review") await renderReview(serial);
    else if (state.route === "purchase") await renderPurchase(serial);
    else if (state.route === "pair") await renderPair(serial);
    else if (state.route === "agents") await renderAgents(serial);
    else await renderActivity(serial);
  } catch (error) {
    if (serial !== state.serial) return;
    if (error.status === 401) { sessionExpired(error); return; }
    const linkAction = state.route === "purchase" ? `<button type="button" class="outline-button" data-action="clear-invalid-link">Open Shop without this purchase link</button>` : state.route === "pair" ? `<button type="button" class="outline-button" data-action="clear-invalid-link">Continue without this agent link</button>` : error instanceof DraftLinkError ? `<button type="button" class="outline-button" data-action="clear-invalid-link">Open Shop without this link</button>` : "";
    const title = state.route === "review" ? "Review spending permission" : state.route === "purchase" ? "Review pending purchase" : state.route === "pair" ? "Connect a shopping agent" : state.route;
    setScreen(`<div class="page-title"><h1>${esc(title)}</h1></div>${errorPanel("This screen could not be loaded", error)}${linkAction}`);
    if (state.route === "purchase") {
      const heading = screen.querySelector(".page-title h1");
      heading.tabIndex = -1;
      heading.focus();
    }
  }
}

function renderLogin() {
  const registering = state.authMode === "register";
  const context = hasPurchaseLink() ? `${registering ? "Create an account" : "Sign in"} to review a pending purchase.` : (state.pairCode !== null || state.pairLinkError || requestedRoute() === "pair") ? `${registering ? "Create an account" : "Sign in"} to review an agent connection request.` : `${registering ? "Create an account" : "Sign in"} to review spending permissions sent by your shopping agent.`;
  setScreen(`<section class="identity-view"><div class="identity-intro"><span class="section-kicker">LOCAL DEMO ACCOUNT</span><h1>${registering ? "Create your account" : "Welcome to your Wallet."}</h1><p>${context} This uses a local account, not a Viseca banking login.</p></div><div class="auth-fields"><label for="username">Username</label><input id="username" maxlength="80" autocomplete="username" placeholder="Your username" /><label for="password">Password</label><input id="password" type="password" minlength="8" maxlength="256" autocomplete="${registering ? "new-password" : "current-password"}" /><p class="auth-error" role="alert" hidden></p><button class="primary-button" type="button" data-action="${registering ? "register" : "login"}">${registering ? "Create account" : "Sign in"}</button></div><div class="auth-switch"><span>${registering ? "Already have an account?" : "New here?"}</span><button type="button" class="text-button" data-action="auth-mode" data-mode="${registering ? "login" : "register"}">${registering ? "Sign in" : "Create an account"}</button></div></section>`);
}

function setSession(payload) {
  const { accountId, username } = validateSession(payload);
  const previousOwner = window.sessionStorage.getItem(MANDATE_OWNER_KEY);
  if (previousOwner && previousOwner !== accountId) {
    window.sessionStorage.removeItem(MANDATE_KEY);
    window.sessionStorage.removeItem(MANDATE_OWNER_KEY);
  }
  state.accountId = accountId;
  state.user = username;
}

function renderPairEntry(message = state.pairLinkError) {
  setScreen(`<section class="identity-view pair-code-view"><button type="button" class="back-button" data-route="shop">‹ Shop</button><div class="identity-intro"><span class="section-kicker">AGENT CONNECTION</span><h1>Connect an agent</h1><p>Paste the code from your agent. Review its access before you decide.</p></div><section class="pair-code-entry"><div class="pair-code-fields"><label for="pair-code">Pairing code</label><input id="pair-code" class="pair-code-input" type="text" maxlength="128" autocomplete="off" autocapitalize="none" spellcheck="false" aria-describedby="pair-code-guidance pair-code-error" placeholder="Paste code from your agent" /><p id="pair-code-guidance">Entering a code does not approve access.</p></div><p id="pair-code-error" class="pair-code-error" role="alert" ${message ? "" : "hidden"}>${message ? esc(message) : ""}</p><div class="pair-code-actions"><button type="button" class="outline-button" data-action="clear-pair-code">Clear</button><button type="button" class="primary-button" data-action="submit-pair-code">Review agent</button></div></section></section>`);
  if (message) screen.querySelector("#pair-code").focus();
}

async function renderPair(serial) {
  if (state.pairLinkError || state.pairCode === null) { renderPairEntry(); return; }
  const code = pairingCode();
  loading("Checking agent connection…");
  let pairing;
  try {
    pairing = validatePairing(await walletApi.pairing(code));
  } catch (error) {
    if (serial !== state.serial) return;
    if (error.status !== 404) throw error;
    state.pairCode = null;
    state.pairLinkError = "Invalid, expired or used code.";
    renderPairEntry();
    return;
  }
  if (serial !== state.serial) return;
  state.pairing = pairing;
  state.pairingCode = code;
  setScreen(`<section class="identity-view"><button type="button" class="back-button" data-route="shop">‹ Shop</button><div class="identity-intro"><span class="section-kicker">AGENT CONNECTION</span><h1>Connect this agent?</h1><p>Approving pairs this agent to your local account, ${esc(state.user)}. Only you can approve access in the Wallet.</p></div><section class="identity-card"><h2>${esc(pairing.agent_label)}</h2><p>This agent will be able to:</p><ul class="scope-list"><li>Propose spending plans for you to review (policy:propose)</li><li>Read the status and summary of its plans (policy:read)</li></ul><p>It cannot authorize a plan, answer a purchase review or change your rules.</p><p class="expiry"><span id="pair-remaining"></span><time datetime="${esc(pairing.expires_at)}">${esc(new Date(pairing.expires_at).toLocaleString("en-CH"))}</time></p><div class="agent-actions"><button type="button" class="outline-button" data-action="decline-pair">Not now</button><button type="button" class="primary-button" data-action="approve-pair">Approve connection</button></div></section></section>`);
  const heading = screen.querySelector(".identity-intro h1");
  heading.tabIndex = -1;
  heading.focus();
  const expiry = validTime(pairing.expires_at, "Connection expiry");
  function updateExpiry() {
    if (serial !== state.serial) return;
    const remaining = Math.max(0, Math.ceil((expiry - Date.now()) / 1000));
    const label = document.querySelector("#pair-remaining");
    const approve = document.querySelector('[data-action="approve-pair"]');
    if (!label || !approve) return;
    label.textContent = remaining ? `Expires in ${Math.floor(remaining / 60)}m ${String(remaining % 60).padStart(2, "0")}s · ` : "This connection link has expired. ";
    approve.disabled = remaining === 0;
    if (!remaining) window.clearInterval(state.pairTimer);
  }
  updateExpiry();
  if (expiry > Date.now()) state.pairTimer = window.setInterval(updateExpiry, 1000);
}

async function renderAgents(serial) {
  loading("Loading connected agents…");
  const agents = validateAgentList(await walletApi.agents());
  if (serial !== state.serial) return;
  state.agents = agents;
  const cards = agents.map((agent) => `<article class="identity-card agent-card"><span class="section-kicker">${agent.revoked_at ? "REVOKED" : "CONNECTED"}</span><h2>${esc(agent.agent_label)}</h2><dl class="agent-meta"><div><dt>Access</dt><dd>${esc(agent.scopes.join(" · "))}</dd></div><div><dt>Connected</dt><dd>${esc(new Date(agent.created_at).toLocaleString("en-CH"))}</dd></div><div><dt>Last used</dt><dd>${agent.last_used_at === null ? "Never" : esc(new Date(agent.last_used_at).toLocaleString("en-CH"))}</dd></div></dl>${agent.revoked_at ? `<p>Access revoked ${esc(new Date(agent.revoked_at).toLocaleString("en-CH"))}.</p>` : `<div class="agent-actions"><button type="button" class="outline-button" data-action="open-agent-revoke" data-id="${esc(agent.agent_id)}">Revoke access</button></div>`}</article>`).join("");
  setScreen(`<section class="identity-view"><button type="button" class="back-button" data-route="wallet">‹ Wallet</button><div class="identity-intro"><span class="section-kicker">YOUR ACCOUNT</span><h1>Connected agents</h1><p>Review which shopping agents can propose plans. Revoking an agent stops future tool calls; it does not change your confirmed permissions.</p></div><div class="agents-list">${cards || `<section class="identity-card"><h2>No connected agents</h2><p>Ask an agent to begin pairing, then open its Wallet link to approve access. An approved agent appears here after it finishes pairing.</p></section>`}</div><div class="agent-actions"><button type="button" class="text-button" data-action="refresh-agents">Refresh list</button></div></section>`);
}

async function initialize() {
  try {
    capturePairLink();
    setSession(await walletApi.session());
    navigate(requestedRoute());
  } catch (error) {
    if (error.status === 401) { renderLogin(); return; }
    setScreen(errorPanel("Your session could not be checked", error));
  }
}

function growTextArea(input, minimum) {
  input.style.height = "auto";
  input.style.height = `${Math.max(minimum, input.scrollHeight)}px`;
}

function startExamples() {
  window.clearTimeout(state.exampleTimer);
  if (reducedMotion.matches) return;
  let index = 0, position = 0, erasing = false;
  function tick() {
    const composer = document.querySelector("#shop-prompt");
    const example = document.querySelector("#animated-example");
    if (!composer || !example || document.activeElement === composer || document.activeElement === example || composer.value) return;
    const current = examples[index];
    example.dataset.example = current;
    example.setAttribute("aria-label", `Use example: ${current}`);
    example.textContent = current.slice(0, position);
    if (!erasing && position < current.length) { position += 1; state.exampleTimer = window.setTimeout(tick, 44); }
    else if (!erasing) { erasing = true; state.exampleTimer = window.setTimeout(tick, 1900); }
    else if (position > 0) { position -= 1; state.exampleTimer = window.setTimeout(tick, 22); }
    else { erasing = false; index = (index + 1) % examples.length; state.exampleTimer = window.setTimeout(tick, 350); }
  }
  tick();
}

function purchaseCap(rules) {
  const caps = rules.filter((rule) => rule.field === "authorization.billing_amount_chf" && rule.scope !== "period" && ["<", "<="].includes(rule.operator) && typeof rule.value === "number");
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
  setScreen(`<section class="shop-view"><div class="shop-intro"><h1>What can I<br />get for you?</h1><div class="orbit" aria-hidden="true"><span class="orbit-glow"></span><span class="orbit-ring one"></span><span class="orbit-ring two"></span><span class="orbit-core">✓</span><span class="orbit-dot"></span><span class="category-float tech"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/></svg>Tech</span><span class="category-float travel"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="5" y="3" width="14" height="16" rx="4"/><path d="M5 12h14M9 19l-2 3m8-3 2 3"/></svg>Travel</span><span class="category-float gifts"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3" y="9" width="18" height="12" rx="2"/><path d="M2 9h20M12 9v12M12 9c-5 0-7-2-5-5s5 0 5 5Zm0 0c5 0 7-2 5-5s-5 0-5 5Z"/></svg>Gifts</span><span class="category-float home"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 10 12 3l9 7v11H3V10Z"/><path d="M9 21v-7h6v7"/></svg>Home</span><span class="category-float style"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="m8 3-5 4-1 5 4 2v7h12v-7l4-2-1-5-5-4-4 3-4-3Z"/></svg>Style</span></div></div>
    <div class="composer"><label for="shop-prompt" class="sr-only">Your shopping request</label><textarea id="shop-prompt" rows="2" placeholder="Ask Viseca to buy something…">${esc(state.prompt)}</textarea><button class="send-button" type="button" data-action="copy-prompt" aria-label="Copy request for your shopping agent" title="Copy request for your shopping agent" ${state.prompt.trim() ? "" : "disabled"}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 20V4M5 11l7-7 7 7"/></svg></button></div>
    <div class="prompt-example" aria-live="off" ${state.prompt.trim() ? "hidden" : ""}><span>TRY ASKING</span><button type="button" data-action="use-example" id="animated-example" data-example="${esc(examples[0])}" aria-label="Use example: ${esc(examples[0])}">${esc(examples[0])}</button></div><p class="request-hint" ${state.prompt.trim() ? "hidden" : ""}>Include details that matter to you, such as colour, size, shape, price or returns.</p>
    <div class="clarification" ${state.prompt.trim() ? "" : "hidden"}><label for="request-details">Anything else your agent should know?</label><textarea id="request-details" rows="2" placeholder="Colour, size, shape, delivery or returns…">${esc(state.extraDetails)}</textarea><small>These details are copied with your request. Review any spending limits in the Wallet before authorizing.</small></div>
    <p class="agent-state">Shopping agent <span>· use an external MCP client</span></p><p class="external-agent">The arrow copies your request for your external agent. This demo has no in-app shopping model. Your agent can send you a Wallet review link after saving a plan.</p>
    ${plan ? `<section class="shop-plan"><span class="section-kicker">PLAN SAVED BY YOUR AGENT</span><h2>${esc(productName(plan))}</h2><p>${cap ? `${cap.strict ? "Below" : "Up to"} ${esc(money(cap.amount))}` : "Review the saved limits"}</p><button type="button" class="text-button" data-route="review">Review in Wallet <span aria-hidden="true">→</span></button></section>` : ""}
  </section>`);
  growTextArea(document.querySelector("#shop-prompt"), 62);
  if (state.prompt.trim()) growTextArea(document.querySelector("#request-details"), 72);
  startExamples();
}

function walletTabs() {
  return `<div class="wallet-tabs" role="tablist" aria-label="Wallet sections">${[
    ["needs", "Needs you"], ["active", "Active"], ["rules", "Rules"],
  ].map(([id, label]) => `<button type="button" role="tab" aria-selected="${state.walletTab === id}" tabindex="${state.walletTab === id ? 0 : -1}" class="${state.walletTab === id ? "selected" : ""}" data-action="wallet-tab" data-tab="${id}">${label}</button>`).join("")}</div>`;
}

function ownedRequestCard(item) {
  const label = item.state === "proposed" ? "Ready for review" : item.state === "confirming" ? "Confirmation in progress" : item.state === "confirmed" ? "Confirmed" : "Rejected";
  const body = `<span class="section-kicker">${esc(label.toUpperCase())}</span><strong>${esc(item.instruction)}</strong>${item.plain_english.length ? `<small>${esc(item.plain_english[0])}</small>` : ""}`;
  if (item.state === "proposed") return `<button type="button" class="request-record request-button" data-action="open-draft" data-id="${esc(item.draft_id)}">${body}<span>Review spending plan <span aria-hidden="true">→</span></span></button>`;
  return item.state === "confirmed"
    ? `<button type="button" class="request-record request-button" data-action="select-mandate" data-id="${esc(item.mandate_id)}" data-tab="active">${body}<span>View permission <span aria-hidden="true">→</span></span></button>`
    : `<article class="request-record">${body}</article>`;
}

function mandateChoices(items, selectedId, tab = "active") {
  return `<div class="mandate-list" role="group" aria-label="Your spending permissions">${items.map((item) => `<button type="button" class="mandate-choice ${item.mandate_id === selectedId ? "is-selected" : ""}" data-action="select-mandate" data-id="${esc(item.mandate_id)}" data-tab="${esc(tab)}" aria-pressed="${item.mandate_id === selectedId}"><span class="section-kicker">${esc(item.status.toUpperCase())}</span><strong>${esc(item.instruction)}</strong><small>${item.approvals_count} approved purchase${item.approvals_count === 1 ? "" : "s"}${item.pending_step_ups ? ` · ${item.pending_step_ups} pending review` : ""}</small></button>`).join("")}</div>`;
}

function schedulePendingRefresh() {
  window.clearTimeout(state.timer);
  if (state.route !== "wallet" || state.walletTab !== "needs" || !state.user) return;
  state.timer = window.setTimeout(async () => {
    state.timer = null;
    if (await refreshPending()) schedulePendingRefresh();
  }, 2000);
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
  if (state.walletTab === "needs") schedulePendingRefresh();
}

function needsHeading(count) {
  if (count) return `${count} thing${count === 1 ? " needs" : "s need"} you`;
  return state.ownedDrafts.some((item) => item.state === "confirming") ? "Confirmation in progress" : "You're all caught up";
}

async function needsContent(serial) {
  const linked = linkedDraftId();
  const [draft, pending, ownedDrafts, pairings] = await Promise.all([
    linked ? walletApi.draft(linked).then(validateDraft) : Promise.resolve(null),
    walletApi.pending(),
    walletApi.drafts().then(validateDraftList),
    walletApi.pendingPairings(),
  ]);
  if (serial !== state.serial) return "";
  if (!Array.isArray(pending)) throw new Error("The Wallet did not return a list of pending purchases.");
  if (!Array.isArray(pairings)) throw new Error("The Wallet did not return a list of pending agent connections.");
  state.pairings = pairings;
  if (draft && !ownedDrafts.some((item) => item.draft_id === draft.draft_id)) throw new Error("The linked spending request is missing from your account's list.");
  state.pending = pending;
  state.draft = draft;
  state.ownedDrafts = ownedDrafts;
  const count = pending.length + ownedDrafts.filter((item) => item.state === "proposed").length + pairings.length;
  document.querySelector("#wallet-indicator").hidden = !count;
  return `<div class="wallet-section"><h2 id="needs-heading">${esc(needsHeading(count))}</h2>
    <div id="pairing-list">${pairings.map(pairingCard).join("")}</div>
    <div id="pending-list">${pending.map(pendingCard).join("")}</div>
    <p class="calm-copy" id="needs-empty" ${count ? "hidden" : ""}>${ownedDrafts.some((item) => item.state === "confirming") ? "Your confirmation is being checked. It will appear as confirmed when the backend accepts it." : "Spending requests and purchases that need a decision will appear here."}</p>
    <div id="request-history">${ownedDrafts.length ? `<section class="request-history"><h3>Recent spending requests</h3>${ownedDrafts.map(ownedRequestCard).join("")}</section>` : ""}</div></div>`;
}

function pendingTimeLabel(expiresAt) {
  const remaining = new Date(expiresAt).getTime() - Date.now();
  if (!Number.isFinite(remaining)) throw new Error("A pending purchase has an invalid deadline.");
  return remaining > 0 ? `${Math.floor(remaining / 60000)}m ${String(Math.floor(remaining / 1000) % 60).padStart(2, "0")}s left` : "Deadline reached";
}

function pendingTitle(evidence) {
  const count = evidence.filter((check) => check.result !== "pass").length;
  return count === 1 ? "One detail needs a decision" : count ? `${count} details need a decision` : "Review this purchase";
}

function pendingPurchase(item) {
  text(item.authorization_id, "Pending purchase ID");
  validTime(item.expires_at, "Pending purchase deadline");
  if (!item.event?.authorization?.merchant || !item.decision || !Array.isArray(item.decision.evidence)) throw new Error("A pending purchase is incomplete.");
  const auth = item.event.authorization;
  if (auth.authorization_id !== item.authorization_id || item.decision.authorization_id !== item.authorization_id || item.decision.decision !== "step_up") throw new Error("The pending purchase and its decision do not match.");
  text(auth.merchant.merchant_name, "Pending merchant");
  text(item.decision.customer_message, "Purchase review message");
  return auth;
}

function pairingCard(item) {
  const label = text(item.agent_label, "Agent label");
  const scopes = Array.isArray(item.scopes) ? item.scopes.map((scope) => text(scope, "Scope")) : [];
  return `<div class="need-card uncertain-card pairing-card"><span class="section-kicker" aria-live="off">AGENT CONNECTION</span>
    <h3>${esc(label)} wants to connect</h3>
    <p class="calm-copy">It can propose spending permissions and read their status. It cannot confirm, change or revoke anything, and it cannot buy.</p>
    <p class="meta">Allowed: ${esc(scopes.join(", "))}</p>
    <div class="need-actions"><button type="button" class="primary-button" data-action="approve-pending-pair" data-id="${esc(text(item.pairing_id, "Pairing id"))}">Approve</button></div></div>`;
}

function pendingCard(item) {
  const auth = pendingPurchase(item);
  return `<button type="button" class="need-card uncertain-card" data-action="open-pending" data-id="${esc(item.authorization_id)}"><span class="section-kicker" aria-live="off">PURCHASE REVIEW · ${esc(pendingTimeLabel(item.expires_at))}</span><strong>${esc(pendingTitle(item.decision.evidence))}</strong><span>${esc(auth.merchant.merchant_name)} · ${esc(money(auth.billing_amount_chf, auth.currency))}</span><small>${esc(item.decision.customer_message)}</small><b aria-hidden="true">›</b></button>`;
}

async function renderPurchase(serial) {
  loading("Loading pending purchase…");
  const id = linkedPurchaseId();
  const pending = await walletApi.pending();
  if (serial !== state.serial) return;
  if (!Array.isArray(pending)) throw new Error("The Wallet did not return pending purchases.");
  const item = pending.find((entry) => entry.authorization_id === id);
  if (!item) throw new PurchaseLinkError("This purchase is not pending for your account. It may have been answered or timed out.");
  const auth = pendingPurchase(item);
  const items = auth.items.map((entry) => text(entry.item_name, "Purchase item")).join(" + ");
  state.pending = pending;
  setScreen(`<section class="linked-purchase-view"><button type="button" class="back-button" data-route="shop">‹ Shop</button><div class="linked-purchase-intro"><span class="section-kicker">PURCHASE REVIEW</span><h1>Review pending purchase</h1><p>Your Wallet loaded this pending purchase for your account. Your answer applies only to this purchase.</p></div><section class="linked-purchase-summary"><h2>${esc(auth.merchant.merchant_name)}</h2><strong>${esc(money(auth.billing_amount_chf, auth.currency))}</strong><p>${esc(items)}</p><p class="linked-purchase-meta">${esc(item.decision.customer_message)}</p><p class="linked-purchase-meta"><time datetime="${esc(item.expires_at)}">${esc(new Date(item.expires_at).toLocaleString("en-CH"))}</time> · ${esc(pendingTimeLabel(item.expires_at))}</p></section><div class="linked-purchase-actions"><button type="button" class="outline-button" data-action="reload">Refresh status</button><button type="button" class="primary-button" data-action="open-pending" data-id="${esc(id)}">Review decision</button></div></section>`);
}

async function refreshPending() {
  if (state.route !== "wallet" || state.walletTab !== "needs" || !state.user) return;
  const container = document.querySelector("#pending-list");
  if (!container) return;
  const request = ++state.pendingSerial;
  const route = state.serial;
  const id = mandateId();
  try {
    const [pending, ownedDrafts, pairings] = await Promise.all([walletApi.pending(), walletApi.drafts().then(validateDraftList), walletApi.pendingPairings()]);
    if (!Array.isArray(pending)) throw new Error("Pending purchases must be a list.");
    if (!Array.isArray(pairings)) throw new Error("Pending agent connections must be a list.");
    const pairingList = document.querySelector("#pairing-list");
    const pairingsChanged = !state.pairings || pairings.length !== state.pairings.length || pairings.some((item, index) => item.pairing_id !== state.pairings[index].pairing_id);
    if (pairingList && pairingsChanged) { pairingList.innerHTML = pairings.map(pairingCard).join(""); state.pairings = pairings; }
    if (request !== state.pendingSerial || route !== state.serial || id !== mandateId() || !container.isConnected) return;
    const markup = pending.map(pendingCard).join("");
    const unchanged = pending.length === state.pending.length && pending.every((item, index) =>
      item.authorization_id === state.pending[index].authorization_id &&
      item.expires_at === state.pending[index].expires_at &&
      item.decision.customer_message === state.pending[index].decision.customer_message);
    if (unchanged) {
      pending.forEach((item, index) => {
        const label = container.children[index]?.querySelector(".section-kicker");
        if (!label) throw new Error("The pending purchase card is missing its deadline.");
        const next = `PURCHASE REVIEW · ${pendingTimeLabel(item.expires_at)}`;
        if (label.textContent !== next) label.textContent = next;
      });
    } else {
      const focusedId = container.contains(document.activeElement) ? document.activeElement.closest('[data-action="open-pending"]')?.dataset.id : null;
      container.innerHTML = markup;
      if (focusedId) {
        const card = [...container.querySelectorAll('[data-action="open-pending"]')].find((item) => item.dataset.id === focusedId);
        if (card) card.focus();
        else {
          const heading = document.querySelector("#needs-heading");
          heading.tabIndex = -1;
          heading.focus();
        }
      }
    }
    state.pending = pending;
    const requests = document.querySelector("#request-history");
    if (!requests) throw new Error("The spending request list is missing from the Wallet.");
    const draftsChanged = ownedDrafts.length !== state.ownedDrafts.length || ownedDrafts.some((item, index) =>
      item.draft_id !== state.ownedDrafts[index].draft_id || item.version !== state.ownedDrafts[index].version || item.hash !== state.ownedDrafts[index].hash || item.state !== state.ownedDrafts[index].state);
    if (draftsChanged) {
      const focusedId = requests.contains(document.activeElement) ? document.activeElement.closest('[data-action="open-draft"]')?.dataset.id : null;
      requests.innerHTML = ownedDrafts.length ? `<section class="request-history"><h3>Recent spending requests</h3>${ownedDrafts.map(ownedRequestCard).join("")}</section>` : "";
      if (focusedId) {
        const card = [...requests.querySelectorAll('[data-action="open-draft"]')].find((item) => item.dataset.id === focusedId);
        if (card) card.focus();
        else {
          const heading = document.querySelector("#needs-heading");
          heading.tabIndex = -1;
          heading.focus();
        }
      }
    }
    state.ownedDrafts = ownedDrafts;
    const openAnswer = overlayRoot.querySelector('[data-action="resolve"]');
    if (openAnswer) {
      const current = pending.find((item) => item.authorization_id === openAnswer.dataset.id);
      if (!current || new Date(current.expires_at).getTime() <= Date.now()) {
        overlayRoot.querySelectorAll('[data-action="resolve"]').forEach((button) => { button.disabled = true; });
        const deadline = overlayRoot.querySelector("#pending-deadline");
        if (deadline) deadline.textContent = "This decision window has closed. Refresh Wallet for the final outcome.";
      }
    }
    const count = pending.length + ownedDrafts.filter((item) => item.state === "proposed").length;
    const heading = document.querySelector("#needs-heading");
    const title = needsHeading(count);
    if (heading.textContent !== title) heading.textContent = title;
    const empty = document.querySelector("#needs-empty");
    if (!empty) throw new Error("The Wallet inbox summary is missing.");
    empty.hidden = Boolean(count);
    empty.textContent = ownedDrafts.some((item) => item.state === "confirming") ? "Your confirmation is being checked. It will appear as confirmed when the backend accepts it." : "Spending requests and purchases that need a decision will appear here.";
    document.querySelector("#wallet-indicator").hidden = !count;
    return true;
  } catch (error) {
    if (request !== state.pendingSerial || route !== state.serial || !container.isConnected) return;
    if (error.status === 401) { sessionExpired(error); return; }
    window.clearTimeout(state.timer);
    state.timer = null;
    state.pending = [];
    closeOverlay();
    container.innerHTML = errorPanel("Pending purchases could not be refreshed", error);
    return false;
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
  const items = validateMandateList(await walletApi.mandates());
  if (serial !== state.serial) return "";
  state.ownedMandates = items;
  if (!items.length) {
    state.mandate = null;
    return `<div class="wallet-section"><h2>No confirmed spending permissions</h2><p class="calm-copy">An external shopping agent can send you a spending plan. Your Wallet will ask you to approve it.</p><button type="button" class="outline-button" data-route="shop">Go to Shop</button></div>`;
  }
  const id = mandateId();
  const selected = items.find((item) => item.mandate_id === id);
  let detail = `<p class="calm-copy">${id ? "Your saved selection is unavailable to this account. Choose a permission below." : "Choose a permission to see its current limits and recorded spend."}</p>`;
  state.mandate = null;
  if (selected) {
    const response = await walletApi.mandate(id);
    if (serial !== state.serial) return "";
    const payload = validateMandate(response);
    if (payload.mandate.mandate_id !== id) throw new Error("The selected permission does not match the Wallet response.");
    state.mandate = payload;
    const { mandate, draft, effective_policy, state: usage } = payload;
    const cap = purchaseCap(effective_policy.rules);
    detail = `<section class="permission-card"><span class="section-kicker">${esc(mandate.status.toUpperCase())}</span><h3>${esc(productName(draft))}</h3><strong>${cap ? esc(money(cap.amount)) : "No per-purchase amount limit"}</strong><p>${cap ? cap.strict ? "Each purchase must stay below this amount." : "Maximum per purchase." : "Review the confirmed rules before your agent shops."}</p><div class="permission-stats"><span>Approved purchases</span><b>${usage.approvals.length}</b><span>Approved spend</span><b>${esc(money(usage.approvals.reduce((sum, entry) => sum + entry.amount_chf, 0)))}</b></div></section><p class="calm-copy">${mandate.status === "active" ? "Only the rules you confirmed grant purchasing authority." : `This permission is ${esc(mandate.status)} and cannot authorize new purchases.`}</p><button type="button" class="text-button" data-action="wallet-tab" data-tab="rules">View current rules <span aria-hidden="true">→</span></button>`;
  }
  return `<div class="wallet-section"><h2>Spending permissions</h2>${detail}<section class="permission-list"><h3>All permissions</h3>${mandateChoices(items, selected?.mandate_id)}</section></div>`;
}

function globalPolicyCard(policy, savedGlobal) {
  let notice = "";
  if (!savedGlobal) notice = "";
  else if (savedGlobal.version < policy.version) notice = `This permission uses version ${savedGlobal.version}. Version ${policy.version} will apply to your next confirmed permission.`;
  else if (savedGlobal.version > policy.version) notice = `This permission was confirmed with version ${savedGlobal.version}, but the current account-wide record reports version ${policy.version}. Check the saved rules before another confirmation.`;
  else if (savedGlobal.hash !== policy.hash) notice = `This permission and the current account-wide record both report version ${policy.version}, but their rule hashes differ. Check the saved rules before another confirmation.`;
  const capRules = policy.rules.filter((rule) => rule.field === "authorization.billing_amount_chf" && rule.scope === "period" && rule.period_days === 7);
  const editable = capRules.length === 0 || (capRules.length === 1 && capRules[0].operator === "<=" && capRules[0].currency === "CHF" && typeof capRules[0].value === "number");
  const cap = capRules.length ? capRules[0] : null;
  const editor = editable ? `<div class="global-cap-editor"><label for="global-seven-day-cap">Seven-day approved spend cap (CHF)</label><input id="global-seven-day-cap" type="number" min="0.01" step="0.01" inputmode="decimal" value="${cap ? esc(cap.value) : ""}" placeholder="No cap" /><p>Counts approved purchases across your permissions over the previous seven days, plus the proposed purchase.</p><div class="global-cap-actions"><button type="button" class="outline-button" data-action="save-global-cap">Save cap</button>${cap ? `<button type="button" class="danger-link" data-action="remove-global-cap">Remove cap</button>` : ""}</div></div>` : `<p>This account has a seven-day rule that needs a different editor. Its saved value is shown above.</p>`;
  return `<section class="rule-group"><h3>Account-wide rules · version ${policy.version}</h3>${policy.rules.length ? policy.rules.map((rule) => `<div class="rule-item"><span class="rule-check" aria-hidden="true">✓</span><span>${esc(rule.plain_english)}</span></div>`).join("") : `<p>No account-wide rules are saved for this local customer.</p>`}<p>${notice ? `${esc(notice)} ` : ""}Changes apply to the next confirmed permission. Existing permissions keep their saved rules.</p>${editor}<button type="button" class="outline-button" data-action="open-global-rules">Edit all account-wide rules</button></section>`;
}

function stagedGlobalRuleLabel(rule) {
  if (rule.plain_english) return text(rule.plain_english, "Account-wide rule description");
  if (rule.field === "authorization.billing_amount_chf") return rule.scope === "period" ? `Up to ${money(rule.value)} in ${rule.period_days} days across your permissions.` : `Up to ${money(rule.value)} for each purchase.`;
  if (rule.field === "state.approvals_count" && rule.scope === "period") return `Up to ${rule.value} accepted purchases in ${rule.period_days} days across your permissions.`;
  throw new Error("The staged account-wide rule has no supported description.");
}

function showGlobalEditor() {
  const policy = state.globalPolicy;
  const rules = state.stagedGlobalRules;
  if (!policy || policy.customer !== state.accountId || !Array.isArray(rules)) throw new Error("The account-wide rules are not ready for editing.");
  const changed = JSON.stringify(rules) !== JSON.stringify(policy.rules);
  const rows = rules.length ? rules.map((rule, index) => `<div class="global-rule-row"><span>${esc(stagedGlobalRuleLabel(rule))}</span><button type="button" class="text-button" data-action="remove-global-rule" data-index="${index}" aria-label="Remove rule ${index + 1}: ${esc(stagedGlobalRuleLabel(rule))}">Remove</button></div>`).join("") : `<p>${policy.rules.length ? "Saving this empty draft will remove all account-wide rules for future confirmations." : "No account-wide rules are saved."}</p>`;
  openOverlay(`<span class="section-kicker">ACCOUNT-WIDE RULES · VERSION ${policy.version}</span><h2>Edit future spending limits</h2><p class="overlay-intro">These edits affect only permissions you confirm later. Existing permissions keep their saved rules. Nothing changes until you save the full list.</p><div class="global-rule-list">${rows}</div><div class="global-rule-form"><h3>Add a limit</h3><label for="global-control">Limit type</label><select id="global-control"><option value="purchase_amount">Maximum per purchase, CHF</option><option value="rolling_amount">Rolling spending cap, CHF</option><option value="rolling_count">Rolling purchase count</option></select><label for="global-value" id="global-value-label">Maximum CHF</label><input id="global-value" type="number" min="0.01" step="0.01" inputmode="decimal" /><div id="global-days-wrap" hidden><label for="global-days">Window in days</label><input id="global-days" type="number" min="1" step="1" inputmode="numeric" disabled /></div><button type="button" class="outline-button" data-action="stage-global-rule">Add to draft</button></div><p id="global-rule-error" class="global-rule-error" role="alert" hidden></p><div class="global-rule-actions"><button type="button" class="outline-button" data-action="close-overlay">Cancel</button><button type="button" class="primary-button" data-action="save-global-rules" ${!changed || state.globalConflict ? "disabled" : ""}>Save all rules</button></div><button type="button" class="text-button" data-action="reload-global-rules" ${state.globalConflict ? "" : "hidden"}>Reload current rules</button>`, "Edit account-wide rules");
}

function showGlobalEditorError(message, conflict = false) {
  const alert = overlayRoot.querySelector("#global-rule-error");
  if (!alert) throw new Error("The account-wide rule editor is unavailable.");
  alert.textContent = message;
  alert.hidden = false;
  if (conflict) {
    state.globalConflict = true;
    overlayRoot.querySelectorAll('[data-action="save-global-rules"], [data-action="remove-global-rule"], [data-action="stage-global-rule"], .global-rule-form input, .global-rule-form select').forEach((control) => { control.disabled = true; });
    const reload = overlayRoot.querySelector('[data-action="reload-global-rules"]');
    reload.hidden = false;
    reload.focus();
  }
}

function stageGlobalRule() {
  const control = globalControls[document.querySelector("#global-control").value];
  if (!control) throw new Error("Choose a supported account-wide limit.");
  const raw = document.querySelector("#global-value").value.trim();
  const count = control.field === "state.approvals_count";
  if (!(count ? /^[1-9]\d*$/.test(raw) : /^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/.test(raw)) || !Number.isFinite(Number(raw)) || Number(raw) <= 0 || (count && !Number.isSafeInteger(Number(raw)))) {
    showGlobalEditorError(count ? "Enter a positive whole number of purchases." : "Enter a positive CHF amount with at most two decimal places.");
    return;
  }
  const days = document.querySelector("#global-days").value.trim();
  if (control.scope === "period" && (!/^[1-9]\d*$/.test(days) || !Number.isSafeInteger(Number(days)))) {
    showGlobalEditorError("Enter a positive whole number of days.");
    return;
  }
  const rule = { field: control.field, operator: control.operator, value: Number(raw), scope: control.scope, source_text: `Wallet ${control.label}` };
  if (control.currency) rule.currency = control.currency;
  if (control.scope === "period") rule.period_days = Number(days);
  if (state.stagedGlobalRules.some((item) => item.field === rule.field && (item.scope || "purchase") === rule.scope && item.period_days === rule.period_days)) {
    showGlobalEditorError("A limit for this field and window already exists. Remove it before adding another.");
    return;
  }
  state.stagedGlobalRules.push(rule);
  showGlobalEditor();
}

async function saveGlobalRules() {
  const policy = state.globalPolicy;
  if (!policy || policy.customer !== state.accountId || !state.stagedGlobalRules || state.globalConflict) throw new Error("Reload your account-wide rules before saving.");
  if (JSON.stringify(state.stagedGlobalRules) === JSON.stringify(policy.rules)) throw new Error("No account-wide rule changes are staged.");
  const accepted = validateGlobalPolicy(await walletApi.saveGlobalPolicy(policy.version, policy.hash, state.stagedGlobalRules));
  if (accepted.version !== policy.version + 1) throw new Error("The account-wide rules were not acknowledged at a new version. Reload them before another edit.");
  state.globalPolicy = accepted;
  state.stagedGlobalRules = null;
  closeOverlay();
  state.walletTab = "rules";
  await navigate("wallet");
  toast(`Account-wide rules saved as version ${accepted.version}. Future confirmations use this version.`, "success");
}

async function rulesContent(serial) {
  const [items, globalPolicy] = await Promise.all([
    walletApi.mandates().then(validateMandateList),
    walletApi.globalPolicy().then(validateGlobalPolicy),
  ]);
  if (serial !== state.serial) return "";
  state.ownedMandates = items;
  state.globalPolicy = globalPolicy;
  const id = mandateId();
  const selected = items.find((item) => item.mandate_id === id);
  let detail = `<p class="calm-copy">${items.length ? "Select a permission below to inspect its confirmed rules." : "You have no confirmed permission to inspect."}</p>`;
  let savedGlobal = null;
  state.mandate = null;
  if (selected) {
    const response = await walletApi.mandate(id);
    if (serial !== state.serial) return "";
    const payload = validateMandate(response);
    if (payload.mandate.mandate_id !== id || payload.global_policy_version !== selected.global_policy_version || payload.global_policy_hash !== selected.global_policy_hash) throw new Error("The selected permission does not match the Wallet list.");
    savedGlobal = { version: payload.global_policy_version, hash: payload.global_policy_hash };
    state.mandate = payload;
    const { mandate, effective_policy } = payload;
    detail = `<p class="calm-copy">These are the effective rules saved on the selected permission. Later account-wide changes apply to the next confirmation.</p><h3 class="rule-section-heading">Effective rules for this permission</h3>${ruleGroups(effective_policy.rules)}<section class="rule-group"><h3>Missing information</h3><p>${esc(effective_policy.uncertainty_policy === "ask" ? "Ask me before buying" : effective_policy.uncertainty_policy === "decline" ? "Decline the purchase" : "Allow the purchase when evidence is missing")}</p></section><section class="rule-group"><h3>Security</h3><p>Purchase decisions and unfamiliar evidence are checked by the Wallet backend. Your agent cannot change these confirmed rules.</p></section><div class="rule-actions"><button type="button" class="outline-button" data-action="open-tighten" ${mandate.status !== "active" || effective_policy.uncertainty_policy === "decline" ? "disabled" : ""}>Decline uncertain purchases</button><button type="button" class="danger-link" data-action="open-revoke" ${mandate.status !== "active" ? "disabled" : ""}>Revoke this permission</button></div>`;
  }
  return `<div class="wallet-section"><h2>Rules for your permissions</h2>${detail}${globalPolicyCard(globalPolicy, savedGlobal)}${items.length ? `<section class="permission-list"><h3>Choose a permission</h3>${mandateChoices(items, selected?.mandate_id, "rules")}</section>` : ""}</div>`;
}

function boundaryResultCards(evaluation) {
  if (!evaluation.results.length) return `<section class="boundary-results"><h2>Checked purchase cases</h2><p>This plan has no computed purchase cases. Agent-authored examples, when present, are illustrative.</p></section>`;
  return `<section class="boundary-results"><h2>Checked purchase cases</h2><p>The agent authored these synthetic purchase cases. The Wallet backend evaluated them. No live purchase is shown here.</p><p class="boundary-meta">Checked on ${esc(new Date(evaluation.evaluated_at).toLocaleString("en-CH"))} at ${esc(evaluation.phase)} · engine ${esc(evaluation.engine_version)}</p><div class="boundary-list">${evaluation.results.map((item, index) => `<article class="boundary-card"><span class="boundary-number">CASE ${index + 1}</span><h3>${esc(item.description)}</h3><p>Agent expected: <strong>${esc(item.expected)}</strong></p><p>Backend computed: <strong>${esc(item.observed)}</strong></p>${item.reason_codes.length ? `<p class="boundary-reasons">Reason codes: ${item.reason_codes.map(esc).join(", ")}</p>` : ""}</article>`).join("")}</div></section>`;
}

async function renderReview(serial) {
  loading("Loading saved spending plan…");
  const id = text(linkedDraftId(), "Draft link");
  const [draft, ownedDrafts] = await Promise.all([
    walletApi.draft(id).then(validateDraft),
    walletApi.drafts().then(validateDraftList),
  ]);
  if (serial !== state.serial) return;
  if (state.draft?.draft_id !== id || state.draft.version !== draft.version || state.draft.hash !== draft.hash) state.answers = {};
  state.draft = draft;
  state.ownedDrafts = ownedDrafts;
  const recorded = ownedDrafts.find((item) => item.draft_id === id);
  if (!recorded || recorded.version !== draft.version || recorded.hash !== draft.hash) throw new Error("The spending request does not match your account's saved list.");
  if (recorded.state !== "proposed") {
    const message = recorded.state === "confirmed" ? "This request was confirmed. Review its current permission in Wallet." : recorded.state === "rejected" ? "This request was rejected and cannot be authorized." : "Confirmation is in progress. The Wallet will show the result when the backend accepts it.";
    setScreen(`<section class="review-view"><button class="back-button" type="button" data-route="wallet">‹ Wallet</button><div class="page-title"><h1>Spending request ${esc(recorded.state)}</h1></div><p class="review-subtitle">${esc(message)}</p>${recorded.state === "confirmed" ? `<button class="outline-button" type="button" data-action="select-mandate" data-id="${esc(recorded.mandate_id)}" data-tab="active">View permission</button>` : ""}</section>`);
    return;
  }
  const evaluation = validateBoundaryResults(await walletApi.boundaryResults(id), draft);
  if (serial !== state.serial) return;
  const cap = purchaseCap(draft.rules);
  const questions = draft.open_questions;
  const ready = questions.every((question) => question.confirming_answers.includes(state.answers[question.question] ?? question.answer));
  const needsRevision = questions.some((question) => {
    const answer = state.answers[question.question] ?? question.answer;
    return answer && !question.confirming_answers.includes(answer);
  });
  setScreen(`<section class="review-view"><button class="back-button" type="button" data-route="wallet">‹ Wallet</button><div class="page-title"><h1>Review spending permission</h1></div><p class="review-subtitle">Your Wallet loaded the plan saved by your shopping agent. Only you can authorize it.<span class="review-version">Saved draft version ${esc(draft.version)}.</span></p><section class="review-summary"><span class="section-kicker">YOUR AGENT MAY BUY</span><h2>${esc(productName(draft))}</h2><strong>${cap ? esc(money(cap.amount)) : "No per-purchase cap"}</strong><small>${cap ? cap.strict ? "SPEND MUST STAY BELOW THIS AMOUNT" : "MAXIMUM PER PURCHASE" : "REVIEW ALL RULES BEFORE AUTHORIZING"}</small></section><section class="review-rules"><h2>The limits you'll authorize</h2>${ruleGroups(draft.rules)}<details><summary>Original request</summary><p>${esc(draft.instruction)}</p></details></section>${boundaryResultCards(evaluation)}${draft.examples.length ? `<section class="agent-examples"><details><summary>Agent-authored examples</summary><p>These descriptions are the agent's claims. The Wallet has not computed their outcomes.</p>${draft.examples.map((example) => `<p><strong>${esc(example.expected)}</strong> · ${esc(example.description)}. ${esc(example.why)}</p>`).join("")}</details></section>` : ""}
    ${questions.length ? `<section class="questions"><h2>Confirm these details</h2>${questions.map((question) => { const selected = state.answers[question.question] ?? question.answer; return `<div class="question"><strong>${esc(question.question)}</strong><div class="choices">${question.options.map((option) => `<button type="button" class="${selected === option ? "selected" : ""}" aria-pressed="${selected === option}" data-action="answer-question" data-question="${esc(question.question)}" data-answer="${esc(option)}">${esc(option)}</button>`).join("")}</div></div>`; }).join("")}${needsRevision ? `<p class="uncertainty-note">Your selection requires a revised plan from the shopping agent before authorization.</p>` : ""}</section>` : ""}<div class="review-spacer"></div><div class="review-actions"><button type="button" class="outline-button" data-action="open-reject">Reject</button><button type="button" class="primary-button" data-action="confirm" ${ready ? "" : "disabled"}>Authorize agent</button></div></section>`);
}

function decisionLabel(decision) {
  if (decision.decision === "approve") return decision.reason_codes.includes("customer_confirmation") ? "Approved after review" : "Approved";
  if (decision.decision === "decline") {
    if (decision.reason_codes.includes("customer_declined")) return "Declined after review";
    if (decision.reason_codes.includes("step_up_timeout")) return "Timed out and declined";
    return "Blocked";
  }
  return "Needs a decision";
}

function activityTabs() {
  return `<div class="activity-tabs" role="tablist" aria-label="Filter decisions">${[["all", "All"], ["purchases", "Purchases"], ["blocked", "Declined"]].map(([id, label]) => `<button type="button" role="tab" tabindex="${state.activityFilter === id ? 0 : -1}" aria-selected="${state.activityFilter === id}" class="${state.activityFilter === id ? "selected" : ""}" data-action="activity-filter" data-filter="${id}">${label}</button>`).join("")}</div>`;
}

function activityRows() {
  const filtered = state.history.filter(({ decision }) => state.activityFilter === "all" || (state.activityFilter === "purchases" ? decision.decision === "approve" : decision.decision === "decline"));
  if (!filtered.length) return `<section class="wallet-empty"><h2>No ${state.activityFilter === "all" ? "decisions" : state.activityFilter === "blocked" ? "declines" : "purchases"} yet</h2><p>Decisions for this permission will appear here after the backend records them.</p></section>`;
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
    const label = decisionLabel(decision);
    const kind = decision.decision === "approve" ? "approved" : decision.decision === "decline" ? "blocked" : "uncertain";
    return `${heading}<button type="button" class="activity-card" data-action="open-detail" data-id="${esc(decision.authorization_id)}"><span class="activity-card-top"><span class="outcome-icon ${kind}" aria-hidden="true">${decision.decision === "approve" ? "✓" : decision.decision === "decline" ? "×" : "?"}</span><strong>${esc(merchant)}</strong><b>${esc(money(auth.billing_amount_chf, auth.currency))}</b></span><span class="activity-product">${esc(item)}</span><span class="activity-card-bottom"><span class="${kind}">${esc(label)}</span><time datetime="${esc(decision.decided_at)}">${esc(new Date(decision.decided_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" }))}</time></span></button>`;
  }).join("");
}

async function renderActivity(serial) {
  const id = mandateId();
  if (!id) { setScreen(`<section class="activity-view"><div class="page-title"><h1>Activity</h1></div><p class="calm-copy">Choose a spending permission in Wallet to see its recorded purchase decisions.</p><button type="button" class="outline-button" data-action="wallet-tab" data-tab="active">Choose a permission</button></section>`); return; }
  loading("Loading recorded decisions…");
  const response = await walletApi.mandate(id);
  if (serial !== state.serial) return;
  const permission = validateMandate(response);
  if (permission.mandate.mandate_id !== id) throw new Error("The selected permission does not match the Wallet response.");
  const history = await walletApi.history(id);
  if (!Array.isArray(history)) throw new Error("The Wallet did not return a decision history.");
  history.forEach((entry) => {
    if (!entry?.decision || !entry.state_after) throw new Error("A history entry is incomplete.");
    text(entry.decision.authorization_id, "History authorization ID");
  });
  if (new Set(history.map((entry) => entry.decision.authorization_id)).size !== history.length) throw new Error("The decision history contains duplicate purchase outcomes.");
  const details = await Promise.all(history.map(({ decision }) => walletApi.decision(decision.authorization_id).then(validateDecision)));
  if (serial !== state.serial) return;
  state.history = history.map((entry, index) => {
    if (entry.decision.authorization_id !== details[index].decision.authorization_id) throw new Error("The decision history and transaction detail refer to different purchases.");
    return { decision: details[index].decision, state_after: details[index].state_after };
  })
    .sort((a, b) => new Date(b.decision.decided_at) - new Date(a.decision.decided_at));
  state.details = new Map(details.map((detail) => [detail.decision.authorization_id, detail]));
  setScreen(`<section class="activity-view"><div class="page-title"><h1>Activity</h1></div><p class="calm-copy">For ${esc(productName(permission.draft))}</p><button type="button" class="text-button" data-action="wallet-tab" data-tab="active">Change permission <span aria-hidden="true">→</span></button>${activityTabs()}<div id="activity-list">${activityRows()}</div><p class="activity-disclaimer">Recorded purchase decisions for the selected permission. Permission changes are not in this history.</p></section>`);
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
  openOverlay(`<span class="section-kicker amber-text">VISECA NEEDS YOU</span><h2>${esc(pendingTitle(item.decision.evidence))}</h2><p class="overlay-intro">${esc(item.decision.customer_message)}</p><div class="purchase-highlight"><span>${esc(auth.merchant.merchant_name)}</span><strong>${esc(money(auth.billing_amount_chf, auth.currency))}</strong><p>${esc(auth.items.map((entry) => text(entry.item_name, "Item")).join(" + "))}</p></div><h3>Why you're seeing this</h3><div class="evidence-list">${issue.map((check) => `<div class="evidence-card ${check.result}"><span>${check.result === "fail" ? "×" : "?"}</span><div><strong>${esc(check.name.replaceAll("_", " "))}</strong><p>${esc(check.note)}</p><small>Source: ${esc(check.source)}</small></div></div>`).join("")}</div><p class="calm-copy">This answer applies only to this purchase. It does not change your confirmed limits.</p><p id="pending-deadline" class="calm-copy">${remaining > 0 ? `Decision window: ${Math.floor(remaining / 60000)}m ${String(Math.floor(remaining / 1000) % 60).padStart(2, "0")}s left` : "The decision window has closed."}</p><div class="overlay-actions"><button class="outline-button" type="button" data-action="resolve" data-id="${esc(id)}" data-decision="decline" ${remaining <= 0 ? "disabled" : ""}>Don't buy</button><button class="primary-button" type="button" data-action="resolve" data-id="${esc(id)}" data-decision="approve" ${remaining <= 0 ? "disabled" : ""}>Buy anyway</button></div>${remaining <= 0 ? `<p class="uncertainty-note">The decision window has closed. Refresh Wallet for the final result.</p>` : ""}`, "Purchase review");
}

function openDetail(payload) {
  state.detail = validateDecision(payload);
  const { decision, event } = payload;
  const auth = event.authorization;
  const failed = decision.evidence.filter((check) => check.result === "fail");
  const uncertain = decision.evidence.filter((check) => check.result === "uncertain");
  const title = decision.decision === "approve" ? "Why was this approved?" :
    decision.decision === "step_up" ? "Why does this need a decision?" :
    decision.reason_codes.includes("customer_declined") ? "Why was this declined?" :
    decision.reason_codes.includes("step_up_timeout") ? "Why did this purchase time out?" : "Why was this blocked?";
  openOverlay(`<span class="section-kicker">TRANSACTION</span><h2>${esc(title)}</h2><div class="purchase-highlight"><span>${esc(auth.merchant.merchant_name)}</span><strong>${esc(money(auth.billing_amount_chf, auth.currency))}</strong><p>${esc(auth.items.map((entry) => text(entry.item_name, "Item")).join(" + "))}</p></div><p class="overlay-intro">${esc(decision.customer_message)}</p>${failed.length || uncertain.length ? `<div class="evidence-list">${[...failed, ...uncertain].slice(0, 4).map((check) => `<div class="evidence-card ${check.result}"><span>${check.result === "fail" ? "×" : "?"}</span><div><strong>${esc(check.name.replaceAll("_", " "))}</strong><p>${esc(check.note)}</p></div></div>`).join("")}</div>` : ""}<button type="button" class="text-button" data-action="inspector" data-tab="summary">View technical details <span aria-hidden="true">→</span></button>`, "Transaction explanation");
}

function inspector(tab) {
  if (!state.detail) throw new Error("The transaction details are not loaded.");
  if (!["summary", "checks", "record"].includes(tab)) throw new Error("Unknown inspector section.");
  const { decision, event, state_before, state_after } = state.detail;
  const status = decisionLabel(decision);
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
  window.sessionStorage.setItem(MANDATE_OWNER_KEY, text(state.accountId, "Current account ID"));
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
  state.pendingSerial += 1;
  window.clearTimeout(state.timer);
  state.timer = null;
  overlayRoot.querySelectorAll('[data-action="resolve"]').forEach((action) => { action.disabled = true; });
  await walletApi.answer(id, decision);
  closeOverlay();
  toast(decision === "approve" ? "Your answer was accepted for this purchase." : "Your decline was accepted for this purchase.", "success");
  if (state.route === "purchase") { navigate("wallet"); return; }
  const refreshed = await refreshPending();
  if (refreshed) schedulePendingRefresh();
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
  if (action !== "open-detail") state.detailSerial += 1;
  try {
    if (action === "close-overlay") {
      if (button === event.target || button.classList.contains("overlay-close") || event.target.classList.contains("overlay-backdrop")) closeOverlay();
      return;
    }
    if (action === "wallet-tab") { state.walletTab = button.dataset.tab; navigate("wallet", { keepScroll: true }); return; }
    if (action === "activity-filter") { state.activityFilter = button.dataset.filter; document.querySelector("#activity-list").innerHTML = activityRows(); document.querySelectorAll(".activity-tabs [role=tab]").forEach((tab) => { const active = tab === button; tab.classList.toggle("selected", active); tab.setAttribute("aria-selected", String(active)); tab.tabIndex = active ? 0 : -1; }); return; }
    if (action === "auth-mode") { if (!["login", "register"].includes(button.dataset.mode)) throw new Error("Unknown account action."); state.authMode = button.dataset.mode; renderLogin(); return; }
    if (action === "clear-pair-code") {
      const input = document.querySelector("#pair-code");
      const error = document.querySelector("#pair-code-error");
      input.value = "";
      error.textContent = "";
      error.hidden = true;
      state.pairLinkError = null;
      input.focus();
      return;
    }
    if (action === "submit-pair-code") {
      const input = document.querySelector("#pair-code");
      const code = input.value.trim();
      if (!code || code.length > 128 || /\s/.test(code)) {
        const error = document.querySelector("#pair-code-error");
        error.textContent = "Enter a code without spaces.";
        error.hidden = false;
        input.focus();
        return;
      }
      state.pairCode = code;
      state.pairLinkError = null;
      await navigate("pair");
      return;
    }
    if (action === "decline-pair") { clearPairLink(); navigate(requestedRoute("")); return; }
    if (action === "refresh-agents") { void render(); return; }
    if (action === "open-global-rules") {
      if (state.route !== "wallet" || state.walletTab !== "rules" || !state.globalPolicy) throw new Error("Load account-wide rules before editing them.");
      state.stagedGlobalRules = state.globalPolicy.rules.map((rule) => ({ ...rule }));
      state.globalConflict = false;
      showGlobalEditor();
      return;
    }
    if (action === "remove-global-rule") {
      const index = Number(button.dataset.index);
      if (!state.stagedGlobalRules || !Number.isInteger(index) || index < 0 || index >= state.stagedGlobalRules.length) throw new Error("The account-wide rule to remove is unavailable.");
      state.stagedGlobalRules.splice(index, 1);
      showGlobalEditor();
      return;
    }
    if (action === "stage-global-rule") { stageGlobalRule(); return; }
    if (action === "reload-global-rules") {
      state.stagedGlobalRules = null;
      state.globalConflict = false;
      state.walletTab = "rules";
      await navigate("wallet");
      return;
    }
    if (action === "open-draft") {
      const id = text(button.dataset.id, "Spending request ID");
      if (!state.ownedDrafts.some((item) => item.draft_id === id && item.state === "proposed")) throw new Error("This spending request is no longer ready for review.");
      const url = new URL(window.location.href);
      url.searchParams.delete("draft");
      url.searchParams.delete("pair");
      url.searchParams.set("draft_id", id);
      window.history.replaceState(null, "", url.pathname + url.search + url.hash);
      navigate("review");
      return;
    }
    if (action === "open-agent-revoke") {
      const agent = state.agents.find((item) => item.agent_id === button.dataset.id && item.revoked_at === null);
      if (!agent) throw new Error("This connected agent is no longer available to revoke.");
      openOverlay(`<span class="section-kicker">CONNECTED AGENT</span><h2>Revoke ${esc(agent.agent_label)}?</h2><p class="overlay-intro">This stops future tool calls from this agent. It does not change permissions you have already confirmed.</p><div class="overlay-actions"><button type="button" class="outline-button" data-action="close-overlay">Cancel</button><button type="button" class="primary-button" data-action="revoke-agent" data-id="${esc(agent.agent_id)}">Revoke access</button></div>`, "Revoke agent access");
      return;
    }
    if (action === "use-example") { const composer = document.querySelector("#shop-prompt"); composer.value = text(button.dataset.example, "Example request"); state.prompt = composer.value; composer.focus(); composer.dispatchEvent(new Event("input", { bubbles: true })); return; }
    if (action === "account") { openOverlay(`<span class="section-kicker">LOCAL DEMO ACCOUNT</span><h2>${esc(state.user || "Sign in")}</h2><p class="calm-copy">This demo uses a local password account and session cookie. It is not a Viseca banking login.</p>${state.user ? `<div class="agent-actions"><button type="button" class="outline-button" data-route="pair">Connect agent</button><button type="button" class="outline-button" data-route="agents">Connected agents</button><button type="button" class="outline-button" data-action="logout">Sign out</button></div>` : `<button type="button" class="outline-button" data-action="close-overlay">Close</button>`}`, "Account"); return; }
    if (action === "open-pending") { openPending(button.dataset.id); return; }
    if (action === "inspector") { inspector(button.dataset.tab); return; }
    if (action === "open-reject") { confirmDialog("Reject this spending plan?", "Your agent will not receive authority from this request.", "reject", "Reject request"); return; }
    if (action === "open-tighten") { confirmDialog("Decline uncertain purchases?", "Future purchases with missing evidence will be declined instead of asking you.", "tighten", "Decline uncertainty"); return; }
    if (action === "open-revoke") { confirmDialog("Revoke this permission?", "Your shopping agent will no longer be able to use it.", "revoke", "Revoke permission"); return; }
    if (action === "answer-question") { state.answers[button.dataset.question] = button.dataset.answer; await renderReview(state.serial); return; }
    if (action === "open-detail") {
      const id = button.dataset.id;
      const screenAtClick = state.serial;
      const request = ++state.detailSerial;
      let detail;
      try {
        detail = validateDecision(await walletApi.decision(id));
      } catch (error) {
        if (request !== state.detailSerial || screenAtClick !== state.serial) return;
        throw error;
      }
      if (request !== state.detailSerial || screenAtClick !== state.serial || state.route !== "activity") return;
      if (detail.decision.authorization_id !== id) throw new Error("The transaction detail does not match the selected purchase.");
      state.details.set(id, detail);
      const entry = state.history.find((item) => item.decision.authorization_id === id);
      if (!entry) throw new Error("This purchase is no longer in the current history.");
      if (entry.decision.decision !== detail.decision.decision || entry.decision.decided_at !== detail.decision.decided_at) {
        entry.decision = detail.decision;
        entry.state_after = detail.state_after;
        state.history.sort((a, b) => new Date(b.decision.decided_at) - new Date(a.decision.decided_at));
        document.querySelector("#activity-list").innerHTML = activityRows();
        const updated = [...document.querySelectorAll('[data-action="open-detail"]')].find((item) => item.dataset.id === id);
        if (updated) updated.focus();
        else document.querySelector('.activity-tabs [aria-selected="true"]').focus();
      }
      openDetail(detail);
      return;
    }
    if (action === "reload") { if (state.user) void render(); else void initialize(); return; }
    if (action === "clear-invalid-link") {
      const purchase = state.route === "purchase";
      if (state.route === "pair") clearPairLink();
      else if (purchase) clearPurchaseLink();
      else clearDraftLink();
      await navigate(requestedRoute(""));
      if (purchase && state.route === "shop") {
        const heading = screen.querySelector(".shop-view h1");
        if (!heading) throw new Error("The Shop heading is missing after leaving a purchase link.");
        heading.tabIndex = -1;
        heading.focus();
      }
      return;
    }
    button.disabled = true;
    if (action === "select-mandate") {
      const id = text(button.dataset.id, "Selected permission ID");
      const tab = button.dataset.tab;
      if (!["active", "rules"].includes(tab)) throw new Error("Unknown permission destination.");
      const routeSerial = state.serial;
      const response = await walletApi.mandate(id);
      if (routeSerial !== state.serial || !state.user) return;
      const payload = validateMandate(response);
      if (payload.mandate.mandate_id !== id) throw new Error("The selected permission does not match the Wallet response.");
      window.sessionStorage.setItem(MANDATE_KEY, id);
      window.sessionStorage.setItem(MANDATE_OWNER_KEY, text(state.accountId, "Current account ID"));
      state.mandate = payload;
      state.walletTab = tab;
      navigate("wallet");
    } else if (action === "login" || action === "register") {
      const username = text(document.querySelector("#username").value.trim(), "Username");
      const password = document.querySelector("#password").value;
      if (password.length < 8 || password.length > 256) throw new Error("Password must have 8 to 256 characters.");
      setSession(action === "register" ? await walletApi.register(username, password) : await walletApi.login(username, password));
      navigate(requestedRoute());
    } else if (action === "logout") {
      await walletApi.logout();
      clearPairLink();
      window.sessionStorage.removeItem(MANDATE_KEY);
      window.sessionStorage.removeItem(MANDATE_OWNER_KEY);
      state.pendingSerial += 1;
      window.clearTimeout(state.timer);
      window.clearInterval(state.pairTimer);
      window.clearTimeout(state.exampleTimer);
      state.pairTimer = null;
      state.serial += 1;
      state.user = null;
      state.accountId = null;
      state.authMode = "login";
      state.mandate = null;
      state.globalPolicy = null;
      state.ownedMandates = [];
      state.stagedGlobalRules = null;
      state.globalConflict = false;
      state.agents = [];
      state.pairing = null;
      state.pairingCode = null;
      state.pending = [];
      state.draft = null;
      state.ownedDrafts = [];
      state.answers = {};
      state.history = [];
      state.detail = null;
      state.prompt = "";
      state.extraDetails = "";
      state.details.clear();
      document.querySelector("#wallet-indicator").hidden = true;
      closeOverlay();
      renderLogin();
    } else if (action === "approve-pending-pair") {
      const id = button.dataset.id;
      await walletApi.approvePendingPairing(id);
      state.pairings = null;
      toast("Agent connected. It will continue on its own.", "success");
      await refreshPending();
    } else if (action === "approve-pair") {
      const code = pairingCode();
      if (code !== state.pairingCode || !state.pairing || validTime(state.pairing.expires_at, "Connection expiry") <= Date.now()) throw new Error("The agent connection link has expired or changed. Reload it before approving.");
      await walletApi.approvePairing(code);
      clearPairLink();
      navigate(requestedRoute(""));
      toast("Connection approved. Return to your agent to finish pairing.", "success");
    } else if (action === "revoke-agent") {
      const id = text(button.dataset.id, "Agent ID");
      if (!state.agents.some((agent) => agent.agent_id === id && agent.revoked_at === null)) throw new Error("This agent is no longer active in your Wallet.");
      const updated = validateAgentList([await walletApi.revokeAgent(id)])[0];
      if (updated.agent_id !== id || updated.revoked_at === null) throw new Error("The agent revocation response did not confirm this agent was revoked.");
      closeOverlay();
      navigate("agents");
      toast("Agent access revoked.", "success");
    } else if (action === "save-global-cap" || action === "remove-global-cap") {
      const policy = state.globalPolicy;
      if (!policy || policy.customer !== state.accountId) throw new Error("Reload the account-wide rules before changing them.");
      const otherRules = policy.rules.filter((rule) => !(rule.field === "authorization.billing_amount_chf" && rule.scope === "period" && rule.period_days === 7));
      if (policy.rules.length - otherRules.length > 1) throw new Error("This seven-day rule needs a different editor.");
      let rules = otherRules;
      if (action === "save-global-cap") {
        const raw = document.querySelector("#global-seven-day-cap")?.value.trim();
        const amount = Number(raw);
        if (!raw || !/^\d+(?:\.\d{1,2})?$/.test(raw) || !Number.isFinite(amount) || amount <= 0) throw new Error("Enter a positive CHF amount with at most two decimal places.");
        rules = [...otherRules, {
          field: "authorization.billing_amount_chf", operator: "<=", value: amount,
          currency: "CHF", scope: "period", period_days: 7,
          source_text: "Account-wide seven-day approved spending cap set in Wallet",
        }];
      }
      const updated = validateGlobalPolicy(await walletApi.saveGlobalPolicy(policy.version, policy.hash, rules));
      if (updated.version !== policy.version + 1) throw new Error("The Wallet did not return the next account-wide rule version.");
      state.globalPolicy = updated;
      navigate("wallet");
      toast(action === "save-global-cap" ? "Account-wide cap saved for future permissions." : "Account-wide cap removed for future permissions.", "success");
    } else if (action === "confirm") await performConfirm();
    else if (action === "reject") await performReject();
    else if (action === "resolve") await performResolution(button);
    else if (action === "tighten") await performTighten();
    else if (action === "revoke") await performRevoke();
    else if (action === "save-global-rules") await saveGlobalRules();
    else if (action === "copy-prompt") {
      const prompt = text(document.querySelector("#shop-prompt").value.trim(), "Shopping request");
      const details = document.querySelector("#request-details").value.trim();
      const request = details ? `${prompt}\nMore details: ${details}` : prompt;
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard access requires a secure browser connection. Copy the request and any extra details manually.");
      await navigator.clipboard.writeText(request);
      button.disabled = false;
      toast("Request copied. Paste it into your connected shopping agent.", "success");
    }
  } catch (error) {
    if (action === "login" || action === "register") {
      const message = error.status === 401 && action === "login" ? "Username or password is wrong." : error.status === 409 && action === "register" ? "That username is already taken." : error.status === 429 ? "Too many sign-in attempts. Wait a minute and try again." : error.status === 422 ? "Check the username and password length, then try again." : error.message;
      const field = document.querySelector(".auth-error");
      if (field) { field.textContent = message; field.hidden = false; }
      else toast(message);
      if (button.isConnected) button.disabled = false;
      return;
    }
    if (error.status === 401) { sessionExpired(error); return; }
    if (action === "save-global-rules") {
      const conflict = error.status === 409 || !error.status;
      const message = error.status === 409 ? "Account-wide rules changed. Reload the current version before editing again. Nothing was saved from this draft." : error.status === 503 ? "The account-wide rule update timed out. No change was acknowledged. Retry manually or reload the current rules." : error.message;
      showGlobalEditorError(message, conflict);
      if (!conflict && button.isConnected) button.disabled = false;
      return;
    }
    if (error.status === 404 && action === "approve-pair") { void render(); return; }
    if (error.status === 409 && state.route === "review") { state.draft = null; state.answers = {}; void render(); }
    if (error.status === 409 && (action === "save-global-cap" || action === "remove-global-cap")) { state.globalPolicy = null; void render(); }
    toast(error.message);
    if (action === "resolve") { navigate("wallet"); return; }
    if (button.isConnected) button.disabled = false;
  }
});

document.addEventListener("change", (event) => {
  if (event.target.id !== "global-control") return;
  const control = globalControls[event.target.value];
  if (!control) throw new Error("An account-wide limit type is unsupported.");
  const count = control.field === "state.approvals_count";
  const value = document.querySelector("#global-value");
  value.value = "";
  value.min = count ? "1" : "0.01";
  value.step = count ? "1" : "0.01";
  document.querySelector("#global-value-label").textContent = count ? "Maximum accepted purchases" : "Maximum CHF";
  const days = document.querySelector("#global-days");
  days.value = "";
  days.disabled = control.scope !== "period";
  document.querySelector("#global-days-wrap").hidden = control.scope !== "period";
});

document.addEventListener("input", (event) => {
  if (event.target.id === "request-details") { state.extraDetails = event.target.value; growTextArea(event.target, 72); return; }
  if (event.target.id !== "shop-prompt") return;
  state.prompt = event.target.value;
  growTextArea(event.target, 62);
  const hasPrompt = Boolean(state.prompt.trim());
  if (!hasPrompt) {
    state.extraDetails = "";
    const details = document.querySelector("#request-details");
    if (details) details.value = "";
  }
  const send = document.querySelector(".send-button");
  if (send) send.disabled = !hasPrompt;
  if (state.exampleTimer) window.clearTimeout(state.exampleTimer);
  const example = document.querySelector(".prompt-example");
  if (example) example.hidden = hasPrompt;
  const hint = document.querySelector(".request-hint");
  if (hint) hint.hidden = hasPrompt;
  const clarification = document.querySelector(".clarification");
  if (clarification) clarification.hidden = !hasPrompt;
});

document.addEventListener("focusin", (event) => {
  if (event.target.id === "shop-prompt") window.clearTimeout(state.exampleTimer);
  if (event.target.id === "animated-example") {
    window.clearTimeout(state.exampleTimer);
    event.target.textContent = text(event.target.dataset.example, "Example request");
  }
});

document.addEventListener("focusout", (event) => {
  if (event.target.id === "shop-prompt" && !event.target.value) startExamples();
  if (event.target.id === "animated-example" && !state.prompt && state.route === "shop") startExamples();
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
  if (event.key === "Enter" && ["username", "password"].includes(event.target.id)) {
    event.preventDefault();
    document.querySelector('[data-action="login"], [data-action="register"]').click();
  }
  if (event.key === "Enter" && event.target.id === "pair-code") {
    event.preventDefault();
    document.querySelector('[data-action="submit-pair-code"]').click();
  }
});

window.addEventListener("hashchange", () => navigate(requestedRoute()));
reducedMotion.addEventListener("change", () => {
  window.clearTimeout(state.exampleTimer);
  const example = document.querySelector("#animated-example");
  if (!example || state.route !== "shop") return;
  if (reducedMotion.matches) example.textContent = text(example.dataset.example, "Example request");
  else startExamples();
});
initialize();
