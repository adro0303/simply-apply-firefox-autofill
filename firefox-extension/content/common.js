// content/common.js — shared helpers, loaded before the per-ATS script on every
// matched page (see manifest.json content_scripts). Per-ATS files attach a
// `window.SimplyApplyATS` object; this file wires the runtime message that
// triggers it and the low-level DOM helpers everyone needs.

/**
 * React/Ember/Vue-controlled inputs track their own internal value and ignore
 * a plain `element.value = x` — the framework's re-render clobbers it right
 * back. You have to go through the native property setter (bypassing the
 * framework's overridden setter on the instance) and then fire the events the
 * framework's listeners actually expect.
 */
function setNativeValue(element, value) {
  const proto = element.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  const descriptor = Object.getOwnPropertyDescriptor(proto, "value");
  descriptor.set.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

/**
 * Fills a list of `{selectors, value}` fields. `selectors` is an array of CSS
 * selectors tried in order (best-guess fields may have several candidates
 * across ATS versions/tenants) — the first one found on the page wins.
 * Missing fields are skipped, never thrown on.
 */
function fillFields(fields) {
  const filled = [];
  const missed = [];
  for (const { name, selectors, value } of fields) {
    if (!value) continue;
    const selector = Array.isArray(selectors) ? selectors : [selectors];
    const el = selector.map((s) => document.querySelector(s)).find(Boolean);
    if (!el) {
      missed.push(name);
      continue;
    }
    setNativeValue(el, value);
    filled.push(name);
  }
  return { filled, missed };
}

/**
 * File inputs can't be filled by script (browsers block it). Instead, visibly
 * flag any file input on the page so the user knows to attach the resume
 * SimplyApply generated for them themselves.
 */
function highlightFileInputs(selectors, filenameHint) {
  const candidates = selectors && selectors.length ? selectors : ['input[type="file"]'];
  const seen = new Set();
  for (const selector of candidates) {
    document.querySelectorAll(selector).forEach((el) => {
      if (seen.has(el) || el.dataset.simplyapplyFlagged) return;
      seen.add(el);
      el.dataset.simplyapplyFlagged = "true";
      el.style.outline = "3px solid #ff7a00";
      el.style.outlineOffset = "2px";

      const tip = document.createElement("div");
      tip.textContent = filenameHint
        ? `Attach your resume here — SimplyApply generated "${filenameHint}", check your Downloads folder.`
        : "Attach your resume here — SimplyApply generated it, check your Downloads folder.";
      tip.style.cssText =
        "background:#ff7a00;color:#1a1a1a;font:12px/1.4 sans-serif;padding:4px 8px;" +
        "border-radius:4px;max-width:320px;margin:4px 0;";
      el.insertAdjacentElement("afterend", tip);
    });
  }
}

browser.runtime.onMessage.addListener((message) => {
  if (message?.type !== "fillPage") return undefined;
  if (!window.SimplyApplyATS || typeof window.SimplyApplyATS.fill !== "function") {
    return Promise.resolve({ ok: false, error: "no ATS handler loaded on this page" });
  }
  try {
    const result = window.SimplyApplyATS.fill(message.data);
    return Promise.resolve({ ok: true, result });
  } catch (err) {
    return Promise.resolve({ ok: false, error: String(err) });
  }
});
