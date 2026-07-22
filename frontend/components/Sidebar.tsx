"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Search", icon: SearchIcon },
  { href: "/resume", label: "Resume", icon: DocIcon },
  { href: "/applications", label: "Applications", icon: ListIcon },
  { href: "/settings", label: "Settings", icon: GearIcon },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-60 shrink-0 border-r border-line bg-white px-4 py-6 hidden md:flex md:flex-col">
      <Link href="/" className="flex items-center gap-2 px-2 pb-8">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand text-white font-bold">
          S
        </span>
        <span className="text-lg font-bold tracking-tight">SimplyApply</span>
      </Link>

      <nav className="flex flex-col gap-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${
                active
                  ? "bg-brand-tint text-brand"
                  : "text-muted hover:bg-page hover:text-ink"
              }`}
            >
              <Icon />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto rounded-xl bg-page p-3 text-xs leading-relaxed text-muted">
        Your resume and API keys stay on this machine. Nothing is uploaded anywhere.
      </div>
    </aside>
  );
}

/* Inline SVGs rather than an icon package — four icons isn't worth a dependency. */
const strokeProps = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function SearchIcon() {
  return (
    <svg {...strokeProps} aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

function DocIcon() {
  return (
    <svg {...strokeProps} aria-hidden>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5M9 13h6M9 17h4" />
    </svg>
  );
}

function ListIcon() {
  return (
    <svg {...strokeProps} aria-hidden>
      <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg {...strokeProps} aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9c.14.6.66 1.03 1.28 1.05H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}
