"""No-fabrication enforcement.

Telling a model "do not invent experience" is a request, not a control. This module is
the control: after tailoring, every load-bearing fact in the output must trace back to
something in the user's base resume. Anything that doesn't is a violation.

What we check, and why each one:

  employer / title / institution
      The facts a recruiter verifies first, and the ones that get someone rescinded.
      Must match a base-resume value exactly (after normalization).

  dates
      Stretching an end date to close a gap is the most tempting single edit and the
      easiest to disprove. Must match a base value.

  metrics
      "Improved performance by 40%" when the base said 15% is fabrication even though
      every word around it is true. Every numeric token in the output must appear in the
      base resume.

  skills
      The one place tailoring legitimately surfaces things — but only things already
      present. A skill may be *promoted* from anywhere in the base resume (a bullet, a
      project description); it may not be introduced because the JD asked for it.

  contact info (basics: name, email, phone, url, location, profiles)
      There is no legitimate reason tailoring ever touches these — unlike the summary,
      which is rewritten for the target role on purpose, a rewritten phone number or
      email is either a model malfunction or a poisoned-JD prompt injection, and either
      way the extension will type it into a live application form. Must match the base
      resume value exactly (after normalization).

Everything else — bullet order, section order, phrasing, the summary — is free. That is
the whole point of tailoring, and none of it asserts a new verifiable fact.

Design note: this is deliberately a whitelist over the base resume rather than a
blocklist of suspicious phrases. A blocklist can only catch fabrications someone
anticipated; a whitelist catches every fabrication by construction, and its failure mode
is a false positive (annoying) rather than a false negative (career damage).
"""

from __future__ import annotations

import re
import unicodedata
from itertools import zip_longest

from app.schemas import Basics, GuardrailViolation, StructuredResume

# Matches numbers with optional magnitude/unit suffixes: 40%, 1.2M, $500k, 3x, 12,000
_NUMERIC = re.compile(r"\$?\d[\d,]*(?:\.\d+)?\s*(?:%|[kKmMbB]\b|[xX]\b)?")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Numbers that carry no factual claim on their own — years of a date, small counts that
# appear incidentally ("2 of the 3 services"). Flagging these produces noise without
# catching fabrication, because they're not the impressive-metric class we care about.
_TRIVIAL_NUMBERS = {str(n) for n in range(0, 11)}


def _fold(value: str) -> str:
    """Lowercase, strip accents, collapse to alphanumerics.

    Makes "Société Générale" and "societe generale" compare equal, so a purely cosmetic
    rewrite doesn't trip the guardrail.
    """
    decomposed = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM.sub(" ", stripped.lower()).strip()


def _key(value: str) -> str:
    return _NON_ALNUM.sub("", _fold(value))


def _normalize_number(token: str) -> str:
    """`$1,200.00` and `1200` compare equal; `40%` stays distinct from `40`."""
    token = token.strip().lower().replace(",", "").replace("$", "").replace(" ", "")
    if token.endswith("%"):
        return _strip_trailing_zeros(token[:-1]) + "%"
    for suffix in ("k", "m", "b", "x"):
        if token.endswith(suffix):
            return _strip_trailing_zeros(token[:-1]) + suffix
    return _strip_trailing_zeros(token)


def _strip_trailing_zeros(number: str) -> str:
    if "." in number:
        number = number.rstrip("0").rstrip(".")
    return number or "0"


def _fold_phone(value: str) -> str:
    """Digits only. `+34 675 931 520` and `+34675931520` are the same number; spacing,
    parens, and dashes carry no meaning."""
    return re.sub(r"\D", "", value or "")


def _fold_url(value: str) -> str:
    """Scheme/`www.`/trailing-slash agnostic — cosmetic URL formatting shouldn't trip
    the guardrail, but a different domain or path must."""
    value = (value or "").strip().lower()
    value = re.sub(r"^[a-z][a-z0-9+.-]*://", "", value)
    value = re.sub(r"^www\.", "", value)
    return value.rstrip("/")


