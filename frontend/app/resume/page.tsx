"use client";

import { useEffect, useRef, useState } from "react";
import ResumeEditor from "@/components/ResumeEditor";
import ProviderSetup from "@/components/ProviderSetup";
import {
  api,
  needsProviderSetup,
  type ResumeOut,
  type SettingsOut,
  type StructuredResume,
} from "@/lib/api";

const EMPTY: StructuredResume = {
  basics: {
    name: "",
    label: "",
    email: "",
    phone: "",
    url: "",
    summary: "",
    location: { city: "", region: "", countryCode: "" },
    profiles: [],
  },
  work: [],
  education: [],
  skills: [],
  projects: [],
};

export default function ResumePage() {
  const [existing, setExisting] = useState<ResumeOut | null>(null);
  const [draft, setDraft] = useState<StructuredResume | null>(null);
  const [name, setName] = useState("My resume");
  const [needsConfirm, setNeedsConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [settings, setSettings] = useState<SettingsOut | null>(null);
  // Once the user has saved from the setup card, keep it on screen even though
  // `setupNeeded` may now be false — otherwise the connection-test result they were
  // waiting for disappears along with the card.
  const [setupTouched, setSetupTouched] = useState(false);

  useEffect(() => {
    api
      .baseResume()
      .then((r) => {
        if (r) {
          setExisting(r);
          setDraft(r.data);
          setName(r.name);
        }
      })
      .catch(() => undefined);
    api.settings().then(setSettings).catch(() => undefined);
  }, []);

  const setupNeeded = settings ? needsProviderSetup(settings) : false;

  async function handleUpload(file: File) {
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const parsed = await api.parseResume(file);
      setDraft(parsed.data);
      setNeedsConfirm(true);
      setName(file.name.replace(/\.[^.]+$/, "") || "My resume");
      setStatus(
        "Parsed. Review every field below — this becomes the source of truth for every resume you generate.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not parse that file.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSave() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const saved =
        existing && !needsConfirm
          ? await api.updateResume(existing.id, name, draft)
          : await api.saveResume(name, draft);
      setExisting(saved);
      setDraft(saved.data);
      setNeedsConfirm(false);
      setStatus("Saved. This is now your base resume.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Your resume</h1>
        <p className="mt-1 text-sm text-muted">
          Stored as structured data, not a file. Every tailored resume is regenerated from
          this — and the no-fabrication check is measured against it.
        </p>
      </header>

      {/* Parsing needs a model, so ask for the key before the upload button rather
          than letting the user pick a file and then fail. */}
      {settings && (setupNeeded || setupTouched) && (
        <div className="card mb-6 border-brand/30 p-5">
          <ProviderSetup
            settings={settings}
            onSaved={(next) => {
              setSettings(next);
              setSetupTouched(true);
            }}
          />
        </div>
      )}

      <section className="card mb-6 p-5">
        <h2 className="font-bold">Upload</h2>
        <p className="mt-1 text-sm text-muted">
          PDF, DOCX, TXT, or MD. Parsing runs through your configured LLM provider and
          stays on this machine.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.docx,.txt,.md"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleUpload(file);
              e.target.value = "";
            }}
          />
          <button
            className="btn-primary"
            onClick={() => fileInput.current?.click()}
            disabled={busy}
          >
            {busy ? "Working…" : "Choose file"}
          </button>
          {!draft && (
            <button
              className="btn-ghost"
              onClick={() => {
                setDraft(EMPTY);
                setNeedsConfirm(true);
              }}
            >
              Start from scratch
            </button>
          )}
        </div>
      </section>

      {status && (
        <p className="card mb-6 border-brand/30 bg-brand-tint p-4 text-sm">{status}</p>
      )}
      {error && (
        <div className="card mb-6 border-gold/60 bg-gold/10 p-4">
          <p className="text-sm font-semibold">{error}</p>
          {settings && !setupNeeded && /key|ollama|provider|reach/i.test(error) && (
            <div className="mt-4 border-t border-gold/40 pt-4">
              <ProviderSetup settings={settings} onSaved={setSettings} compact />
            </div>
          )}
        </div>
      )}

      {draft && (
        <>
          {needsConfirm && (
            <div className="card mb-4 border-gold/60 bg-gold/10 p-4">
              <p className="text-sm font-bold">Confirm before saving</p>
              <p className="mt-1 text-sm text-muted">
                Automated parsing is imperfect — dates and bullet text are the usual
                casualties. An error here silently propagates into every application you
                send, so check it now rather than later.
              </p>
            </div>
          )}

          <div className="card mb-4 p-4">
            <label className="text-xs font-bold uppercase tracking-wide text-muted">
              Resume name
            </label>
            <input
              className="field mt-1"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <ResumeEditor value={draft} onChange={setDraft} />

          <div className="sticky bottom-0 mt-6 flex items-center justify-between gap-4 rounded-t-xl border-t border-line bg-white/95 px-4 py-4 backdrop-blur">
            <p className="text-xs text-muted">
              {existing && !needsConfirm
                ? "Editing your saved base resume."
                : "Not saved yet."}
            </p>
            <button className="btn-primary" onClick={handleSave} disabled={busy}>
              {busy ? "Saving…" : needsConfirm ? "Confirm & save" : "Save changes"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
