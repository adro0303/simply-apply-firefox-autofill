"use client";

import type {
  Education,
  Project,
  Skill,
  StructuredResume,
  Work,
} from "@/lib/api";

/**
 * Structured resume editor — the confirm screen after parsing, and the edit screen after.
 *
 * Every field is editable because the parse is never trusted. The whole design of the app
 * assumes this document is correct; this is the only place the user can make it so.
 */
export default function ResumeEditor({
  value,
  onChange,
}: {
  value: StructuredResume;
  onChange: (next: StructuredResume) => void;
}) {
  const patch = (partial: Partial<StructuredResume>) =>
    onChange({ ...value, ...partial });

  return (
    <div className="flex flex-col gap-4">
      {/* ---------------- basics ---------------- */}
      <Section title="Basics">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            label="Full name"
            value={value.basics.name}
            onChange={(v) => patch({ basics: { ...value.basics, name: v } })}
          />
          <Field
            label="Headline"
            value={value.basics.label}
            onChange={(v) => patch({ basics: { ...value.basics, label: v } })}
          />
          <Field
            label="Email"
            value={value.basics.email}
            onChange={(v) => patch({ basics: { ...value.basics, email: v } })}
          />
          <Field
            label="Phone"
            value={value.basics.phone}
            onChange={(v) => patch({ basics: { ...value.basics, phone: v } })}
          />
          <Field
            label="City"
            value={value.basics.location.city}
            onChange={(v) =>
              patch({
                basics: {
                  ...value.basics,
                  location: { ...value.basics.location, city: v },
                },
              })
            }
          />
          <Field
            label="Region / state"
            value={value.basics.location.region}
            onChange={(v) =>
              patch({
                basics: {
                  ...value.basics,
                  location: { ...value.basics.location, region: v },
                },
              })
            }
          />
        </div>
        <TextArea
          label="Summary"
          value={value.basics.summary}
          onChange={(v) => patch({ basics: { ...value.basics, summary: v } })}
        />
      </Section>

      {/* ---------------- experience ---------------- */}
      <Section
        title="Experience"
        onAdd={() =>
          patch({
            work: [
              ...value.work,
              {
                name: "",
                position: "",
                url: "",
                startDate: "",
                endDate: "",
                location: "",
                summary: "",
                highlights: [],
              },
            ],
          })
        }
      >
        {value.work.map((job, i) => (
          <Card
            key={i}
            onRemove={() => patch({ work: value.work.filter((_, j) => j !== i) })}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <Field
                label="Job title"
                value={job.position}
                onChange={(v) => patch({ work: replace(value.work, i, { position: v }) })}
              />
              <Field
                label="Employer"
                value={job.name}
                onChange={(v) => patch({ work: replace(value.work, i, { name: v }) })}
              />
              <Field
                label="Start"
                placeholder="2022-01"
                value={job.startDate}
                onChange={(v) =>
                  patch({ work: replace(value.work, i, { startDate: v }) })
                }
              />
              <Field
                label="End"
                placeholder="Present"
                value={job.endDate}
                onChange={(v) => patch({ work: replace(value.work, i, { endDate: v }) })}
              />
              <Field
                label="Location"
                value={job.location}
                onChange={(v) => patch({ work: replace(value.work, i, { location: v }) })}
              />
            </div>
            <ListField
              label="Bullets"
              items={job.highlights}
              onChange={(items) =>
                patch({ work: replace(value.work, i, { highlights: items }) })
              }
            />
          </Card>
        ))}
      </Section>

      {/* ---------------- education ---------------- */}
      <Section
        title="Education"
        onAdd={() =>
          patch({
            education: [
              ...value.education,
              {
                institution: "",
                area: "",
                studyType: "",
                startDate: "",
                endDate: "",
                score: "",
                courses: [],
              },
            ],
          })
        }
      >
        {value.education.map((edu, i) => (
          <Card
            key={i}
            onRemove={() =>
              patch({ education: value.education.filter((_, j) => j !== i) })
            }
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <Field
                label="Institution"
                value={edu.institution}
                onChange={(v) =>
                  patch({ education: replace(value.education, i, { institution: v }) })
                }
              />
              <Field
                label="Degree"
                placeholder="BSc"
                value={edu.studyType}
                onChange={(v) =>
                  patch({ education: replace(value.education, i, { studyType: v }) })
                }
              />
              <Field
                label="Field of study"
                value={edu.area}
                onChange={(v) =>
                  patch({ education: replace(value.education, i, { area: v }) })
                }
              />
              <Field
                label="GPA / score"
                value={edu.score}
                onChange={(v) =>
                  patch({ education: replace(value.education, i, { score: v }) })
                }
              />
              <Field
                label="Start"
                value={edu.startDate}
                onChange={(v) =>
                  patch({ education: replace(value.education, i, { startDate: v }) })
                }
              />
              <Field
                label="End"
                value={edu.endDate}
                onChange={(v) =>
                  patch({ education: replace(value.education, i, { endDate: v }) })
                }
              />
            </div>
          </Card>
        ))}
      </Section>

      {/* ---------------- skills ---------------- */}
      <Section
        title="Skills"
        hint="Group related skills. Tailoring can reorder and surface these, but never add new ones."
        onAdd={() =>
          patch({ skills: [...value.skills, { name: "", level: "", keywords: [] }] })
        }
      >
        {value.skills.map((skill, i) => (
          <Card
            key={i}
            onRemove={() => patch({ skills: value.skills.filter((_, j) => j !== i) })}
          >
            <Field
              label="Category"
              placeholder="Languages"
              value={skill.name}
              onChange={(v) => patch({ skills: replace(value.skills, i, { name: v }) })}
            />
            <Field
              label="Skills (comma separated)"
              value={skill.keywords.join(", ")}
              onChange={(v) =>
                patch({
                  skills: replace(value.skills, i, {
                    keywords: v
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  }),
                })
              }
            />
          </Card>
        ))}
      </Section>

      {/* ---------------- projects ---------------- */}
      <Section
        title="Projects"
        onAdd={() =>
          patch({
            projects: [
              ...value.projects,
              {
                name: "",
                description: "",
                url: "",
                startDate: "",
                endDate: "",
                highlights: [],
                keywords: [],
              },
            ],
          })
        }
      >
        {value.projects.map((project, i) => (
          <Card
            key={i}
            onRemove={() => patch({ projects: value.projects.filter((_, j) => j !== i) })}
          >
            <Field
              label="Name"
              value={project.name}
              onChange={(v) =>
                patch({ projects: replace(value.projects, i, { name: v }) })
              }
            />
            <TextArea
              label="Description"
              value={project.description}
              onChange={(v) =>
                patch({ projects: replace(value.projects, i, { description: v }) })
              }
            />
            <ListField
              label="Bullets"
              items={project.highlights}
              onChange={(items) =>
                patch({ projects: replace(value.projects, i, { highlights: items }) })
              }
            />
            <Field
              label="Technologies (comma separated)"
              value={project.keywords.join(", ")}
              onChange={(v) =>
                patch({
                  projects: replace(value.projects, i, {
                    keywords: v
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  }),
                })
              }
            />
          </Card>
        ))}
      </Section>
    </div>
  );
}

