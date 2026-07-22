"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import ApplyPanel from "@/components/ApplyPanel";
import ProviderSetup from "@/components/ProviderSetup";
import {
  api,
  needsProviderSetup,
  type ApplyResponse,
  type JobRecord,
  type SearchResponse,
  type SettingsOut,
} from "@/lib/api";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [location, setLocation] = useState("");
  const [remoteOnly, setRemoteOnly] = useState(false);

  const [results, setResults] = useState<SearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<JobRecord | null>(null);
  const [applyingId, setApplyingId] = useState<string | null>(null);
  const [applyResult, setApplyResult] = useState<ApplyResponse | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [hasResume, setHasResume] = useState<boolean | null>(null);
  const [settings, setSettings] = useState<SettingsOut | null>(null);
  const [showSetup, setShowSetup] = useState(false);

  useEffect(() => {
    api
      .baseResume()
      .then((r) => setHasResume(Boolean(r)))
      .catch(() => setHasResume(false));
    api.settings().then(setSettings).catch(() => undefined);
  }, []);

  const setupNeeded = settings ? needsProviderSetup(settings) : false;

  async function runSearch(e?: React.FormEvent) {
    e?.preventDefault();
    setSearching(true);
    setError(null);
    setSelected(null);
    try {
      const res = await api.search(query, location, remoteOnly);
      setResults(res);
      setSelected(res.jobs[0] ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setSearching(false);
    }
  }

  async function handleApply(job: JobRecord) {
    setApplyingId(job.id);
    setApplyError(null);
    try {
      setApplyResult(await api.apply(job.id));
    } catch (err) {
      setApplyError(err instanceof Error ? err.message : "Apply failed.");
    } finally {
      setApplyingId(null);
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Find a role</h1>
        <p className="mt-1 text-sm text-muted">
          Search public job boards, then tailor your resume to any posting in one click.
        </p>
      </header>

      {/* Two setup steps, surfaced in the order they're needed. Both are dismissible-by-
          completion rather than nagging banners, and the model step is inline so the key
          can be pasted without hunting through Settings. */}
      {/* Stays mounted once opened (`|| showSetup`). Saving a local provider flips
          `setupNeeded` to false, and unmounting on that would rip the card away before
          the user ever sees the connection-test result. */}
      {settings && (setupNeeded || showSetup) && (
        <div className="card mb-6 border-brand/30 p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="font-bold">
                {setupNeeded ? "Step 1 — connect a model" : "Model settings"}
              </p>
              <p className="mt-0.5 text-sm text-muted">
                Search works without this. Reading your resume and tailoring it don&apos;t.
              </p>
            </div>
            {showSetup ? (
              <button
                className="btn-ghost shrink-0"
                onClick={() => setShowSetup(false)}
              >
                Hide
              </button>
            ) : (
              <button className="btn-primary shrink-0" onClick={() => setShowSetup(true)}>
                Add API key
              </button>
            )}
          </div>
          {showSetup && (
            <div className="mt-4 border-t border-line pt-4">
              <ProviderSetup settings={settings} onSaved={setSettings} compact />
            </div>
          )}
        </div>
      )}

      {hasResume === false && (
        <div className="card mb-6 flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm">
            <span className="font-bold">
              {setupNeeded ? "Step 2 — " : ""}No resume yet.
            </span>{" "}
            <span className="text-muted">
              Upload one so Apply can tailor it against a posting.
            </span>
          </p>
          <Link href="/resume" className="btn-primary shrink-0">
            Upload resume
          </Link>
        </div>
      )}

      <form onSubmit={runSearch} className="card mb-6 p-4">
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            className="field flex-1"
            placeholder="Job title or keywords (e.g. backend engineer)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <input
            className="field sm:max-w-[220px]"
            placeholder="Location"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
          />
          <button type="submit" className="btn-primary shrink-0" disabled={searching}>
            {searching ? "Searching…" : "Search"}
          </button>
        </div>
        <label className="mt-3 flex w-fit cursor-pointer items-center gap-2 text-sm text-muted">
          <input
            type="checkbox"
            checked={remoteOnly}
            onChange={(e) => setRemoteOnly(e.target.checked)}
            className="h-4 w-4 accent-[#12a1c0]"
          />
          Remote only
        </label>
      </form>

      {error && (
        <p className="card mb-6 border-gold/60 bg-gold/10 p-4 text-sm">{error}</p>
      )}
      {applyError && (
        <div className="card mb-6 border-gold/60 bg-gold/10 p-4">
          <p className="text-sm font-semibold">{applyError}</p>
          {/* If the failure was the model, offer the fix right here rather than
              sending the user off to Settings to figure it out. */}
          {settings && /key|ollama|provider|reach/i.test(applyError) && (
            <div className="mt-4 border-t border-gold/40 pt-4">
              <ProviderSetup settings={settings} onSaved={setSettings} compact />
            </div>
          )}
        </div>
      )}

      {results && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-muted">
            <span>
              {results.jobs.length} result{results.jobs.length === 1 ? "" : "s"}
            </span>
            {results.sources_ok.map((s) => (
              <span
                key={s}
                className="rounded-full bg-brand-tint px-2 py-0.5 font-semibold text-brand"
              >
                {s}
              </span>
            ))}
            {/* A failed source degrades results silently otherwise — say so out loud. */}
            {Object.entries(results.sources_failed).map(([source, detail]) => (
              <span
                key={source}
                title={detail}
                className="rounded-full bg-gold/20 px-2 py-0.5 font-semibold"
              >
                {source} unavailable
              </span>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
            <ul className="flex max-h-[70vh] flex-col gap-2 overflow-y-auto pr-1">
              {results.jobs.map((job) => (
                <li key={job.id}>
                  <button
                    onClick={() => setSelected(job)}
                    className={`card w-full p-4 text-left transition-colors ${
                      selected?.id === job.id
                        ? "border-brand bg-brand-tint"
                        : "hover:border-brand/40"
                    }`}
                  >
                    <p className="font-bold leading-snug">{job.title}</p>
                    <p className="mt-0.5 text-sm text-muted">{job.company}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
                      {job.location && <span>{job.location}</span>}
                      {job.remote && (
                        <span className="rounded-full bg-brand-teal/30 px-2 py-0.5 font-semibold text-ink">
                          Remote
                        </span>
                      )}
                      <span className="rounded-full border border-line px-2 py-0.5">
                        {job.source}
                      </span>
                    </div>
                  </button>
                </li>
              ))}
              {results.jobs.length === 0 && (
                <li className="card p-6 text-center text-sm text-muted">
                  No matches. Try broader keywords, or add more Greenhouse companies in
                  Settings.
                </li>
              )}
            </ul>

            {selected && (
              <section className="card flex max-h-[70vh] flex-col p-5">
                <header className="border-b border-line pb-4">
                  <h2 className="text-lg font-bold leading-snug">{selected.title}</h2>
                  <p className="mt-0.5 text-sm text-muted">
                    {selected.company}
                    {selected.location ? ` · ${selected.location}` : ""}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      className="btn-primary"
                      disabled={applyingId === selected.id || !hasResume}
                      onClick={() => handleApply(selected)}
                      title={hasResume ? undefined : "Upload a resume first"}
                    >
                      {applyingId === selected.id
                        ? "Tailoring…"
                        : "Tailor resume & apply"}
                    </button>
                    <a
                      className="btn-ghost"
                      href={selected.apply_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      View posting ↗
                    </a>
                  </div>
                </header>
                <div className="mt-4 overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed text-muted">
                  {selected.description || "No description provided by this source."}
                </div>
              </section>
            )}
          </div>
        </>
      )}

      {applyResult && (
        <ApplyPanel result={applyResult} onClose={() => setApplyResult(null)} />
      )}
    </div>
  );
}
