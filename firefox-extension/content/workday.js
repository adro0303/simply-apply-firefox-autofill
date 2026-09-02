// SELECTORS UNVERIFIED — confirm against a live posting before relying on this, see firefox-extension/README.md
//
// Workday is a heavily-customized per-tenant SPA: field naming, page order,
// and `data-automation-id` values vary by employer. These selectors are
// best-effort guesses at the `data-automation-id`s commonly seen on the
// first "Personal Information" page only.
//
// SCOPE: this file intentionally does NOT attempt the later multi-step
// Experience/Education wizard pages (dynamic "add another" lists, per-tenant
// custom questions) — that's documented as a known gap in README.md, not
// silently half-implemented here.

(function () {
  function fill(data) {
    const basics = data?.resume?.basics || {};
    const [firstName, ...rest] = (basics.name || "").split(" ");
    const lastName = rest.join(" ");

    const fields = [
      { name: "firstName", value: firstName, selectors: ['[data-automation-id="legalNameSection_firstName"]', 'input[name*="firstName" i]'] },
      { name: "lastName", value: lastName, selectors: ['[data-automation-id="legalNameSection_lastName"]', 'input[name*="lastName" i]'] },
      { name: "email", value: basics.email, selectors: ['[data-automation-id="email"]', 'input[type="email"]'] },
      { name: "phone", value: basics.phone, selectors: ['[data-automation-id="phone-number"]', '[data-automation-id="phoneNumber"]', 'input[type="tel"]'] },
      { name: "city", value: basics.location?.city, selectors: ['[data-automation-id="addressSection_city"]'] },
      { name: "region", value: basics.location?.region, selectors: ['[data-automation-id="addressSection_countryRegion"]'] },
    ];

    const { filled, missed } = fillFields(fields);

    // No standard cover-letter free-text field on Workday's Personal
    // Information page — cover letters there are typically a file upload on
    // a later page, which is out of scope (see file-level comment above).
    if (data?.coverLetter) missed.push("coverLetter (no known field on this page — Workday cover letters are usually a later-page upload)");

    highlightFileInputs(['[data-automation-id="file-upload-input-ref"]', 'input[type="file"]'], data?.resumeFilename);

    return { filled, missed };
  }

  window.SimplyApplyATS = { name: "workday", fill };
})();
