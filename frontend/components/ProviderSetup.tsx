"use client";

import { useEffect, useState } from "react";
import { api, type SettingsOut } from "@/lib/api";

/**
 * Inline "connect a model" card.
 *
 * Deliberately self-contained so it can appear wherever the user actually hits the wall
 * — the search page, the resume upload screen, or Settings — rather than forcing them to
 * go hunting through Settings after a failed action. Paste a key or point at Ollama and
 * test it, all without leaving the page.
 */

const PROVIDERS = [
  {
    id: "anthropic",
    label: "Anthropic",
    blurb: "Recommended",
    placeholder: "sk-ant-…",
    keyUrl: "https://console.anthropic.com/settings/keys",
    defaultModel: "claude-opus-4-8",
  },
  {
    id: "openai",
    label: "OpenAI",
    blurb: "Or any OpenAI-compatible endpoint",
    placeholder: "sk-…",
    keyUrl: "https://platform.openai.com/api-keys",
    defaultModel: "gpt-4o",
  },
  {
    id: "ollama",
    label: "Local (Ollama)",
    blurb: "Free, fully offline",
    placeholder: "",
    keyUrl: "https://ollama.com/download",
    defaultModel: "qwen2.5:7b",
  },
] as const;

export default function ProviderSetup({
  settings,
  onSaved,
  compact = false,
}: {
  settings: SettingsOut;
  onSaved: (next: SettingsOut) => void;
  compact?: boolean;
}) {
  const [provider, setProvider] = useState(settings.llm_provider);
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(settings.model);
  const [host, setHost] = useState(settings.ollama_host);
  const [baseUrl, setBaseUrl] = useState(settings.openai_base_url);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; detail: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const active = PROVIDERS.find((p) => p.id === provider) ?? PROVIDERS[0];
  const isLocal = provider === "ollama";

  // Switching provider changes which model string is valid, so reset to that
  // provider's default rather than carrying a stale one across.
  useEffect(() => {
    setModel(settings.llm_provider === provider ? settings.model : "");
    setResult(null);
  }, [provider, settings.llm_provider, settings.model]);

  async function saveAndTest() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const patch: Record<string, unknown> = { llm_provider: provider };
      if (model.trim()) patch.model = model.trim();
      if (apiKey.trim()) patch.api_key = apiKey.trim();
      if (isLocal) patch.ollama_host = host.trim();
      if (provider === "openai") patch.openai_base_url = baseUrl.trim();

      const next = await api.saveSettings(patch);
      onSaved(next);
      setApiKey("");

      // Test immediately. Finding out here beats finding out mid-apply.
      setResult(await api.testLlm());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  const canSubmit = isLocal || apiKey.trim().length > 0 || settings.has_key;

  return (
    <section className={compact ? "" : "card p-5"}>
      {!compact && (
        <>
          <h2 className="font-bold">Connect a model</h2>
          <p className="mt-1 text-sm text-muted">
            Needed to read your resume and tailor it. Your key is stored on this machine
            only and is never sent anywhere except the provider you pick.
          </p>
        </>
      )}

      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        {PROVIDERS.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => setProvider(p.id)}
            className={`rounded-xl border p-3 text-left transition-colors ${
              provider === p.id
                ? "border-brand bg-brand-tint"
                : "border-line hover:border-brand/40"
            }`}
          >
            <span className="block text-sm font-bold">{p.label}</span>
            <span className="block text-xs text-muted">{p.blurb}</span>
          </button>
        ))}
      </div>

      <div className="mt-3 grid gap-3">
        {!isLocal ? (
          <label className="block">
            <span className="flex items-center justify-between text-xs font-bold uppercase tracking-wide text-muted">
              <span>
                API key
                {settings.has_key && provider === settings.llm_provider && (
                  <span className="ml-1 text-brand">· saved</span>
                )}
              </span>
              <a
                href={active.keyUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="font-semibold normal-case text-brand hover:underline"
              >
                Get a key ↗
              </a>
            </span>
            <input
              className="field mt-1 font-mono text-xs"
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={apiKey}
              placeholder={
                settings.has_key && provider === settings.llm_provider
                  ? "••••••••••  (leave blank to keep the saved key)"
                  : active.placeholder
              }
              onChange={(e) => setApiKey(e.target.value)}
            />
          </label>
        ) : (
          <label className="block">
            <span className="flex items-center justify-between text-xs font-bold uppercase tracking-wide text-muted">
              <span>Ollama host</span>
              <a
                href={active.keyUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="font-semibold normal-case text-brand hover:underline"
              >
                Install Ollama ↗
              </a>
            </span>
            <input
              className="field mt-1 font-mono text-xs"
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder="http://localhost:11434"
            />
          </label>
        )}

        {provider === "openai" && (
          <label className="block">
            <span className="text-xs font-bold uppercase tracking-wide text-muted">
              Base URL
            </span>
            <input
              className="field mt-1 font-mono text-xs"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
            />
            <span className="mt-1 block text-xs text-muted">
              Change this to use Groq, Together, OpenRouter, or a local LM Studio server.
            </span>
          </label>
        )}

        <label className="block">
          <span className="text-xs font-bold uppercase tracking-wide text-muted">
            Model <span className="normal-case">(optional)</span>
          </span>
          <input
            className="field mt-1 font-mono text-xs"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={active.defaultModel}
          />
        </label>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="btn-primary"
          onClick={saveAndTest}
          disabled={busy || !canSubmit}
        >
          {busy ? "Testing…" : "Save & test connection"}
        </button>
        {result && (
          <span
            role="status"
            className={`text-sm font-semibold ${result.ok ? "text-brand" : ""}`}
          >
            {result.ok ? "✓ Connected — " : "✕ "}
            <span className="font-normal text-muted">{result.detail}</span>
          </span>
        )}
        {error && <span className="text-sm">{error}</span>}
      </div>

      {isLocal && (
        <p className="mt-3 text-xs leading-relaxed text-muted">
          Ollama must be running (<code className="rounded bg-page px-1">ollama serve</code>
          ) with the model pulled (
          <code className="rounded bg-page px-1">
            ollama pull {model || active.defaultModel}
          </code>
          ). Smaller local models make more parsing mistakes — review the confirm screen
          carefully.
        </p>
      )}
    </section>
  );
}
