"use client";

import { useMemo } from "react";

import type { SectionRecord, SourceSpanRecord } from "../lib/contracts";
import { resolveSegmentSelection, segmentSection } from "../lib/spans";

export interface DocumentPaneProps {
  sections: SectionRecord[];
  spans: SourceSpanRecord[];
  selectedSpanId: string | null;
  onSelectSpan: (spanId: string | null) => void;
}

function headingLevel(depth: number): "h2" | "h3" | "h4" {
  if (depth <= 1) return "h2";
  if (depth === 2) return "h3";
  return "h4";
}

/**
 * Rendered document content synchronized with the extracted sections. Source
 * spans are highlighted with background + dotted underline + a citation glyph
 * (never color alone) and are focusable buttons that drive the fact panel.
 *
 * Clicking (or keyboard-activating — the segments are real buttons) a segment
 * covered by several spans selects the NARROWEST covering span so nested
 * spans stay reachable; activating a segment whose covering spans include the
 * current selection toggles it off.
 *
 * Layout: a <button> can never be a true inline box. Browsers render
 * `display: inline` on a button as an atomic inline-block (HTML rendering
 * spec, "The button element"), which cannot break across lines, so a long
 * cited sentence used to become a full-width, UA-centred block that split
 * its surrounding sentence. The highlighted text is therefore a plain inline
 * span that wraps with the paragraph, and the real button (named by that
 * text via aria-labelledby, still `aria-pressed`) sits inline right after it
 * as the citation glyph.
 */
export function DocumentPane({ sections, spans, selectedSpanId, onSelectSpan }: DocumentPaneProps) {
  // Memoized so selection changes re-render without re-segmenting every
  // section. Span offsets are GLOBAL canonical offsets; segmentSection derives
  // the section-local render anchors internally (last-moment derivation).
  const segmentedSections = useMemo(
    () =>
      sections.map((section) => ({
        section,
        segments: segmentSection(section, spans),
      })),
    [sections, spans],
  );
  // Span length is coordinate-system independent (global end - global start).
  const spanLengthById = useMemo(
    () =>
      new Map(spans.map((record) => [record.id, record.span.end_char - record.span.start_char])),
    [spans],
  );

  return (
    <article className="document-pane" aria-label="Filing content">
      {segmentedSections.map(({ section, segments }) => {
        const Heading = headingLevel(section.level);
        return (
          <section key={section.id} id={`section-${section.id}`} aria-label={section.title}>
            <Heading className={`section-heading depth-${section.level}`}>{section.title}</Heading>
            <p className="section-content">
              {segments.map((segment) => {
                const key = `${section.id}-${segment.start}`;
                if (segment.spanIds.length === 0) {
                  return <span key={key}>{segment.text}</span>;
                }
                const pressed = segment.spanIds.includes(selectedSpanId ?? "");
                const activate = () =>
                  onSelectSpan(
                    resolveSegmentSelection(segment.spanIds, selectedSpanId, spanLengthById),
                  );
                return (
                  <span key={key} className="span-cite" data-pressed={pressed}>
                    {/* Visible cited text, a plain inline box so it flows
                        and wraps with its sentence. Hidden from AT because
                        the button below carries it as its name; a pointer
                        click on it activates (and focuses) that button. */}
                    <span
                      id={`cite-text-${key}`}
                      className="span-text"
                      aria-hidden="true"
                      onClick={(event) => {
                        activate();
                        (event.currentTarget.nextElementSibling as HTMLElement | null)?.focus();
                      }}
                    >
                      {segment.text}
                    </span>
                    <button
                      type="button"
                      className="span-mark"
                      aria-pressed={pressed}
                      aria-labelledby={`cite-label-${key} cite-text-${key}`}
                      data-span-ids={segment.spanIds.join(" ")}
                      onClick={activate}
                    >
                      <span id={`cite-label-${key}`} className="visually-hidden">
                        Cited source span:{" "}
                      </span>
                      <span className="span-glyph" aria-hidden="true">
                        &dagger;
                      </span>
                    </button>
                  </span>
                );
              })}
            </p>
          </section>
        );
      })}
    </article>
  );
}
