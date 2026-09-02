// popup/popup.js — no framework, no build step. Talks only to background.js
// (which is the only thing allowed to hit localhost:8000) and to the active
// tab's content script (to trigger the actual fill).

const loadingEl = document.getElementById("loading");
const foundView = document.getElementById("found-view");
const adhocView = document.getElementById("adhoc-view");

let activeTab = null;
// Filled in once we have data to hand to the content script.
let fillPayload = null;

function filenameFromUrl(url) {
  if (!url) return null;
  try {
    return decodeURIComponent(new URL(url, "http://localhost:8000").pathname.split("/").pop());
  } catch {
    return null;
  }
}

function renderWarnings(container, items) {
  container.innerHTML = "";
  for (const text of items.filter(Boolean)) {
    const div = document.createElement("div");
    div.className = "warning";
    div.textContent = text;
    container.appendChild(div);
  }
}

function showError(container, message) {
  const div = document.createElement("div");
  div.className = "error";
  div.textContent = message;
  container.appendChild(div);
}

// A 401 from the backend means no (or a wrong) token is stored — this is the
// one error that's actionable from the popup itself, so give it a button
// instead of just text.
class AuthRequiredError extends Error {}

// Shared by every backend call below so a 401 is handled the same way no
// matter which step of the chain (create job / tailor / cover letter) hit it.
function checkOk(resp, fallbackMessage) {
  if (resp.ok) return resp;
  if (resp.status === 401) throw new AuthRequiredError();
  throw new Error(resp.body?.detail || fallbackMessage);
}

function showAuthSetupNeeded(container) {
  container.innerHTML = "";
  const div = document.createElement("div");
  div.className = "error";
  div.textContent = "Set up your extension token in Options first. ";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = "Open Options";
  btn.addEventListener("click", () => browser.runtime.openOptionsPage());
  div.appendChild(btn);
  container.appendChild(div);
}

// Normalizes both the "already prepared" lookup response and the freshly-built
// adhoc chain into one shape the render/fill code below can share.
function showFound({ job, docx_url, tailoring, coverLetterBody, coverLetterWarning, coverLetterFellBack }) {
  loadingEl.classList.add("hidden");
  adhocView.classList.add("hidden");
  foundView.classList.remove("hidden");

  document.getElementById("job-summary").textContent = `${job.title} @ ${job.company}`;
  document.getElementById("resume-filename").textContent = filenameFromUrl(docx_url) || "(filename unknown — check Downloads)";

  const warnings = [];
  if (tailoring?.fell_back) warnings.push("Resume: guardrail fell back to the generic (untailored) resume — " + (tailoring.warning || "see backend logs for why."));
  else if (tailoring?.warning) warnings.push("Resume: " + tailoring.warning);
  if (coverLetterFellBack) warnings.push("Cover letter: guardrail fell back to a generic letter — " + (coverLetterWarning || "see backend logs for why."));
  else if (coverLetterWarning) warnings.push("Cover letter: " + coverLetterWarning);
  renderWarnings(document.getElementById("found-warnings"), warnings);

  fillPayload = {
    resume: tailoring?.resume,
    coverLetter: coverLetterBody || null,
    resumeFilename: filenameFromUrl(docx_url),
  };
}

function showAdhocForm() {
  loadingEl.classList.add("hidden");
  foundView.classList.add("hidden");
  adhocView.classList.remove("hidden");
}

async function init() {
  const tabs = await browser.tabs.query({ active: true, currentWindow: true });
  activeTab = tabs[0];
  if (!activeTab?.url) {
    showAdhocForm();
    return;
  }

  const resp = await browser.runtime.sendMessage({ type: "lookup", url: activeTab.url });
  if (resp.ok) {
    // GET /api/applications/by-url returns ApplicationDetail: {application, resume,
    // cover_letter, cover_letter_fell_back}, a different shape from POST /api/apply's
    // ApplyResponse (used below in the adhoc-submit handler) — it has no TailorResult,
    // so the resume's fell_back/warning aren't available here, only the cover letter's.
    const b = resp.body;
    showFound({
      job: { title: b.application.title, company: b.application.company },
      docx_url: b.application.docx_url,
      tailoring: { resume: b.resume },
      coverLetterBody: b.cover_letter,
      coverLetterFellBack: b.cover_letter_fell_back,
      coverLetterWarning: b.cover_letter_warning,
    });
  } else if (resp.status === 401) {
    showAuthSetupNeeded(loadingEl);
  } else {
    // 404 = no prepared application yet, expected. Anything else is a real
    // error but the adhoc form is still the right fallback action.
    showAdhocForm();
  }
}

document.getElementById("fill-btn").addEventListener("click", async () => {
  const statusEl = document.getElementById("fill-status");
  statusEl.textContent = "";
  if (!fillPayload?.resume) {
    showError(statusEl, "No resume data to fill.");
    return;
  }
  try {
    const result = await browser.tabs.sendMessage(activeTab.id, { type: "fillPage", data: fillPayload });
    if (!result?.ok) {
      showError(statusEl, result?.error || "Could not fill this page — is it a supported ATS page?");
      return;
    }
    const { filled, missed } = result.result;
    statusEl.textContent = `Filled: ${filled.join(", ") || "none"}.` + (missed.length ? ` Not found on page: ${missed.join(", ")}.` : "");
  } catch (err) {
    showError(statusEl, "Could not reach this tab's content script — reload the page and try again.");
  }
});

document.getElementById("adhoc-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const statusEl = document.getElementById("adhoc-status");
  const submitBtn = document.getElementById("adhoc-submit");
  statusEl.textContent = "";
  statusEl.className = "status";
  submitBtn.disabled = true;

  try {
    const company = document.getElementById("company").value.trim();
    const title = document.getElementById("title").value.trim();
    const description = document.getElementById("description").value.trim();

    statusEl.textContent = "Creating job…";
    const adhoc = await browser.runtime.sendMessage({
      type: "createAdhoc",
      company,
      title,
      description,
      apply_url: activeTab.url,
      location: "",
      remote: false,
    });
    checkOk(adhoc, "Could not create job.");
    const jobId = adhoc.body.id;

    statusEl.textContent = "Tailoring resume (this calls your local model, may take a moment)…";
    const applyResp = await browser.runtime.sendMessage({ type: "apply", jobId });
    checkOk(applyResp, "Could not tailor resume.");

    statusEl.textContent = "Writing cover letter…";
    const coverResp = await browser.runtime.sendMessage({ type: "coverLetter", jobId });
    checkOk(coverResp, "Could not generate cover letter.");

    statusEl.textContent = "";
    showFound({
      job: applyResp.body.job,
      docx_url: applyResp.body.docx_url,
      tailoring: applyResp.body.tailoring,
      coverLetterBody: coverResp.body.body,
      coverLetterWarning: coverResp.body.warning,
      coverLetterFellBack: coverResp.body.fell_back,
    });
  } catch (err) {
    statusEl.className = "status";
    if (err instanceof AuthRequiredError) showAuthSetupNeeded(statusEl);
    else showError(statusEl, err.message || String(err));
  } finally {
    submitBtn.disabled = false;
  }
});

init();
