"""No-fabrication enforcement.

Telling a model "do not invent experience" is a request, not a control. This module is
the control: after tailoring, every load-bearing fact in the output must trace back to
something in the user's base resume. Anything that doesn't is a violation.

What we check, and why each one:

  employer / institution
      The facts a recruiter verifies first, and the ones that get someone rescinded.
      Must match a base-resume value exactly (after normalization).

  job title
      NOT whitelisted, by design. Reframing the same real job's title/focus for the
      target role (e.g. leading with "Frontend" when the base title is "Software
      Engineer", if the person genuinely did that work) is legitimate tailoring — the
      employer and dates anchor it to a real job either way.

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

# Named products/platforms found live: qwen3:8b's tailored `basics.label` claimed "Power
# BI Analyst" for a job whose posting mentioned Power BI — the user has never touched it.
# Unlike a domain/role word ("Frontend", "Specialist", "Engineer" — legitimate to lead
# with if the underlying skills support it, see the `job title` section above), a named
# tool is a specific, falsifiable claim exactly like an employer name, so it's checked the
# same way: must appear somewhere in the base resume.
#
# This is a fixed list, not exhaustive — it won't catch every possible tool name, only the
# common ones below. Extend it when a new one turns up in practice rather than trying to
# enumerate every technology in existence.
_KNOWN_TOOLS = {
    "power bi", "power automate", "power query", "tableau", "excel", "sap", "salesforce",
    "spring boot", "spring", "angular", "react", "vue", "django", "flask", "laravel",
    "aws", "azure", "gcp", "kubernetes", "terraform", "jenkins", "ansible", "sql server",
    "oracle", "mongodb", "redis", "kafka", "jira", "confluence", "figma", "photoshop",
    "sketch", "unity", "unreal", "matlab", "sas", "spss", "hadoop", "spark", "snowflake",
    "looker", "qlik", "dax", "thymeleaf", "jquery",
}

# Rank words checked against the SAME job's own real title — user decision, found live:
# qwen3:8b promoted "AI & Software Engineer" to "Senior Software Engineer" unprompted.
# Relative, not absolute: a rank word already in the real title (e.g. this base resume's
# own "...promoted to Project Team Lead") is never flagged for that job.
_SENIORITY_WORDS = {
    "senior", "staff", "principal", "vp", "director", "lead", "head", "chief", "manager",
}

def fold(value: str) -> str:
    """Lowercase, strip accents, collapse to alphanumerics.

    Makes "Société Générale" and "societe generale" compare equal, so a purely cosmetic
    rewrite doesn't trip the guardrail.
    """
    decomposed = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM.sub(" ", stripped.lower()).strip()


def key(value: str) -> str:
    return _NON_ALNUM.sub("", fold(value))


def _tokens(value: str) -> set[str]:
    return {t for t in fold(value).split() if len(t) > 2}


def project_name_matches(candidate: str, base_names: list[str], min_overlap: float = 0.5) -> bool:
    """Fuzzy project-identity check, unlike the exact-match whitelist used elsewhere.

    A project name has no employer+dates anchor to confirm "same real thing, reworded"
    the way a job title does, so full free-text isn't safe — but exact string matching is
    too brittle: "OpenSSH Log Anomaly Detection" reworded to "OpenSSH Anomaly Detection
    System" is the same real project, not an invention. Token-overlap against each base
    project name is the middle ground: it tolerates reordering/rewording of a real name
    while still rejecting a name that shares nothing with anything in the base resume.
    """
    cand_tokens = _tokens(candidate)
    if not cand_tokens:
        return False
    for base_name in base_names:
        base_tokens = _tokens(base_name)
        if not base_tokens:
            continue
        shared = cand_tokens & base_tokens
        if not shared:
            continue
        if len(shared) / min(len(cand_tokens), len(base_tokens)) >= min_overlap:
            return True
    return False


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
    """Every number in `text`, normalized. No "trivial number" exemption on purpose — a
    small digit is not automatically harmless: "8+ years of experience" reads as a
    load-bearing claim exactly like "40% faster" does, and a fixed range (originally 0-10)
    that excluded exactly that pattern let it through uncaught in practice. Per-field
    repair (see tailor.py) keeps the cost of an incidental false positive ("3 teams") to
    reverting just that one bullet, not the whole resume, so there's no longer a reason to
    accept the false-negative risk in exchange for less noise.
    """
    found = set()
    for match in _NUMERIC.finditer(text or ""):
        normalized = _normalize_number(match.group())
        if normalized:
            found.add(normalized)
    return found


class BaseFacts:
    """The set of things the tailored resume is allowed to assert."""

    def __init__(self, base: StructuredResume) -> None:
        self.employers = {key(j.name) for j in base.work if j.name}
        self.institutions = {key(e.institution) for e in base.education if e.institution}
        self.degrees = {key(e.studyType) for e in base.education if e.studyType}
        self.fields = {key(e.area) for e in base.education if e.area}
        self.project_names = [p.name for p in base.projects if p.name]

        self.dates: set[str] = set()
        for job in base.work:
            self.dates.update(key(d) for d in (job.startDate, job.endDate) if d)
        for edu in base.education:
            self.dates.update(key(d) for d in (edu.startDate, edu.endDate) if d)
        for project in base.projects:
            self.dates.update(key(d) for d in (project.startDate, project.endDate) if d)

        self.corpus = fold(_all_text(base))
        self.numbers = _numbers_in(_all_text(base))

    def mentions(self, value: str) -> bool:
        """True if `value` appears anywhere in the base resume's text."""
        folded = fold(value)
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
        norm = _fold_url if field == "url" else (_fold_phone if field == "phone" else key)
        if norm(base_value) != norm(tailored_value):
            changed.append((field, base_value, tailored_value))

    for field in _LOCATION_FIELDS:
        base_value = getattr(base.location, field)
        tailored_value = getattr(tailored.location, field)
        if key(base_value) != key(tailored_value):
            changed.append((f"location.{field}", base_value, tailored_value))

    for i, (bp, tp) in enumerate(zip_longest(base.profiles, tailored.profiles)):
        for field, norm in (("network", key), ("username", key), ("url", _fold_url)):
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

    def flag_numbers(text: str, where: str) -> None:
        for number in sorted(_numbers_in(text) - facts.numbers):
            flag(
                "metric",
                number,
                where,
                "Figure does not appear in the base resume — possible inflated or invented metric.",
            )

    def flag_tools(text: str, where: str) -> None:
        text_key = fold(text)
        for tool in sorted(_KNOWN_TOOLS):
            if tool in text_key and tool not in facts.corpus:
                flag(
                    "skill",
                    tool,
                    where,
                    "Names a tool/platform that doesn't appear anywhere in the base resume.",
                )

    def flag_free_text(text: str, where: str) -> None:
        flag_numbers(text, where)
        flag_tools(text, where)

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
    # Job title CAN be reworded, unlike employer/dates — honestly reframing the same real
    # job (e.g. leading with "Frontend" when the base title is "Software Engineer", if
    # that job's own highlights show real frontend work) is legitimate tailoring, not
    # fabrication — user decision, see tailor.py SYSTEM_PROMPT. But the reword must be
    # grounded in THAT SAME job's own real content, checked two ways below: a named tool
    # ("Power BI Analyst") is checked the same as basics.label; the title as a whole must
    # share at least one real word with that job's own position/summary/highlights (found
    # live: qwen3:8b once retitled a sales role "Software Engineer" — a different function,
    # not a rewording of the real one), and any seniority word must already be true for
    # that job (found live: "AI & Software Engineer" promoted unprompted to "Senior
    # Software Engineer").
    for i, job in enumerate(tailored.work):
        where = f"work[{i}]"
        if key(job.name) not in facts.employers:
            # No `job.name and` guard here on purpose: a work entry with content
            # (position/highlights) but no employer name is not "omitted", it's
            # unverifiable — there's nothing to match it to.
            flag("employer", job.name, where, "Employer is not in the base resume.")
        for field in ("startDate", "endDate"):
            value = getattr(job, field)
            if value and key(value) not in facts.dates:
                flag("date", value, f"{where}.{field}", "Date is not in the base resume.")
        flag_tools(job.position, f"{where}.position")

        base_job = next((b for b in base.work if b.name and key(b.name) == key(job.name)), None)
        if base_job is not None and job.position:
            base_job_tokens = _tokens(base_job.position) | _tokens(base_job.summary)
            for highlight in base_job.highlights:
                base_job_tokens |= _tokens(highlight)
            pos_tokens = _tokens(job.position)
            if pos_tokens and not (pos_tokens & base_job_tokens):
                flag(
                    "title",
                    job.position,
                    f"{where}.position",
                    "Title claims a function/focus with no basis anywhere in this job's real duties.",
                )
            claimed_rank = (pos_tokens & _SENIORITY_WORDS) - _tokens(base_job.position)
            if claimed_rank:
                flag(
                    "title",
                    job.position,
                    f"{where}.position",
                    f"Title claims a seniority ({', '.join(sorted(claimed_rank))}) this job's real title doesn't have.",
                )

    # --- education -------------------------------------------------------
    for i, edu in enumerate(tailored.education):
        where = f"education[{i}]"
        if edu.institution and key(edu.institution) not in facts.institutions:
            flag("institution", edu.institution, where, "Institution is not in the base resume.")
        if edu.studyType and key(edu.studyType) not in facts.degrees:
            flag("degree", edu.studyType, where, "Degree is not in the base resume.")
        if edu.area and key(edu.area) not in facts.fields:
            flag("field", edu.area, where, "Field of study is not in the base resume.")
        for field in ("startDate", "endDate"):
            value = getattr(edu, field)
            if value and key(value) not in facts.dates:
                flag("date", value, f"{where}.{field}", "Date is not in the base resume.")

    # --- projects --------------------------------------------------------
    for i, project in enumerate(tailored.projects):
        if not project_name_matches(project.name, facts.project_names):
            # No `project.name and` guard, same reasoning as the employer check above.
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

    # --- metrics & tool names ---------------------------------------------
    # Checked per free-text field, not across the whole document: an inflated number or
    # an invented tool name can appear in a rewritten bullet whose surrounding words are
    # all legitimate, and a specific `where` lets tailor.py repair just that field instead
    # of discarding everything the model got right.
    flag_free_text(tailored.basics.summary, "basics.summary")
    flag_free_text(tailored.basics.label, "basics.label")
    for i, job in enumerate(tailored.work):
        flag_free_text(job.summary, f"work[{i}].summary")
        for j, highlight in enumerate(job.highlights):
            flag_free_text(highlight, f"work[{i}].highlights[{j}]")
    for i, project in enumerate(tailored.projects):
        flag_free_text(project.name, f"projects[{i}].name")
        flag_free_text(project.description, f"projects[{i}].description")
        for j, highlight in enumerate(project.highlights):
            flag_free_text(highlight, f"projects[{i}].highlights[{j}]")

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
