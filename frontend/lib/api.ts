/**
 * Typed client for the FastAPI backend.
 *
 * Everything goes through the Next rewrite at /api, so there is no base URL to configure
 * and no CORS involved.
 */

export type JobRecord = {
  id: string;
  source: string;
  title: string;
  company: string;
  location: string;
  remote: boolean;
  salary_min: number | null;
  salary_max: number | null;
  currency: string | null;
  posted_at: string | null;
  apply_url: string;
  description: string;
};

export type SearchResponse = {
  jobs: JobRecord[];
  sources_ok: string[];
  sources_failed: Record<string, string>;
  from_cache: boolean;
};

export type Work = {
  name: string;
  position: string;
  url: string;
  startDate: string;
  endDate: string;
  location: string;
  summary: string;
  highlights: string[];
};

export type Education = {
  institution: string;
  area: string;
  studyType: string;
  startDate: string;
  endDate: string;
  score: string;
  courses: string[];
};

export type Skill = { name: string; level: string; keywords: string[] };

export type Project = {
  name: string;
  description: string;
  url: string;
  startDate: string;
  endDate: string;
  highlights: string[];
  keywords: string[];
};

export type StructuredResume = {
  basics: {
    name: string;
    label: string;
    email: string;
    phone: string;
    url: string;
    summary: string;
    location: { city: string; region: string; countryCode: string };
    profiles: { network: string; username: string; url: string }[];
  };
  work: Work[];
  education: Education[];
  skills: Skill[];
  projects: Project[];
};

export type ResumeOut = {
  id: number;
  name: string;
  is_base: boolean;
  created_at: string;
  tailored_for_job_id: string | null;
  data: StructuredResume;
};

export type GuardrailViolation = {
  kind: string;
  value: string;
  where: string;
  detail: string;
};

export type TailorResult = {
  resume: StructuredResume;
  changed: boolean;
  fell_back: boolean;
  violations: GuardrailViolation[];
  warning: string | null;
  notes: string[];
};

export type ApplyResponse = {
  application_id: number;
  resume_id: number;
  job: JobRecord;
  docx_url: string | null;
  pdf_url: string | null;
  pdf_error: string | null;
  tailoring: TailorResult;
};

export type ApplicationOut = {
  id: number;
  job_id: string;
  resume_id: number;
  applied_at: string;
  status: string;
  notes: string;
  title: string;
  company: string;
  apply_url: string;
  docx_url: string | null;
  pdf_url: string | null;
};

export type SettingsOut = {
  llm_provider: string;
  model: string;
  has_key: boolean;
  ollama_host: string;
  openai_base_url: string;
  enabled_sources: string[];
  available_sources: string[];
  cache_ttl_minutes: number;
};

/**
 * True when the app can't possibly reach a model yet.
 *
 * Conservative on purpose: for cloud providers a missing key is definitive, but Ollama
 * needs no key and we can't tell whether it's actually running without a network probe.
 * So we don't nag local users on page load — they'll get the real answer from
 * "Save & test connection", or from the error surfaced at the point of failure.
 */
export function needsProviderSetup(settings: SettingsOut): boolean {
  if (settings.llm_provider === "ollama") return false;
  return !settings.has_key;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...init?.headers,
    },
  });

  if (!res.ok) {
    // FastAPI puts the actionable message in `detail`; surface it rather than a status code.
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {
      /* non-JSON error body — keep the generic message */
    }
    throw new Error(message);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  search: (q: string, location: string, remoteOnly: boolean) =>
    request<SearchResponse>(
      `/api/search?q=${encodeURIComponent(q)}&location=${encodeURIComponent(
        location,
      )}&remote_only=${remoteOnly}`,
    ),

  sources: () => request<Record<string, string>>("/api/sources"),

  parseResume: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ data: StructuredResume; extracted_text: string }>(
      "/api/resumes/parse",
      { method: "POST", body: form },
    );
  },

  saveResume: (name: string, data: StructuredResume) =>
    request<ResumeOut>("/api/resumes", {
      method: "POST",
      body: JSON.stringify({ name, data }),
    }),

  updateResume: (id: number, name: string, data: StructuredResume) =>
    request<ResumeOut>(`/api/resumes/${id}`, {
      method: "PUT",
      body: JSON.stringify({ name, data }),
    }),

  baseResume: () => request<ResumeOut | null>("/api/resumes/base"),

  apply: (jobId: string) =>
    request<ApplyResponse>(`/api/apply/${encodeURIComponent(jobId)}`, {
      method: "POST",
    }),

  applications: () => request<ApplicationOut[]>("/api/applications"),

  updateApplication: (id: number, patch: { status?: string; notes?: string }) =>
    request<ApplicationOut>(`/api/applications/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  deleteApplication: (id: number) =>
    request<{ ok: boolean }>(`/api/applications/${id}`, { method: "DELETE" }),

  settings: () => request<SettingsOut>("/api/settings"),

  saveSettings: (patch: Record<string, unknown>) =>
    request<SettingsOut>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(patch),
    }),

  testLlm: () =>
    request<{ ok: boolean; detail: string; provider?: string }>(
      "/api/settings/test-llm",
      { method: "POST" },
    ),

  capabilities: () =>
    request<{ pdf: boolean; pdf_detail: string }>("/api/settings/capabilities"),

  greenhouseCompanies: () =>
    request<string[]>("/api/settings/greenhouse-companies"),
};
