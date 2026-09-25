"use strict";

const walletApi = (() => {
  async function request(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      ...options,
      headers: options.body ? { "Content-Type": "application/json" } : {},
    });
    if (!response.ok) {
      const error = new Error(response.status === 409
        ? "This information changed before your action was accepted. Reload it and review the current version."
        : response.status === 401
          ? "Your local session has ended. Sign in again to continue."
          : response.status === 404
            ? "This record is unavailable to your account or no longer exists."
            : `The Wallet request failed (HTTP ${response.status}). Please try again or contact the demo operator.`);
      error.status = response.status;
      error.path = path;
      throw error;
    }
    return response.status === 204 ? null : response.json();
  }

  return Object.freeze({
    session: () => request("/session"),
    register: (username, password) => request("/account", { method: "POST", body: JSON.stringify({ username, password }) }),
    login: (username, password) => request("/session", { method: "POST", body: JSON.stringify({ username, password }) }),
    logout: () => request("/session", { method: "DELETE" }),
    pairing: (code) => request(`/pairing/${encodeURIComponent(code)}`),
    approvePairing: (code) => request(`/pairing/${encodeURIComponent(code)}/approve`, { method: "POST" }),
    agents: () => request("/agents"),
    revokeAgent: (id) => request(`/agents/${encodeURIComponent(id)}/revoke`, { method: "POST" }),
    draft: (id) => request(`/drafts/${encodeURIComponent(id)}`),
    boundaryResults: (id) => request(`/drafts/${encodeURIComponent(id)}/boundary-results`),
    drafts: () => request("/drafts?state=all"),
    confirm: (id, version, hash, answers) => request(`/drafts/${encodeURIComponent(id)}/confirm`, {
      method: "POST", body: JSON.stringify({ version, hash, answers }),
    }),
    reject: (id, version, hash, reason) => request(`/drafts/${encodeURIComponent(id)}/reject`, {
      method: "POST", body: JSON.stringify({ version, hash, reason }),
    }),
    mandate: (id) => request(`/mandates/${encodeURIComponent(id)}`),
    mandates: () => request("/mandates?status=all"),
    globalPolicy: () => request("/global-policy"),
    tighten: (id) => request(`/mandates/${encodeURIComponent(id)}/tighten`, {
      method: "POST", body: JSON.stringify({ uncertainty_policy: "decline" }),
    }),
    revoke: (id) => request(`/mandates/${encodeURIComponent(id)}/revoke`, { method: "POST" }),
    pending: () => request("/step-ups/pending"),
    answer: (id, decision) => request(`/step-ups/${encodeURIComponent(id)}/answer`, {
      method: "POST", body: JSON.stringify({
        authorization_id: id,
        decision,
        customer_message: decision === "approve" ? "Customer approved this purchase in the Wallet." : "Customer declined this purchase in the Wallet.",
        answered_at: new Date().toISOString(),
      }),
    }),
    history: (id) => request(`/mandates/${encodeURIComponent(id)}/decisions`),
    decision: (id) => request(`/decisions/${encodeURIComponent(id)}`),
  });
})();