def _all_text(resume: StructuredResume) -> str:
    """Every free-text field, concatenated — the corpus a skill may be promoted from."""
    parts: list[str] = [
        resume.basics.name,
        resume.basics.label,
        resume.basics.summary,
        resume.basics.email,
        resume.basics.phone,
        resume.basics.url,
        resume.basics.location.city,
        resume.basics.location.region,
        resume.basics.location.countryCode,
    ]
    for profile in resume.basics.profiles:
        parts += [profile.network, profile.username, profile.url]
    for job in resume.work:
        parts += [job.name, job.position, job.location, job.summary, *job.highlights]
    for edu in resume.education:
        parts += [edu.institution, edu.area, edu.studyType, edu.score, *edu.courses]
    for skill in resume.skills:
        parts += [skill.name, skill.level, *skill.keywords]
    for project in resume.projects:
        parts += [project.name, project.description, *project.highlights, *project.keywords]
    return " ".join(p for p in parts if p)


def _numbers_in(text: str) -> set[str]:
    found = set()
    for match in _NUMERIC.finditer(text or ""):
        normalized = _normalize_number(match.group())
        if normalized and normalized not in _TRIVIAL_NUMBERS:
            found.add(normalized)
    return found


class BaseFacts:
    """The set of things the tailored resume is allowed to assert."""

    def __init__(self, base: StructuredResume) -> None:
        self.employers = {_key(j.name) for j in base.work if j.name}
        self.titles = {_key(j.position) for j in base.work if j.position}
        self.institutions = {_key(e.institution) for e in base.education if e.institution}
        self.degrees = {_key(e.studyType) for e in base.education if e.studyType}
        self.fields = {_key(e.area) for e in base.education if e.area}
        self.project_names = {_key(p.name) for p in base.projects if p.name}

        self.dates: set[str] = set()
        for job in base.work:
            self.dates.update(_key(d) for d in (job.startDate, job.endDate) if d)
        for edu in base.education:
            self.dates.update(_key(d) for d in (edu.startDate, edu.endDate) if d)
        for project in base.projects:
            self.dates.update(_key(d) for d in (project.startDate, project.endDate) if d)

        self.corpus = _fold(_all_text(base))
        self.numbers = _numbers_in(_all_text(base))

    def mentions(self, value: str) -> bool:
        """True if `value` appears anywhere in the base resume's text."""
        folded = _fold(value)
        return bool(folded) and folded in self.corpus


_CONTACT_FIELDS = ("name", "email", "phone", "url")
_LOCATION_FIELDS = ("city", "region", "countryCode")


def _contact_diff(base: Basics, tailored: Basics) -> list[tuple[str, str, str]]:
    """(field path, base value, tailored value) for every contact field that changed.

    Each field uses the normalization appropriate to it, so a cosmetic rewrite (phone
    spacing, a trailing slash on a URL, accent folding on a name) doesn't false-positive
    — but a substituted value, however cosmetic-looking, still differs after folding.
    """
    changed: list[tuple[str, str, str]] = []

    for field in _CONTACT_FIELDS:
        base_value = getattr(base, field)
        tailored_value = getattr(tailored, field)
        norm = _fold_url if field == "url" else (_fold_phone if field == "phone" else _key)
        if norm(base_value) != norm(tailored_value):
            changed.append((field, base_value, tailored_value))

    for field in _LOCATION_FIELDS:
        base_value = getattr(base.location, field)
        tailored_value = getattr(tailored.location, field)
        if _key(base_value) != _key(tailored_value):
            changed.append((f"location.{field}", base_value, tailored_value))

    for i, (bp, tp) in enumerate(zip_longest(base.profiles, tailored.profiles)):
        for field, norm in (("network", _key), ("username", _key), ("url", _fold_url)):
            base_value = getattr(bp, field) if bp else ""
            tailored_value = getattr(tp, field) if tp else ""
            if norm(base_value) != norm(tailored_value):
                changed.append((f"profiles[{i}].{field}", base_value, tailored_value))

    return changed


