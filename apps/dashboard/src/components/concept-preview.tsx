"use client";

import { useState } from "react";

import type { RenderPage } from "@/lib/designs";

const VIEWPORTS = [
  { key: "desktop", label: "Desktop", width: "100%" },
  { key: "tablet", label: "Tablet", width: "768px" },
  { key: "mobile", label: "Mobile", width: "390px" },
] as const;

/** Six-page concept preview in a sandboxed frame: no scripts, forms, popups or top navigation. */
export function ConceptPreview({ renderId, pages }: { renderId: string; pages: RenderPage[] }) {
  const [slug, setSlug] = useState(pages[0]?.slug ?? "home");
  const [viewport, setViewport] = useState<(typeof VIEWPORTS)[number]["key"]>("desktop");
  const width = VIEWPORTS.find((v) => v.key === viewport)?.width ?? "100%";
  const title = pages.find((p) => p.slug === slug)?.title ?? slug;

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div role="tablist" aria-label="Concept pages" className="flex flex-wrap gap-1">
          {pages.map((p) => (
            <button
              key={p.slug}
              type="button"
              role="tab"
              aria-selected={p.slug === slug}
              onClick={() => setSlug(p.slug)}
              className={`min-h-9 rounded-lg px-3 text-sm ${
                p.slug === slug ? "bg-accent text-white" : "border border-line hover:bg-background"
              }`}
            >
              {p.title}
            </button>
          ))}
        </div>
        <div role="group" aria-label="Viewport" className="flex gap-1">
          {VIEWPORTS.map((v) => (
            <button
              key={v.key}
              type="button"
              aria-pressed={v.key === viewport}
              onClick={() => setViewport(v.key)}
              className={`min-h-9 rounded-lg px-3 text-sm ${
                v.key === viewport
                  ? "bg-foreground text-background"
                  : "border border-line hover:bg-background"
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>
      <div className="overflow-x-auto rounded-lg border border-line bg-background p-2">
        <iframe
          key={`${slug}-${viewport}`}
          title={`Concept preview: ${title} (${viewport})`}
          src={`/api/concepts/${renderId}/${slug}`}
          sandbox="allow-same-origin"
          referrerPolicy="no-referrer"
          loading="lazy"
          className="mx-auto block h-[70vh] max-w-full rounded border-0 bg-white"
          style={{ width }}
        />
      </div>
      <p className="text-xs text-muted">
        Links inside the frame move between concept pages. The inquiry form is a demo and cannot submit.
      </p>
    </div>
  );
}
