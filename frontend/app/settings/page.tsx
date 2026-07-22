"use client";

import { useEffect, useState } from "react";
import ProviderSetup from "@/components/ProviderSetup";
import { api, type SettingsOut } from "@/lib/api";

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsOut | null>(null);
  const [sources, setSources] = useState<Record<string, string>>({});
  const [companies, setCompanies] = useState("");
  const [capabilities, setCapabilities] = useState<{
    pdf: boolean;
    pdf_detail: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.settings(),
      api.sources(),
      api.capabilities(),
      api.greenhouseCompanies(),
    ])
      .then(([s, src, caps, cos]) => {
        setSettings(s);
        setSources(src);
        setCapabilities(caps);
        setCompanies(cos.join("\n"));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Load failed."));
  }, []);

  if (error && !settings) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-8">
        <p className="card border-gold/60 bg-gold/10 p-4 text-sm">{error}</p>
      </div>
    );
  }
  if (!settings) {
    return <p className="px-6 py-8 text-sm text-muted">Loading…</p>;
  }

  async function save(patch: Record<string, unknown>) {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      setSettings(await api.saveSettings(patch));
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted">
          Stored in the local SQLite database. Keys never leave this machine and are never
          returned by the API once saved.
        </p>
      </header>

      {error && (
        <p className="card mb-4 border-gold/60 bg-gold/10 p-4 text-sm">{error}</p>
      )}
      {saved && (
        <p className="card mb-4 border-brand/30 bg-brand-tint p-4 text-sm">Saved.</p>
      )}

      {/* Same component the search and resume pages use, so there is exactly one
          implementation of "connect a model" to keep correct. */}
      <div className="mb-4">
        <ProviderSetup settings={settings} onSaved={setSettings} />
      </div>

      {/* ---------------- sources ---------------- */}
      <section className="card mb-4 p-5">
        <h2 className="font-bold">Job sources</h2>
        <p className="mt-1 text-sm text-muted">
          A source that fails is reported in the results header rather than silently
          dropped.
        </p>
        <div className="mt-3 flex flex-col gap-2">
          {settings.available_sources.map((source) => {
            const enabled = settings.enabled_sources.includes(source);
            return (
              <label
                key={source}
                className="flex cursor-pointer items-center gap-3 text-sm"
              >
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-[#12a1c0]"
                  checked={enabled}
                  onChange={() =>
                    save({
                      enabled_sources: enabled
                        ? settings.enabled_sources.filter((s) => s !== source)
                        : [...settings.enabled_sources, source],
                    })
                  }
                />
                {sources[source] ?? source}
              </label>
            );
          })}
        </div>
      </section>

      {/* ---------------- greenhouse ---------------- */}
      <section className="card mb-4 p-5">
        <h2 className="font-bold">Greenhouse companies</h2>
        <p className="mt-1 text-sm text-muted">
          Greenhouse serves one board per company — there is no global search — so this
          list defines what gets searched. One slug per line, taken from{" "}
          <code className="rounded bg-page px-1">
            boards.greenhouse.io/<b>slug</b>
          </code>
          .
        </p>
        <textarea
          className="field mt-3 min-h-[160px] resize-y font-mono text-xs"
          value={companies}
          onChange={(e) => setCompanies(e.target.value)}
        />
        <button
          className="btn-primary mt-3"
          disabled={busy}
          onClick={() =>
            save({
              greenhouse_companies: companies
                .split("\n")
                .map((c) => c.trim())
                .filter(Boolean),
            })
          }
        >
          Save companies
        </button>
      </section>

      {/* ---------------- capabilities ---------------- */}
      <section className="card p-5">
        <h2 className="font-bold">This install</h2>
        <dl className="mt-3 grid gap-2 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-muted">DOCX rendering</dt>
            <dd className="font-semibold text-brand">Available</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-muted">PDF rendering</dt>
            <dd className={capabilities?.pdf ? "font-semibold text-brand" : "text-muted"}>
              {capabilities?.pdf ? "Available · single page" : "Unavailable"}
            </dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-muted">Search cache TTL</dt>
            <dd>{settings.cache_ttl_minutes} min</dd>
          </div>
        </dl>
        {capabilities && !capabilities.pdf && (
          <p className="mt-3 text-xs leading-relaxed text-muted">
            {capabilities.pdf_detail}
          </p>
        )}
      </section>
    </div>
  );
}
