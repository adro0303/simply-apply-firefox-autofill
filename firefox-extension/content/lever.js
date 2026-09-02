// SELECTORS UNVERIFIED — confirm against a live posting before relying on this, see firefox-extension/README.md
//
// Best-guess based on Lever's documented `name` attribute conventions
// (`name`, `email`, `phone`, `urls[LinkedIn]`, `urls[Portfolio]`, `comments`).
// Lever has no dedicated cover-letter field on most postings — "Additional
// Information" (`comments`) is the closest free-text field, used as a
// best-effort drop target.

(function () {
  function fill(data) {
    const basics = data?.resume?.basics || {};
    const linkedin = (basics.profiles || []).find((p) => /linkedin/i.test(p.network || p.url || ""));
    const portfolio = basics.url || (basics.profiles || []).find((p) => /portfolio|github/i.test(p.network || ""))?.url;

    const fields = [
      { name: "name", value: basics.name, selectors: ['input[name="name"]'] },
      { name: "email", value: basics.email, selectors: ['input[name="email"]'] },
      { name: "phone", value: basics.phone, selectors: ['input[name="phone"]'] },
      { name: "location", value: basics.location?.city, selectors: ['input[name="location"]'] },
      { name: "linkedin", value: linkedin?.url, selectors: ['input[name="urls[LinkedIn]"]'] },
      { name: "portfolio", value: portfolio, selectors: ['input[name="urls[Portfolio]"]', 'input[name="urls[GitHub]"]'] },
    ];

    const { filled, missed } = fillFields(fields);

    if (data?.coverLetter) {
      const el = document.querySelector('textarea[name="comments"]');
      if (el) {
        setNativeValue(el, data.coverLetter);
        filled.push("coverLetter (Additional Information field)");
      } else {
        missed.push("coverLetter");
      }
    }

    highlightFileInputs(['input[name="resume"]', 'input[type="file"]'], data?.resumeFilename);

    return { filled, missed };
  }

  window.SimplyApplyATS = { name: "lever", fill };
})();