function replace<T>(items: T[], index: number, patch: Partial<T>): T[] {
  return items.map((item, i) => (i === index ? { ...item, ...patch } : item));
}

function Section({
  title,
  hint,
  onAdd,
  children,
}: {
  title: string;
  hint?: string;
  onAdd?: () => void;
  children: React.ReactNode;
}) {
  return (
    <section className="card p-5">
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <h2 className="font-bold">{title}</h2>
          {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
        </div>
        {onAdd && (
          <button
            onClick={onAdd}
            className="shrink-0 rounded-full border border-line px-3 py-1 text-xs font-semibold hover:border-brand hover:text-brand"
          >
            + Add
          </button>
        )}
      </div>
      <div className="flex flex-col gap-3">{children}</div>
    </section>
  );
}

function Card({
  onRemove,
  children,
}: {
  onRemove: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="relative rounded-xl border border-line bg-page p-4">
      <button
        onClick={onRemove}
        className="absolute right-3 top-3 text-xs font-semibold text-muted hover:text-ink"
        aria-label="Remove"
      >
        Remove
      </button>
      <div className="flex flex-col gap-3 pr-16">{children}</div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="text-xs font-bold uppercase tracking-wide text-muted">
        {label}
      </span>
      <input
        className="field mt-1"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function TextArea({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <span className="text-xs font-bold uppercase tracking-wide text-muted">
        {label}
      </span>
      <textarea
        className="field mt-1 min-h-[80px] resize-y"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function ListField({
  label,
  items,
  onChange,
}: {
  label: string;
  items: string[];
  onChange: (items: string[]) => void;
}) {
  return (
    <div>
      <span className="text-xs font-bold uppercase tracking-wide text-muted">
        {label}
      </span>
      <div className="mt-1 flex flex-col gap-2">
        {items.map((item, i) => (
          <div key={i} className="flex gap-2">
            <textarea
              className="field min-h-[44px] flex-1 resize-y"
              value={item}
              onChange={(e) =>
                onChange(items.map((it, j) => (j === i ? e.target.value : it)))
              }
            />
            <button
              onClick={() => onChange(items.filter((_, j) => j !== i))}
              className="shrink-0 self-start rounded-lg border border-line px-2 py-2 text-xs text-muted hover:text-ink"
              aria-label="Remove bullet"
            >
              ✕
            </button>
          </div>
        ))}
        <button
          onClick={() => onChange([...items, ""])}
          className="w-fit rounded-full border border-line px-3 py-1 text-xs font-semibold hover:border-brand hover:text-brand"
        >
          + Add bullet
        </button>
      </div>
    </div>
  );
}
