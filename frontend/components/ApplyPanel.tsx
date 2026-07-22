"use client";

import type { ApplyResponse } from "@/lib/api";

/**
 * Result of an Apply run: downloads, the guardrail verdict, and the hand-off link.
 *
 * The guardrail outcome is shown prominently rather than tucked away. If tailoring fell
 * back, the user needs to know *before* they submit that this is their generic resume —
 * a quiet fallback would be worse than no tailoring at all.
 */
export default function ApplyPanel({
  result,
  onClose,
}: {
  result: ApplyResponse;
  onClose: () => void;
}) {
  const { tailoring, job } = result;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 p-0 sm:items-center sm:p-6">
      <div className="w-full max-w-2xl overflow-hidden rounded-t-[20px] bg-white sm:rounded-[20px]">
        <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-5">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-bold">{job.title}</h2>
            <p className="truncate text-sm text-muted">
              {job.company}
              {job.location ? ` · ${job.location}` : ""}
            </p>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 rounded-lg p-1 text-muted hover:bg-page hover:text-ink"
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        <div className="max-h-[60vh] overflow-y-auto px-6 py-5">
          {/* --- guardrail verdict --- */}
          {tailoring.fell_back ? (
            <div className="mb-5 rounded-xl border border-gold/60 bg-gold/10 p-4">
              <p className="text-sm font-bold">Tailoring was blocked — original resume used</p>
              <p className="mt-1 text-sm text-muted">{tailoring.warning}</p>
              {tailoring.violations.length > 0 && (
                <ul className="mt-3 space-y-1 text-xs text-muted">
                  {tailoring.violations.slice(0, 8).map((v, i) => (
                    <li key={i}>
                      <span className="font-semibold text-ink">{v.kind}</span>{" "}
                      <code className="rounded bg-white px-1">{v.value}</code> — {v.detail}
                    </li>
                  ))}
                  {tailoring.violations.length > 8 && (
                    <li>…and {tailoring.violations.length - 8} more.</li>
                  )}
                </ul>
              )}
            </div>
          ) : (
            <div className="mb-5 rounded-xl border border-brand/30 bg-brand-tint p-4">
              <p className="text-sm font-bold text-brand">
                Tailored and verified against your resume
              </p>
              <p className="mt-1 text-sm text-muted">
                Every employer, title, date, figure, and skill in this version traces back
                to your original resume. Nothing was invented.
              </p>
              {tailoring.notes.length > 0 && (
                <ul className="mt-2 text-xs text-muted">
                  {tailoring.notes.map((n, i) => (
                    <li key={i}>· {n}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* --- downloads --- */}
          <p className="mb-2 text-xs font-bold uppercase tracking-wide text-muted">
            Your files
          </p>
          <div className="flex flex-wrap gap-3">
            {result.pdf_url && (
              <a className="btn-primary" href={result.pdf_url} download>
                Download PDF
                <span className="rounded-full bg-white/20 px-2 py-0.5 text-[10px] font-bold">
                  ONE PAGE
                </span>
              </a>
            )}
            {result.docx_url && (
              <a className="btn-ghost" href={result.docx_url} download>
                Download .docx
              </a>
            )}
          </div>
          {result.pdf_error && (
            <p className="mt-2 text-xs leading-relaxed text-muted">
              PDF couldn&apos;t be generated this time ({result.pdf_error}) — your .docx is
              ready below.
            </p>
          )}
          <p className="mt-3 text-xs text-muted">
            The PDF is a polished single page for humans. The .docx is the safest choice
            when an application form parses your resume with an ATS.
          </p>
        </div>

        <footer className="flex flex-col gap-3 border-t border-line bg-page px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-muted">
            Download your file first, then submit it on the employer&apos;s form yourself.
          </p>
          <a
            className="btn-primary shrink-0"
            href={job.apply_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open application ↗
          </a>
        </footer>
      </div>
    </div>
  );
}