def check(base: StructuredResume, tailored: StructuredResume) -> list[GuardrailViolation]:
    """Return every fact in `tailored` that isn't supported by `base`. Empty = clean."""
    facts = BaseFacts(base)
    violations: list[GuardrailViolation] = []

    def flag(kind: str, value: str, where: str, detail: str) -> None:
        violations.append(
            GuardrailViolation(kind=kind, value=value, where=where, detail=detail)
        )

    # --- contact info ------------------------------------------------------
    # Tailoring has no legitimate reason to touch any of this — unlike the summary, which
    # is meant to change, a rewritten email/phone/url/name/location/profile is either a
    # model malfunction or a prompt-injected job description, and it ends up typed into a
    # live application form. Checked first so it can never be masked by other violations.
    for field, base_value, tailored_value in _contact_diff(base.basics, tailored.basics):
        flag(
            "contact",
            tailored_value,
            f"basics.{field}",
            f"basics.{field} does not match the base resume ({base_value!r} -> "
            f"{tailored_value!r}). Tailoring must never change contact information.",
        )

    # --- experience ------------------------------------------------------
    for i, job in enumerate(tailored.work):
        where = f"work[{i}]"
        if job.name and _key(job.name) not in facts.employers:
            flag("employer", job.name, where, "Employer is not in the base resume.")
        if job.position and _key(job.position) not in facts.titles:
            flag("title", job.position, where, "Job title is not in the base resume.")
        for field in ("startDate", "endDate"):
            value = getattr(job, field)
            if value and _key(value) not in facts.dates:
                flag("date", value, f"{where}.{field}", "Date is not in the base resume.")

    # --- education -------------------------------------------------------
    for i, edu in enumerate(tailored.education):
        where = f"education[{i}]"
        if edu.institution and _key(edu.institution) not in facts.institutions:
            flag("institution", edu.institution, where, "Institution is not in the base resume.")
        if edu.studyType and _key(edu.studyType) not in facts.degrees:
            flag("degree", edu.studyType, where, "Degree is not in the base resume.")
        if edu.area and _key(edu.area) not in facts.fields:
            flag("field", edu.area, where, "Field of study is not in the base resume.")
        for field in ("startDate", "endDate"):
            value = getattr(edu, field)
            if value and _key(value) not in facts.dates:
                flag("date", value, f"{where}.{field}", "Date is not in the base resume.")

    # --- projects --------------------------------------------------------
    for i, project in enumerate(tailored.projects):
        if project.name and _key(project.name) not in facts.project_names:
            flag("project", project.name, f"projects[{i}]", "Project is not in the base resume.")

    # --- skills ----------------------------------------------------------
    # Promoting a buried skill is the legitimate core of tailoring; introducing one the
    # user never claimed is not. The base resume's full text is the allowed source.
    for i, skill in enumerate(tailored.skills):
        where = f"skills[{i}]"
        # `name` is a grouping label when keywords are present ("Languages",
        # "Infrastructure") — an organizational choice that asserts nothing, and one the
        # model should be free to rewrite for the target role. It only becomes a factual
        # claim when it stands alone with no keywords beneath it.
        if skill.name and not skill.keywords and not facts.mentions(skill.name):
            flag("skill", skill.name, where, "Skill does not appear anywhere in the base resume.")
        for keyword in skill.keywords:
            if keyword and not facts.mentions(keyword):
                flag(
                    "skill",
                    keyword,
                    f"{where}.keywords",
                    "Keyword does not appear anywhere in the base resume.",
                )

    # --- metrics ---------------------------------------------------------
    # Checked last and across the whole document, because an inflated number can appear
    # in a rewritten bullet whose surrounding words are all legitimate.
    for number in sorted(_numbers_in(_all_text(tailored)) - facts.numbers):
        flag(
            "metric",
            number,
            "document",
            "Figure does not appear in the base resume — possible inflated or invented metric.",
        )

    return violations


def check_text(base: StructuredResume, text: str) -> list[GuardrailViolation]:
    """Numeric-fabrication check for free prose (cover letters, not a StructuredResume).

    A cover letter has no employer/title/date/skill fields to whitelist against — it's a
    paragraph. The one check that generalizes cleanly to prose is the same one `check()`
    runs last: every numeric token in the output must trace back to the base resume.

    # ponytail: free-text guardrail only catches fabricated numbers, not false
    # employer/date claims embedded in prose — add NER-based entity check if this proves
    # insufficient in practice.
    """
    facts = BaseFacts(base)
    violations: list[GuardrailViolation] = []
    for number in sorted(_numbers_in(text) - facts.numbers):
        violations.append(
            GuardrailViolation(
                kind="metric",
                value=number,
                where="document",
                detail=(
                    "Figure does not appear in the base resume — possible inflated or "
                    "invented metric."
                ),
            )
        )
    return violations


def summarize(violations: list[GuardrailViolation]) -> str:
    """One-line feedback string, fed back to the model on the retry attempt."""
    lines = [
        f"- {v.kind} {v.value!r} at {v.where}: {v.detail}" for v in violations[:20]
    ]
    if len(violations) > 20:
        lines.append(f"- ...and {len(violations) - 20} more.")
    return "\n".join(lines)
