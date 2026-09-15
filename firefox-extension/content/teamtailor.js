// Selectors verified 2026-09-15 against a live posting (ravenpack.teamtailor.com,
// job-boards.teamtailor.com/jobs/{id}-{slug}/applications/new). Teamtailor is
// server-rendered Rails-style markup (`candidate[...]` name attributes), not a
// client SPA, so ids are stable per page load.
//
// No portfolio/LinkedIn text field exists — LinkedIn is only fillable via the
// "Connect with LinkedIn" OAuth button (careersite--linkedin-apply controller),
// there's no field to type a URL into. Resume upload has no plain
// `input[type=file]` either — Teamtailor uses a Dropzone.js widget — so we
// highlight the visible drop-zone trigger instead of a file input.

(function () {
  function fill(data) {
    const basics = data?.resume?.basics || {};
    const [firstName, ...rest] = (basics.name || "").split(" ");
    const lastName = rest.join(" ");

    const fields = [
      { name: "firstName", value: firstName, selectors: ["#candidate_first_name"] },
      { name: "lastName", value: lastName, selectors: ["#candidate_last_name"] },
      { name: "email", value: basics.email, selectors: ["#candidate_email"] },
      { name: "phone", value: basics.phone, selectors: ["#candidate_phone"] },
    ];

    const { filled, missed } = fillFields(fields);

    const coverLetterSelectors = ['textarea[name*="[cover_letter]"]', "#candidate_job_applications_attributes_0_cover_letter"];
    if (data?.coverLetter) {
      const el = coverLetterSelectors.map((s) => document.querySelector(s)).find(Boolean);
      if (el) {
        setNativeValue(el, data.coverLetter);
        filled.push("coverLetter");
      } else {
        missed.push({ name: "coverLetter", value: data.coverLetter });
      }
    }

    highlightFileInputs(
      ['#upload_resume_field [data-forms--inputs--upload-target="trigger"]', "#upload_resume_field"],
      data?.resumeFilename
    );

    return { filled, missed };
  }

  window.SimplyApplyATS = { name: "teamtailor", fill };
})();
