// SELECTORS UNVERIFIED — confirm against a live posting before relying on this, see firefox-extension/README.md
//
// Best-guess selectors covering both the legacy embed (boards.greenhouse.io,
// `job_application[...]` name attributes) and the newer React app
// (job-boards.greenhouse.io, plain ids/aria-labels). Each field lists several
// candidate selectors, tried in order — see fillFields() in common.js.

(function () {
  function fill(data) {
    const basics = data?.resume?.basics || {};
    const [firstName, ...rest] = (basics.name || "").split(" ");
    const lastName = rest.join(" ");
    const linkedin = (basics.profiles || []).find((p) => /linkedin/i.test(p.network || p.url || ""));
    const portfolio = basics.url || (basics.profiles || []).find((p) => /portfolio|website/i.test(p.network || ""))?.url;

    const fields = [
      { name: "firstName", value: firstName, selectors: ['#first_name', 'input[name="job_application[first_name]"]', 'input[aria-label="First Name"]'] },
      { name: "lastName", value: lastName, selectors: ['#last_name', 'input[name="job_application[last_name]"]', 'input[aria-label="Last Name"]'] },
      { name: "email", value: basics.email, selectors: ['#email', 'input[name="job_application[email]"]', 'input[type="email"]'] },
      { name: "phone", value: basics.phone, selectors: ['#phone', 'input[name="job_application[phone]"]', 'input[type="tel"]'] },
      { name: "location", value: basics.location?.city, selectors: ['#job_application_location', 'input[aria-label*="Location" i]'] },
      { name: "linkedin", value: linkedin?.url, selectors: ['#job_application_urls_linkedin', 'input[name*="linkedin" i]', 'input[aria-label*="LinkedIn" i]'] },
      { name: "portfolio", value: portfolio, selectors: ['#job_application_urls_website', 'input[name*="website" i]', 'input[aria-label*="Website" i]'] },
    ];

    const { filled, missed } = fillFields(fields);

    const coverLetterSelectors = ['#cover_letter_text', 'textarea[name*="cover_letter" i]', 'textarea[aria-label*="Cover Letter" i]'];
    if (data?.coverLetter) {
      const el = coverLetterSelectors.map((s) => document.querySelector(s)).find(Boolean);
      if (el) {
        setNativeValue(el, data.coverLetter);
        filled.push("coverLetter");
      } else {
        missed.push("coverLetter");
      }
    }

    highlightFileInputs(['input#resume', 'input[type="file"][name*="resume" i]', 'input[type="file"]'], data?.resumeFilename);

    return { filled, missed };
  }

  window.SimplyApplyATS = { name: "greenhouse", fill };
})();
