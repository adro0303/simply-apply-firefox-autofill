"use client";

import { useEffect, useState } from "react";
import { api, type ApplicationOut } from "@/lib/api";

const STATUSES = [
  "prepared",
  "applied",
  "interviewing",
  "offer",
  "rejected",
  "withdrawn",
];

export default function ApplicationsPage() {
  const [rows, setRows] = useState<ApplicationOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .applications()
      .then(setRows)
      .catch((err) => setError(err instanceof Error ? err.message : "Load failed."))
      .finally(() => setLoading(false));
  }, []);

  async function update(id: number, patch: { status?: string; notes?: string }) {
    const updated = await api.updateApplication(id, patch);
    setRows((prev) => prev.map((r) => (r.id === id ? updated : r)));
  }

  async function remove(id: number) {
    await api.deleteApplication(id);
    setRows((prev) => prev.filter((r) => r.id !== id));
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Applications</h1>
        <p className="mt-1 text-sm text-muted">
          Every tailored resume you generated, with the version that was sent. Local only.
        </p>
      </header>

      {loading && <p className="text-sm text-muted">Loading…</p>}
      {error && <p className="card border-gold/60 bg-gold/10 p-4 text-sm">{error}</p>}

      {!loading && rows.length === 0 && (
        <div className="card p-10 text-center">
          <p className="font-bold">Nothing yet</p>
          <p className="mt-1 text-sm text-muted">
            Applications appear here once you tailor a resume for a posting.
          </p>
        </div>
      )}

      <ul className="flex flex-col gap-3">
        {rows.map((row) => (
          <li key={row.id} className="card p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="font-bold leading-snug">{row.title || row.job_id}</p>
                <p className="text-sm text-muted">
                  {row.company}
                  {" · "}
                  {new Date(row.applied_at).toLocaleDateString()}
                </p>
              </div>
              <select
                className="field w-auto"
                value={row.status}
                onChange={(e) => update(row.id, { status: e.target.value })}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>

            <div className="mt-3 flex flex-wrap gap-2 text-sm">
              {row.docx_url && (
                <a className="btn-ghost !py-1.5 !text-xs" href={row.docx_url} download>
                  .docx
                </a>
              )}
              {row.pdf_url && (
                <a className="btn-ghost !py-1.5 !text-xs" href={row.pdf_url} download>
                  PDF
                </a>
              )}
              {row.apply_url && (
                <a
                  className="btn-ghost !py-1.5 !text-xs"
                  href={row.apply_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Posting ↗
                </a>
              )}
              <button
                className="btn-ghost !py-1.5 !text-xs"
                onClick={() => remove(row.id)}
              >
                Delete
              </button>
            </div>

            <textarea
              className="field mt-3 min-h-[52px] resize-y"
              placeholder="Notes — recruiter name, follow-up date, interview prep…"
              defaultValue={row.notes}
              onBlur={(e) => {
                if (e.target.value !== row.notes) {
                  update(row.id, { notes: e.target.value });
                }
              }}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}
