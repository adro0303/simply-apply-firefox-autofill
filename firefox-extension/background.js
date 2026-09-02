// background.js — the ONLY place in this extension that talks to the network.
// Thin router: content scripts and the popup send {type, ...} messages, this
// shapes the request, fetches localhost:8000, and hands the JSON straight back.
// No business logic beyond that lives here.

const API_BASE = "http://localhost:8000";

async function apiFetch(path, options = {}) {
  const { apiToken } = await browser.storage.local.get("apiToken");
  const headers = { ...(options.headers || {}), "X-SimplyApply-Token": apiToken || "" };
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    // Surface the status so callers can tell "not found" (expected, e.g. 404
    // on lookup) apart from a real error, without throwing away the body.
    return { ok: false, status: res.status, body };
  }
  return { ok: true, status: res.status, body };
}

browser.runtime.onMessage.addListener((message) => {
  switch (message?.type) {
    case "lookup": {
      const url = encodeURIComponent(message.url);
      return apiFetch(`/api/applications/by-url?url=${url}`);
    }

    case "createAdhoc": {
      const { company, title, description, apply_url, location, remote } = message;
      return apiFetch("/api/jobs/adhoc", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company, title, description, apply_url, location, remote }),
      });
    }

    case "apply": {
      const jobId = encodeURIComponent(message.jobId);
      return apiFetch(`/api/apply/${jobId}`, { method: "POST" });
    }

    case "coverLetter": {
      const jobId = encodeURIComponent(message.jobId);
      return apiFetch(`/api/apply/${jobId}/cover-letter`, { method: "POST" });
    }

    default:
      return Promise.resolve({ ok: false, status: 0, body: { error: `unknown message type: ${message?.type}` } });
  }
});
