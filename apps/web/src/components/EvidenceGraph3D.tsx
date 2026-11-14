"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { EvidenceSourceId, GuidanceApproval, ReviewDecision } from "../app/desk/desk-state";
import "../styles/lineage-graph.css";

export type CameraPreset = "constellation" | "dag" | "temporal";
export type ProvenanceLayer = "reported" | "extraction" | "calculation" | "output";
export type NodeState =
  "verified" | "fixture" | "conflict" | "pending" | "override" | "cutoff-blocked";

export interface GraphNode3D {
  id: string;
  label: string;
  /** Compact form shown on the graph when there is no room for the full label. */
  shortLabel: string;
  sublabel: string;
  layer: ProvenanceLayer;
  x: number;
  y: number;
  z: number;
  publishedStep: 0 | 1 | 2;
  publishedAt: string;
  formulaOrHash: string;
  state: NodeState;
}

export interface GraphEdge3D {
  from: string;
  to: string;
  active: boolean;
  kind: "provenance" | "conflict" | "scenario" | "iteration";
}

export interface CutoffStop {
  step: 0 | 1 | 2;
  iso: string;
  label: string;
  description: string;
}

export const CUTOFF_STOPS: readonly CutoffStop[] = [
  {
    step: 0,
    iso: "2026-07-31T23:59:00Z",
    label: "Q2 Close (2026-07-31)",
    description: "Both Q2 10-Q and Earnings Call are in the future (blocked by cutoff).",
  },
  {
    step: 1,
    iso: "2026-08-14T16:15:00Z",
    label: "10-Q Filed (16:15 UTC)",
    description: "10-Q spans are visible; Earnings Call (17:30 UTC) is fenced out by cutoff.",
  },
  {
    step: 2,
    iso: "2026-08-14T18:00:00Z",
    label: "Post-Call (18:00 UTC)",
    description:
      "All Q2 10-Q and Earnings Call evidence spans satisfy published_at <= effective_as_of.",
  },
];

export interface EvidenceGraph3DProps {
  scenario: string;
  source: EvidenceSourceId | null;
  decision: ReviewDecision | null;
  approvals: GuidanceApproval[];
  applied: boolean;
  onSelectNode?: (nodeId: string) => void;
}

function presetAngles(preset: CameraPreset): { yaw: number; pitch: number } {
  switch (preset) {
    case "constellation":
      return { yaw: 0.48, pitch: 0.32 };
    case "dag":
      return { yaw: 0.0, pitch: 0.08 };
    case "temporal":
      return { yaw: -1.15, pitch: 0.22 };
    default: {
      const _never: never = preset;
      return _never;
    }
  }
}

function nodeColor(state: NodeState): { fill: string; ring: string; badge: string } {
  switch (state) {
    case "verified":
      return { fill: "#2ea043", ring: "#56d364", badge: "Verified" };
    case "fixture":
      return { fill: "#6e7681", ring: "#8b949e", badge: "Fixture" };
    case "conflict":
      return { fill: "#d29922", ring: "#f0c96f", badge: "Conflict / Gate" };
    case "pending":
      return { fill: "#388bfd", ring: "#79c0ff", badge: "Pending Review" };
    case "override":
      return { fill: "#a371f7", ring: "#d2a8ff", badge: "Scenario / Calc" };
    case "cutoff-blocked":
      return { fill: "#da3633", ring: "#ff7b72", badge: "Blocked (Future)" };
    default: {
      const _never: never = state;
      return _never;
    }
  }
}

function edgePalette(kind: GraphEdge3D["kind"]): {
  stroke: string;
  width: number;
  pulse: string;
} {
  switch (kind) {
    case "conflict":
      return { stroke: "rgba(210, 153, 34, 0.78)", width: 2, pulse: "#f0c96f" };
    case "scenario":
      return { stroke: "rgba(163, 113, 247, 0.85)", width: 2.2, pulse: "#d2a8ff" };
    case "iteration":
      return { stroke: "rgba(88, 166, 255, 0.85)", width: 2.2, pulse: "#79c0ff" };
    case "provenance":
      return { stroke: "rgba(63, 185, 80, 0.82)", width: 2.2, pulse: "#56d364" };
    default: {
      const _never: never = kind;
      return _never;
    }
  }
}

function layerTitle(layer: ProvenanceLayer): string {
  switch (layer) {
    case "reported":
      return "L0 · Immutable Source Spans";
    case "extraction":
      return "L1 · Extraction & Review Gates";
    case "calculation":
      return "L2 · Decimal Calc DAG & Scenarios";
    case "output":
      return "L3 · Reported Financial Output";
    default: {
      const _never: never = layer;
      return _never;
    }
  }
}

export function buildEpistemicGraph(props: {
  scenario: string;
  source: EvidenceSourceId | null;
  decision: ReviewDecision | null;
  approvals: GuidanceApproval[];
  applied: boolean;
  cutoffStep: 0 | 1 | 2;
}): { nodes: GraphNode3D[]; edges: GraphEdge3D[] } {
  const { scenario, source, decision, approvals, applied, cutoffStep } = props;
  const revApproved = approvals.find((a) => a.claimId === "C-109-revenue")?.approved ?? false;
  const gmApproved = approvals.find((a) => a.claimId === "C-109-gross-margin")?.approved ?? false;
  const effectiveSource = decision?.sourceId ?? source;

  // A saved decision is temporally admissible only if its underlying source span
  // was published at or before the effective cutoff.
  const decisionAdmissible =
    decision !== null && (decision.sourceId === "sec-10q-nrr" ? cutoffStep >= 1 : cutoffStep >= 2);

  const revenueByScenario: Record<string, string> = {
    Base: "$842.4m",
    Bull: "$857.1m",
    Bear: "$823.8m",
  };
  const scenarioDeltaByScenario: Record<string, string> = {
    Base: "+0.0% Base",
    Bull: "+$14.7m (+1.7%)",
    Bear: "-$18.6m (-2.2%)",
  };
  const outputElevationByScenario: Record<string, number> = {
    Base: -118,
    Bull: -128,
    Bear: -108,
  };

  const rawNodes: Omit<GraphNode3D, "state">[] = [
    {
      id: "sec-10q-nrr",
      label: "10-Q Span · NRR 108%",
      shortLabel: "10-Q NRR",
      sublabel: "Page 34 · fixture span",
      layer: "reported",
      x: -170,
      y: 112,
      z: -60,
      publishedStep: 1,
      publishedAt: "2026-08-14T16:05:00Z",
      formulaOrHash: "start_char=48120..48192 · fixture, no content hash",
    },
    {
      id: "call-turn-48",
      label: "Call Turn 48 · NRR 109%",
      shortLabel: "Call NRR",
      sublabel: "Transcript · fixture turn",
      layer: "reported",
      x: -58,
      y: 112,
      z: 65,
      publishedStep: 2,
      publishedAt: "2026-08-14T17:30:00Z",
      formulaOrHash: "turn=48 · fixture, no content hash",
    },
    {
      id: "sec-10q-guidance",
      label: "10-Q Span · Guidance",
      shortLabel: "10-Q Guide",
      sublabel: "Page 42 · $790–794m",
      layer: "reported",
      x: 62,
      y: 112,
      z: -45,
      publishedStep: 1,
      publishedAt: "2026-08-14T16:05:00Z",
      formulaOrHash: "start_char=61004..61118 · fixture, no content hash",
    },
    {
      id: "sec-10q-actuals",
      label: "10-Q Fact · ARR $782m",
      shortLabel: "10-Q ARR",
      sublabel: "Page 12 · XBRL us-gaap",
      layer: "reported",
      x: 174,
      y: 112,
      z: 50,
      publishedStep: 1,
      publishedAt: "2026-08-14T16:05:00Z",
      formulaOrHash: "fact_id=arr-2026q2 · scale=10^6",
    },
    {
      id: "gate-c104",
      label: decisionAdmissible
        ? `C-104 Resolved (${decision.sourceId === "sec-10q-nrr" ? "108%" : "109%"})`
        : "C-104 NRR Conflict",
      shortLabel: decisionAdmissible
        ? `C-104 ${decision.sourceId === "sec-10q-nrr" ? "108%" : "109%"}`
        : "C-104 NRR",
      sublabel: decisionAdmissible
        ? "Human rationale recorded"
        : decision
          ? "Selected source blocked by cutoff"
          : "10-Q 108% vs Call 109%",
      layer: "extraction",
      x: -115,
      y: 36,
      z: 10,
      publishedStep: 1,
      publishedAt: "2026-08-14T16:05:00Z",
      formulaOrHash: "comparability_key=nrr:usd:trailing_12m",
    },
    {
      id: "gate-c109-rev",
      label: "C-109 Revenue Range",
      shortLabel: "C-109 Rev",
      sublabel: revApproved ? "Approved ($790–794m)" : "Pending ($790–794m)",
      layer: "extraction",
      x: 24,
      y: 36,
      z: -35,
      publishedStep: 1,
      publishedAt: "2026-08-14T16:05:00Z",
      formulaOrHash: "low=790000000 · high=794000000 · USD",
    },
    {
      id: "gate-c109-gm",
      label: "C-109 Gross Margin",
      shortLabel: "C-109 GM",
      sublabel: gmApproved ? "Approved (76.0–76.5%)" : "Pending (76.0–76.5%)",
      layer: "extraction",
      x: 145,
      y: 36,
      z: 30,
      publishedStep: 1,
      publishedAt: "2026-08-14T16:05:00Z",
      formulaOrHash: "low=0.760 · high=0.765 · ratio",
    },
    {
      id: "calc-driver-arr",
      label: "OperationalDriver · ARR",
      shortLabel: "ARR Driver",
      sublabel: "Retention + Expansion",
      layer: "calculation",
      x: -105,
      y: -44,
      z: -25,
      publishedStep: 1,
      publishedAt: "2026-08-14T16:05:00Z",
      formulaOrHash: "[arr_q2] * [nrr_authoritative]",
    },
    {
      id: "calc-jacobi-scc",
      label: "Jacobi SCC · 5 Sweeps",
      shortLabel: "Jacobi SCC",
      sublabel: "Convergence tol <= 0.01",
      layer: "calculation",
      x: 18,
      y: -44,
      z: 45,
      publishedStep: 1,
      publishedAt: "2026-08-14T16:05:00Z",
      formulaOrHash: "IterationGroup(max_iterations=100, sweeps=5)",
    },
    {
      id: "calc-scenario",
      label: `ScenarioOverride · ${scenario}`,
      shortLabel: `Scenario ${scenario}`,
      sublabel: scenarioDeltaByScenario[scenario] ?? "+0.0%",
      layer: "calculation",
      x: 142,
      y: -44,
      z: -20,
      publishedStep: 0,
      publishedAt: "2026-07-31T23:59:00Z",
      formulaOrHash: `Scenario(id="${scenario.toLowerCase()}", model="v19")`,
    },
    {
      id: "output-fy27-rev",
      label: `FY27 Revenue · ${revenueByScenario[scenario] ?? "$842.4m"}`,
      shortLabel: `FY27 ${revenueByScenario[scenario] ?? "$842.4m"}`,
      sublabel:
        applied && decisionAdmissible
          ? "Staged in this session · fixture schematic"
          : "Preview · awaiting review gates",
      layer: "output",
      x: 12,
      y: outputElevationByScenario[scenario] ?? -118,
      z: 0,
      publishedStep: 1,
      publishedAt: "2026-08-14T16:05:00Z",
      formulaOrHash: "ReportedFinancialOutputNode(unit=USD, quantum=0.01)",
    },
  ];

  const nodes: GraphNode3D[] = rawNodes.map((n) => {
    if (n.publishedStep > cutoffStep) {
      return { ...n, state: "cutoff-blocked" };
    }
    if (n.id === "gate-c104") {
      return { ...n, state: decisionAdmissible ? "verified" : "conflict" };
    }
    if (n.id === "gate-c109-rev") {
      return { ...n, state: revApproved ? "verified" : "pending" };
    }
    if (n.id === "gate-c109-gm") {
      return { ...n, state: gmApproved ? "verified" : "pending" };
    }
    if (n.id === "calc-scenario" || n.id === "calc-jacobi-scc") {
      return { ...n, state: "override" };
    }
    if (n.id === "output-fy27-rev") {
      return {
        ...n,
        state: applied && decisionAdmissible && revApproved && gmApproved ? "verified" : "pending",
      };
    }
    // Reported spans and the driver node have no admissibility rule. "Verified"
    // is reserved for the gates and the output, which set it above.
    return { ...n, state: "fixture" };
  });

  const edges: GraphEdge3D[] = [
    {
      from: "sec-10q-nrr",
      to: "gate-c104",
      active: cutoffStep >= 1 && (effectiveSource === null || effectiveSource === "sec-10q-nrr"),
      kind: decisionAdmissible && decision.sourceId === "sec-10q-nrr" ? "provenance" : "conflict",
    },
    {
      from: "call-turn-48",
      to: "gate-c104",
      active: cutoffStep >= 2 && (effectiveSource === null || effectiveSource === "call-turn-48"),
      kind: decisionAdmissible && decision.sourceId === "call-turn-48" ? "provenance" : "conflict",
    },
    {
      from: "sec-10q-guidance",
      to: "gate-c109-rev",
      active: cutoffStep >= 1,
      kind: "provenance",
    },
    {
      from: "sec-10q-guidance",
      to: "gate-c109-gm",
      active: cutoffStep >= 1,
      kind: "provenance",
    },
    {
      from: "sec-10q-actuals",
      to: "calc-driver-arr",
      active: cutoffStep >= 1,
      kind: "provenance",
    },
    {
      from: "gate-c104",
      to: "calc-driver-arr",
      active: cutoffStep >= 1 && decisionAdmissible,
      kind: "provenance",
    },
    {
      from: "gate-c109-rev",
      to: "calc-jacobi-scc",
      active: cutoffStep >= 1 && revApproved,
      kind: "iteration",
    },
    {
      from: "gate-c109-gm",
      to: "calc-jacobi-scc",
      active: cutoffStep >= 1 && gmApproved,
      kind: "iteration",
    },
    {
      from: "calc-driver-arr",
      to: "output-fy27-rev",
      active: cutoffStep >= 1,
      kind: "provenance",
    },
    {
      from: "calc-jacobi-scc",
      to: "output-fy27-rev",
      active: cutoffStep >= 1 && revApproved && gmApproved,
      kind: "iteration",
    },
    {
      from: "calc-scenario",
      to: "output-fy27-rev",
      active: cutoffStep >= 1,
      kind: "scenario",
    },
  ];

  return { nodes, edges };
}

// ---------------------------------------------------------------------------
// Label layout
//
// Node labels are HTML pills laid over the canvas. Each frame they are placed
// greedily in priority order (selected node first, then hovered/focused nodes
// and their neighbours, then the rest): every label tries a set of candidate
// positions around its node, then positions displaced further away (drawn
// with a leader line back to the node), and lower-priority labels fall back
// to their short form before they are dropped. A placed label never overlaps
// another placed label and never leaves the canvas.
// ---------------------------------------------------------------------------

export const LABEL_HEIGHT = 20;
/** Horizontal padding plus border on each side of a label pill (see .lg-label). */
const LABEL_CHROME_X = 9;
const LABEL_GAP = 3;
const EDGE_PAD = 4;
const CAPTION_HEIGHT = 14;
const LABEL_FONT_FAMILY = "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
const LABEL_FONT = `600 12px ${LABEL_FONT_FAMILY}`;
const LABEL_FONT_SELECTED = `700 12px ${LABEL_FONT_FAMILY}`;
const CAPTION_FONT = `600 10px ${LABEL_FONT_FAMILY}`;

/** Width of a label pill whose text measures `textWidth` px. */
export function labelBoxWidth(textWidth: number): number {
  return Math.ceil(textWidth) + 1 + LABEL_CHROME_X * 2;
}

export type LabelSide = "right" | "below";
export type LabelForm = "full" | "short" | "hidden";

export interface LabelAnchor {
  id: string;
  x: number;
  y: number;
  r: number;
}

export interface LabelRequest {
  anchor: LabelAnchor;
  fullWidth: number;
  shortWidth: number;
  /** 0: always full text (selected node). 1: prefer full (hovered, focused, neighbours). 2: may shrink first. */
  tier: 0 | 1 | 2;
}

export interface CaptionRequest {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface LabelPlacement {
  id: string;
  form: LabelForm;
  x: number;
  y: number;
  w: number;
  h: number;
  /** True when the label sits away from its node and needs a leader line. */
  leader: boolean;
  key: string;
}

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface Candidate {
  key: string;
  x: number;
  y: number;
  /** Touching the node: no leader line needed. */
  near: boolean;
  /** Within a few label rows of the node: a short leader line. */
  close: boolean;
}

const clampTo = (value: number, lo: number, hi: number) =>
  Math.min(Math.max(value, lo), Math.max(lo, hi));

function rectsOverlap(a: Rect, b: Rect, gap: number): boolean {
  return (
    a.x < b.x + b.w + gap && b.x < a.x + a.w + gap && a.y < b.y + b.h + gap && b.y < a.y + a.h + gap
  );
}

function rectPointDistance(rect: Rect, px: number, py: number): number {
  const dx = Math.max(rect.x - px, 0, px - (rect.x + rect.w));
  const dy = Math.max(rect.y - py, 0, py - (rect.y + rect.h));
  return Math.hypot(dx, dy);
}

function labelCandidates(
  anchor: LabelAnchor,
  w: number,
  h: number,
  side: LabelSide,
  width: number,
  height: number,
): Candidate[] {
  const { x, y, r } = anchor;
  const gap = 5;
  const step = h + LABEL_GAP + 1;
  const primary: Record<"right" | "below" | "above" | "left", [number, number]> = {
    right: [x + r + gap, y - h / 2],
    below: [x - w / 2, y + r + gap],
    above: [x - w / 2, y - r - gap - h],
    left: [x - r - gap - w, y - h / 2],
  };
  const order =
    side === "right"
      ? (["right", "below", "above", "left"] as const)
      : (["below", "above", "right", "left"] as const);
  const raw: [string, number, number][] = order.map((key) => [key, ...primary[key]]);
  for (let k = 1; k <= 2; k += 1) {
    for (const key of order) {
      if (key !== "right" && key !== "left") continue;
      const [px, py] = primary[key];
      raw.push([`${key}+${k}`, px, py + k * step], [`${key}-${k}`, px, py - k * step]);
    }
  }
  for (let k = 1; k <= 10; k += 1) {
    raw.push(
      [`below+${k}`, primary.below[0], primary.below[1] + k * step],
      [`above+${k}`, primary.above[0], primary.above[1] - k * step],
    );
  }
  const seen = new Set<string>();
  const out: Candidate[] = [];
  for (const [key, rx, ry] of raw) {
    const cx = clampTo(rx, EDGE_PAD, width - EDGE_PAD - w);
    const cy = clampTo(ry, EDGE_PAD, height - EDGE_PAD - h);
    const signature = `${Math.round(cx)}:${Math.round(cy)}`;
    if (seen.has(signature)) continue;
    seen.add(signature);
    const distance = rectPointDistance({ x: cx, y: cy, w, h }, x, y) - r;
    out.push({ key, x: cx, y: cy, near: distance <= gap + 2, close: distance <= 3 * step });
  }
  return out;
}

/**
 * Greedy label placement. `requests` must be in priority order; the first
 * tier-0 request always gets its full label.
 */
export function placeLabels(options: {
  width: number;
  height: number;
  side: LabelSide;
  requests: readonly LabelRequest[];
  obstacles: readonly LabelAnchor[];
  captions?: readonly CaptionRequest[];
  previous?: ReadonlyMap<string, LabelPlacement>;
}): LabelPlacement[] {
  const { width, height, side, requests, obstacles, captions = [], previous } = options;
  const placed: Rect[] = [];
  const result: LabelPlacement[] = [];
  const hitsNode = (rect: Rect) =>
    obstacles.some((node) => rectPointDistance(rect, node.x, node.y) < node.r + 2);

  type Form = "full" | "short";
  interface Attempt {
    form: Form;
    candidate: Candidate;
    strict: boolean;
  }

  for (const request of requests) {
    const { anchor } = request;
    const widthOf = (form: Form) => (form === "full" ? request.fullWidth : request.shortWidth);
    const candidates: Record<Form, Candidate[]> = {
      full: labelCandidates(anchor, request.fullWidth, LABEL_HEIGHT, side, width, height),
      short: labelCandidates(anchor, request.shortWidth, LABEL_HEIGHT, side, width, height),
    };
    const attempts: Attempt[] = [];
    const add = (form: Form, strict: boolean, filter?: (c: Candidate) => boolean) => {
      for (const candidate of candidates[form]) {
        if (!filter || filter(candidate)) attempts.push({ form, candidate, strict });
      }
    };
    const near = (c: Candidate) => c.near;
    const close = (c: Candidate) => c.close && !c.near;
    const far = (c: Candidate) => !c.close;
    const nearOrClose = (c: Candidate) => c.close;
    if (request.tier === 0) {
      add("full", true);
      add("full", false);
    } else if (request.tier === 1) {
      // A full label a long leader line away reads worse than a short one nearby.
      add("full", true, nearOrClose);
      add("short", true, nearOrClose);
      add("full", true, far);
      add("short", true, far);
      add("full", false);
      add("short", false);
    } else {
      add("full", true, near);
      add("short", true, near);
      add("full", true, close);
      add("short", true, close);
      add("full", true, far);
      add("short", true, far);
      add("full", false);
      add("short", false);
    }
    const rectOf = (a: Attempt): Rect => ({
      x: a.candidate.x,
      y: a.candidate.y,
      w: widthOf(a.form),
      h: LABEL_HEIGHT,
    });
    const fits = (a: Attempt) => {
      const rect = rectOf(a);
      return (
        !placed.some((other) => rectsOverlap(rect, other, LABEL_GAP)) &&
        (!a.strict || !hitsNode(rect))
      );
    };

    let chosen = attempts.find(fits);
    // Keep last frame's spot while it is still as good, so orbiting labels
    // do not flicker between equally valid positions.
    const prev = previous?.get(anchor.id);
    if (chosen && prev && prev.form === chosen.form && prev.key !== chosen.candidate.key) {
      const best = chosen;
      chosen =
        attempts.find(
          (a) =>
            a.form === best.form &&
            a.strict === best.strict &&
            a.candidate.key === prev.key &&
            fits(a),
        ) ?? best;
    }
    if (!chosen) {
      result.push({
        id: anchor.id,
        form: "hidden",
        x: 0,
        y: 0,
        w: 0,
        h: 0,
        leader: false,
        key: "",
      });
      continue;
    }
    const rect = rectOf(chosen);
    placed.push(rect);
    result.push({
      id: anchor.id,
      form: chosen.form,
      ...rect,
      leader: !chosen.candidate.near,
      key: chosen.candidate.key,
    });
  }

  for (const caption of captions) {
    const rect: Rect = {
      x: clampTo(caption.x, EDGE_PAD, width - EDGE_PAD - caption.w),
      y: clampTo(caption.y, EDGE_PAD, height - EDGE_PAD - caption.h),
      w: caption.w,
      h: caption.h,
    };
    const fitsCaption =
      !placed.some((other) => rectsOverlap(rect, other, LABEL_GAP)) && !hitsNode(rect);
    if (fitsCaption) placed.push(rect);
    result.push({
      id: caption.id,
      form: fitsCaption ? "full" : "hidden",
      ...rect,
      leader: false,
      key: "caption",
    });
  }
  return result;
}

// ---------------------------------------------------------------------------
// Scene geometry
// ---------------------------------------------------------------------------

/** Layers from the top of the canvas to the bottom. */
const DAG_ROWS: readonly ProvenanceLayer[] = ["output", "calculation", "extraction", "reported"];

/** Column of each node within its layer row, ordered to keep edges from crossing. */
const DAG_COLUMN: Readonly<Record<string, number>> = {
  "output-fy27-rev": 0.4,
  "calc-driver-arr": 0,
  "calc-jacobi-scc": 0.45,
  "calc-scenario": 0.75,
  "gate-c104": 0.3,
  "gate-c109-rev": 0.56,
  "gate-c109-gm": 0.8,
  "sec-10q-actuals": 0,
  "sec-10q-nrr": 0.25,
  "call-turn-48": 0.5,
  "sec-10q-guidance": 0.75,
};

const LAYER_CAPTIONS: Readonly<Record<ProvenanceLayer, string>> = {
  output: "L3 · REPORTED OUTPUT",
  calculation: "L2 · DECIMAL CALC DAG",
  extraction: "L1 · EXTRACTION & REVIEW",
  reported: "L0 · SOURCE SPANS",
};

const LAYER_PLANE_Y: Readonly<Record<ProvenanceLayer, number>> = {
  output: -118,
  calculation: -44,
  extraction: 36,
  reported: 112,
};

/** Below this canvas width the DAG puts labels under nodes instead of beside them. */
export const WIDE_DAG_MIN_WIDTH = 560;

/** Canvas CSS height for a given CSS width. */
export function canvasHeightFor(width: number): number {
  return Math.round(Math.min(520, Math.max(400, width * 0.58)));
}

/** Flat layered layout used by the "Layered DAG" preset. */
export function dagLayout(
  nodes: readonly Pick<GraphNode3D, "id" | "layer">[],
  width: number,
  height: number,
): {
  side: LabelSide;
  bandTop: (row: number) => number;
  positions: Map<string, { x: number; y: number }>;
} {
  const side: LabelSide = width >= WIDE_DAG_MIN_WIDTH ? "right" : "below";
  const margin = 6;
  const band = (height - margin * 2) / DAG_ROWS.length;
  const bandTop = (row: number) => margin + band * row;
  const positions = new Map<string, { x: number; y: number }>();
  for (const node of nodes) {
    const row = Math.max(0, DAG_ROWS.indexOf(node.layer));
    const column = DAG_COLUMN[node.id] ?? 0.5;
    positions.set(node.id, {
      x: side === "right" ? 28 + column * (width - 56) : width * (0.12 + column * 0.95),
      y: bandTop(row) + band * (side === "right" ? 0.6 : 0.45),
    });
  }
  return { side, bandTop, positions };
}

function bezierPoint(a: number, b: number, c: number, d: number, t: number): number {
  const u = 1 - t;
  return u * u * u * a + 3 * u * u * t * b + 3 * u * t * t * c + t * t * t * d;
}

interface HitTarget {
  id: string;
  sx: number;
  sy: number;
  r: number;
  depth: number;
}

export function EvidenceGraph3D({
  scenario,
  source,
  decision,
  approvals,
  applied,
  onSelectNode,
}: EvidenceGraph3DProps) {
  const cutoffInputId = useId();
  const [preset, setPreset] = useState<CameraPreset>("dag");
  const [cutoffStep, setCutoffStep] = useState<0 | 1 | 2>(2);
  const [selectedId, setSelectedId] = useState<string>("output-fy27-rev");
  const [autoOrbit, setAutoOrbit] = useState<boolean>(false);
  const [angles, setAngles] = useState<{ yaw: number; pitch: number }>(() => presetAngles("dag"));

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const pulsePhaseRef = useRef<number>(0);
  const orbitYawOffsetRef = useRef<number>(0);
  const dragRef = useRef<{ active: boolean; moved: boolean; lastX: number; lastY: number }>({
    active: false,
    moved: false,
    lastX: 0,
    lastY: 0,
  });
  const projectedRef = useRef<HitTarget[]>([]);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const labelElsRef = useRef<Map<string, HTMLElement>>(new Map());
  const placementsRef = useRef<Map<string, LabelPlacement>>(new Map());
  const pointerRef = useRef<{ hover: string | null; focus: string | null }>({
    hover: null,
    focus: null,
  });
  const repaintRef = useRef<() => void>(() => undefined);
  const sizeRef = useRef<{ width: number; height: number }>({ width: 680, height: 400 });

  const { nodes, edges } = useMemo(
    () =>
      buildEpistemicGraph({
        scenario,
        source,
        decision,
        approvals,
        applied,
        cutoffStep,
      }),
    [scenario, source, decision, approvals, applied, cutoffStep],
  );

  const selectedNode = useMemo(
    () => nodes.find((n) => n.id === selectedId) ?? nodes[nodes.length - 1]!,
    [nodes, selectedId],
  );
  const selectedNodeId = selectedNode.id;
  const orbiting = autoOrbit && preset === "constellation";

  const cutoffInfo = CUTOFF_STOPS[cutoffStep] ?? CUTOFF_STOPS[2]!;
  const blockedCount = nodes.filter((n) => n.state === "cutoff-blocked").length;
  const verifiedCount = nodes.filter((n) => n.state === "verified").length;
  const conflictGateState = nodes.find((n) => n.id === "gate-c104")!.state;
  const outputState = nodes.find((n) => n.id === "output-fy27-rev")!.state;
  const lineageState =
    conflictGateState === "cutoff-blocked" ||
    (decision !== null && conflictGateState !== "verified")
      ? "Review gates blocked by cutoff"
      : outputState === "verified"
        ? "All gates unlocked"
        : conflictGateState === "verified"
          ? "NRR resolved · awaiting guidance"
          : "C-104 conflict active";

  const choosePreset = (next: CameraPreset) => {
    setPreset(next);
    // Orbit only ever runs after the user turns it on in the 3D Orbit view.
    setAutoOrbit(false);
    orbitYawOffsetRef.current = 0;
    setAngles(presetAngles(next));
  };

  const selectNode = (id: string) => {
    setSelectedId(id);
    onSelectNode?.(id);
  };

  const setPointerTarget = (kind: "hover" | "focus", id: string | null) => {
    if (pointerRef.current[kind] === id) return;
    pointerRef.current[kind] = id;
    repaintRef.current();
  };

  const registerLabel = (id: string) => (el: HTMLElement | null) => {
    if (el) labelElsRef.current.set(id, el);
    else labelElsRef.current.delete(id);
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let frameId = 0;
    const reducedMotion =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const flat = preset === "dag";
    const spinning = autoOrbit && preset === "constellation";

    const neighbours = new Map<string, Set<string>>();
    const link = (a: string, b: string) => {
      const set = neighbours.get(a) ?? new Set<string>();
      set.add(b);
      neighbours.set(a, set);
    };
    edges.forEach((edge) => {
      link(edge.from, edge.to);
      link(edge.to, edge.from);
    });

    const textWidths = new Map<string, number>();
    const measure = (text: string, font: string) => {
      const key = `${font}|${text}`;
      let w = textWidths.get(key);
      if (w === undefined) {
        ctx.font = font;
        w = ctx.measureText(text).width;
        textWidths.set(key, w);
      }
      return w;
    };
    const written = new WeakMap<HTMLElement, string>();

    const syncSize = () => {
      const cssWidth = wrapRef.current?.clientWidth ?? 0;
      if (cssWidth > 0) {
        const width = Math.round(cssWidth);
        const height = canvasHeightFor(width);
        const dpr = Math.min(2, Math.max(1, window.devicePixelRatio || 1));
        const backingWidth = Math.round(width * dpr);
        const backingHeight = Math.round(height * dpr);
        if (canvas.width !== backingWidth) canvas.width = backingWidth;
        if (canvas.height !== backingHeight) canvas.height = backingHeight;
        const cssHeight = `${height}px`;
        if (canvas.style.height !== cssHeight) canvas.style.height = cssHeight;
        return { width, height, dpr };
      }
      return { width: canvas.width, height: canvas.height, dpr: 1 };
    };

    const renderFrame = () => {
      const { width, height, dpr } = syncSize();
      sizeRef.current = { width, height };
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      // Deep space / epistemic grid background
      const grad = ctx.createLinearGradient(0, 0, 0, height);
      grad.addColorStop(0, "#080e1a");
      grad.addColorStop(1, "#0f192c");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, width, height);

      const captionWidth = (text: string) => Math.ceil(measure(text, CAPTION_FONT)) + 2;
      const captions: CaptionRequest[] = [];
      const positions = new Map<string, HitTarget>();
      let side: LabelSide = "below";

      ctx.save();
      ctx.strokeStyle = "rgba(88, 166, 255, 0.13)";
      ctx.lineWidth = 1;
      if (flat) {
        const layout = dagLayout(nodes, width, height);
        side = layout.side;
        DAG_ROWS.forEach((layer, row) => {
          const top = layout.bandTop(row);
          if (row > 0) {
            ctx.beginPath();
            ctx.moveTo(8, top);
            ctx.lineTo(width - 8, top);
            ctx.stroke();
          }
          captions.push({
            id: `layer-${layer}`,
            x: 10,
            y: top + 5,
            w: captionWidth(LAYER_CAPTIONS[layer]),
            h: CAPTION_HEIGHT,
          });
        });
        nodes.forEach((node) => {
          const p = layout.positions.get(node.id)!;
          positions.set(node.id, {
            id: node.id,
            sx: p.x,
            sy: p.y,
            r: node.layer === "output" ? 14 : 10,
            depth: 0,
          });
        });
      } else {
        const yaw = angles.yaw + orbitYawOffsetRef.current;
        const pitch = angles.pitch;
        const cosY = Math.cos(yaw);
        const sinY = Math.sin(yaw);
        const cosP = Math.cos(pitch);
        const sinP = Math.sin(pitch);
        // Tuned on a 520x400 canvas so every node stays in frame at each preset
        // pitch for any orbit yaw (labels are placed separately and clamped),
        // then scaled uniformly to the real canvas. The scene sits low (near
        // L0 spans grow under positive pitch), so the projection center is
        // above the canvas midline. Narrow canvases have spare height, so the
        // layers are spread apart a little to give labels room by their nodes.
        const fit = Math.min(width / 520, height / 400);
        const fitY = Math.min(height / 400, fit * 1.6);
        const fov = 320;
        const viewerDist = 420;
        const centerY = height / 2 - 32 * fitY;
        const project = (x: number, y: number, z: number) => {
          const rx = x * cosY - z * sinY;
          const rz = x * sinY + z * cosY;
          const ry = y * cosP - rz * sinP;
          const rz2 = y * sinP + rz * cosP;
          const scale = fov / Math.max(120, viewerDist + rz2);
          return {
            sx: width / 2 + rx * scale * fit,
            sy: centerY + ry * scale * fitY,
            scale,
            depth: rz2,
          };
        };
        DAG_ROWS.forEach((layer) => {
          const ly = LAYER_PLANE_Y[layer];
          const corners = [
            project(-210, ly, -95),
            project(210, ly, -95),
            project(210, ly, 95),
            project(-210, ly, 95),
          ];
          ctx.beginPath();
          ctx.moveTo(corners[0]!.sx, corners[0]!.sy);
          corners.slice(1).forEach((c) => ctx.lineTo(c.sx, c.sy));
          ctx.closePath();
          ctx.stroke();
          captions.push({
            id: `layer-${layer}`,
            x: corners[0]!.sx + 6,
            y: corners[0]!.sy - 4 - CAPTION_HEIGHT,
            w: captionWidth(LAYER_CAPTIONS[layer]),
            h: CAPTION_HEIGHT,
          });
        });
        const radiusScale = Math.min(1.25, Math.max(0.75, fit));
        nodes.forEach((node) => {
          const p = project(node.x, node.y, node.z);
          positions.set(node.id, {
            id: node.id,
            sx: p.sx,
            sy: p.sy,
            r: Math.max(8, (node.layer === "output" ? 16 : 12) * p.scale * radiusScale),
            depth: p.depth,
          });
        });
      }
      ctx.restore();

      // Label layout, in priority order.
      const { hover, focus } = pointerRef.current;
      const near = (a: string | null, b: string) =>
        a !== null && neighbours.get(a)?.has(b) === true;
      const rank = (id: string) =>
        id === selectedNodeId
          ? 0
          : id === hover
            ? 1
            : id === focus
              ? 2
              : near(selectedNodeId, id)
                ? 3
                : near(hover, id) || near(focus, id)
                  ? 4
                  : 5;
      const ordered = [...nodes].sort(
        (a, b) =>
          rank(a.id) - rank(b.id) ||
          positions.get(a.id)!.depth - positions.get(b.id)!.depth ||
          DAG_ROWS.indexOf(a.layer) - DAG_ROWS.indexOf(b.layer),
      );
      const requests: LabelRequest[] = ordered.map((node) => {
        const p = positions.get(node.id)!;
        const font = node.id === selectedNodeId ? LABEL_FONT_SELECTED : LABEL_FONT;
        const r = rank(node.id);
        return {
          anchor: { id: node.id, x: p.sx, y: p.sy, r: p.r },
          fullWidth: labelBoxWidth(measure(node.label, font)),
          shortWidth: labelBoxWidth(measure(node.shortLabel, font)),
          tier: r === 0 ? 0 : r < 5 ? 1 : 2,
        };
      });
      const placements = placeLabels({
        width,
        height,
        side,
        requests,
        obstacles: requests.map((req) => req.anchor),
        captions,
        previous: placementsRef.current,
      });
      placementsRef.current = new Map(placements.map((p) => [p.id, p]));

      // Draw edges and animated provenance pulses
      edges.forEach((edge) => {
        const from = positions.get(edge.from);
        const to = positions.get(edge.to);
        if (!from || !to) return;

        const style = edgePalette(edge.kind);
        const midY = (from.sy + to.sy) / 2;
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(from.sx, from.sy);
        if (flat) ctx.bezierCurveTo(from.sx, midY, to.sx, midY, to.sx, to.sy);
        else ctx.lineTo(to.sx, to.sy);
        if (!edge.active) {
          ctx.strokeStyle = "rgba(139, 148, 158, 0.24)";
          ctx.setLineDash([4, 4]);
          ctx.lineWidth = 1.2;
        } else {
          ctx.strokeStyle = style.stroke;
          ctx.lineWidth = style.width;
        }
        ctx.stroke();

        // Animated energy pulse along active edges
        if (edge.active) {
          const t = (pulsePhaseRef.current * 0.9) % 1;
          const px = flat
            ? bezierPoint(from.sx, from.sx, to.sx, to.sx, t)
            : from.sx + (to.sx - from.sx) * t;
          const py = flat
            ? bezierPoint(from.sy, midY, midY, to.sy, t)
            : from.sy + (to.sy - from.sy) * t;
          ctx.beginPath();
          ctx.arc(px, py, 3.4, 0, Math.PI * 2);
          ctx.fillStyle = style.pulse;
          ctx.fill();
        }
        ctx.restore();
      });

      // Leader lines from displaced labels back to their nodes
      ctx.save();
      ctx.strokeStyle = "rgba(201, 209, 217, 0.7)";
      ctx.lineWidth = 1;
      placements.forEach((p) => {
        const node = positions.get(p.id);
        if (!node || !p.leader || p.form === "hidden") return;
        const tx = clampTo(node.sx, p.x, p.x + p.w);
        const ty = clampTo(node.sy, p.y, p.y + p.h);
        const angle = Math.atan2(ty - node.sy, tx - node.sx);
        ctx.beginPath();
        ctx.moveTo(
          node.sx + Math.cos(angle) * (node.r + 2),
          node.sy + Math.sin(angle) * (node.r + 2),
        );
        ctx.lineTo(tx, ty);
        ctx.stroke();
      });
      ctx.restore();

      // Sort nodes back-to-front (Painter's algorithm)
      const sorted = [...nodes].sort(
        (a, b) => positions.get(b.id)!.depth - positions.get(a.id)!.depth,
      );
      const hitList: HitTarget[] = [];
      sorted.forEach((node) => {
        const { sx, sy, r: radius, depth } = positions.get(node.id)!;
        const palette = nodeColor(node.state);
        const isSelected = node.id === selectedNodeId;
        hitList.push({ id: node.id, sx, sy, r: radius + 6, depth });

        ctx.save();
        if (isSelected || node.state === "conflict" || node.state === "cutoff-blocked") {
          ctx.beginPath();
          ctx.arc(sx, sy, radius + (isSelected ? 6 : 4), 0, Math.PI * 2);
          ctx.strokeStyle = palette.ring;
          ctx.lineWidth = isSelected ? 2.5 : 1.4;
          ctx.stroke();
        }

        const sphereGrad = ctx.createRadialGradient(
          sx - radius * 0.3,
          sy - radius * 0.3,
          radius * 0.15,
          sx,
          sy,
          radius,
        );
        sphereGrad.addColorStop(0, palette.ring);
        sphereGrad.addColorStop(1, palette.fill);

        ctx.beginPath();
        ctx.arc(sx, sy, radius, 0, Math.PI * 2);
        ctx.fillStyle = sphereGrad;
        ctx.fill();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = "#0b1220";
        ctx.stroke();
        ctx.restore();
      });
      projectedRef.current = hitList;

      // Move the HTML label pills; only touch the DOM when something changed.
      placements.forEach((p) => {
        const el = labelElsRef.current.get(p.id);
        if (!el) return;
        const x = Math.round(p.x);
        const y = Math.round(p.y);
        const signature = p.form === "hidden" ? "hidden" : `${p.form}|${x}|${y}|${p.w}`;
        if (written.get(el) === signature) return;
        written.set(el, signature);
        el.dataset.form = p.form;
        if (p.form !== "hidden") {
          el.style.transform = `translate(${x}px, ${y}px)`;
          el.style.width = `${p.w}px`;
        }
      });

      if (!reducedMotion) {
        pulsePhaseRef.current += 0.016;
        if (spinning && !dragRef.current.active) {
          orbitYawOffsetRef.current += 0.0028;
        }
        frameId = window.requestAnimationFrame(renderFrame);
      }
    };

    // With reduced motion there is no animation loop, so repaint on demand.
    repaintRef.current = () => {
      if (reducedMotion) renderFrame();
    };
    const wrap = wrapRef.current;
    const resizeObserver =
      wrap && typeof ResizeObserver === "function"
        ? new ResizeObserver(() => repaintRef.current())
        : null;
    if (wrap) resizeObserver?.observe(wrap);

    renderFrame();
    return () => {
      if (frameId) window.cancelAnimationFrame(frameId);
      resizeObserver?.disconnect();
      repaintRef.current = () => undefined;
    };
  }, [nodes, edges, angles, autoOrbit, preset, selectedNodeId]);

  const toCanvasPoint = (event: { clientX: number; clientY: number }) => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const { width, height } = sizeRef.current;
    return {
      x: (event.clientX - rect.left) * (width / Math.max(1, rect.width)),
      y: (event.clientY - rect.top) * (height / Math.max(1, rect.height)),
    };
  };

  const hitTest = (x: number, y: number): string | null => {
    for (const p of placementsRef.current.values()) {
      if (p.form === "hidden" || p.key === "caption") continue;
      if (x >= p.x && x <= p.x + p.w && y >= p.y && y <= p.y + p.h) return p.id;
    }
    const hits = projectedRef.current
      .filter((item) => Math.hypot(item.sx - x, item.sy - y) <= item.r)
      .sort((a, b) => a.depth - b.depth);
    return hits[0]?.id ?? null;
  };

  const handleCanvasClick = (event: React.MouseEvent<HTMLCanvasElement>) => {
    if (dragRef.current.moved) {
      dragRef.current.moved = false;
      return;
    }
    const point = toCanvasPoint(event);
    if (!point) return;
    const hit = hitTest(point.x, point.y);
    if (hit) selectNode(hit);
  };

  const updateHover = (event: { clientX: number; clientY: number }) => {
    const point = toCanvasPoint(event);
    const hit = point ? hitTest(point.x, point.y) : null;
    setPointerTarget("hover", hit);
    const canvas = canvasRef.current;
    if (canvas?.style) canvas.style.cursor = hit ? "pointer" : "";
  };

  return (
    <section
      className="viz3d-card"
      data-testid="evidence-graph-3d"
      aria-label="3D Evidence and Calculation Lineage Constellation"
    >
      <div className="viz3d-header">
        <div>
          <p className="eyebrow">Illustrative fixture schematic · 4-Layer Provenance DAG</p>
          <h3>3D Evidence &amp; Calculation Lineage Explorer</h3>
        </div>
        <div className="viz3d-controls" role="group" aria-label="3D camera presets">
          {(
            [
              ["constellation", "3D Orbit"],
              ["dag", "Layered DAG"],
              ["temporal", "Cutoff Slice"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              data-testid={`button-viz3d-preset-${id}`}
              aria-pressed={preset === id}
              onClick={() => choosePreset(id)}
            >
              {label}
            </button>
          ))}
          <button
            type="button"
            data-testid="button-viz3d-orbit"
            aria-pressed={orbiting}
            disabled={preset !== "constellation"}
            title={preset === "constellation" ? undefined : "Orbit runs in the 3D Orbit view"}
            onClick={() => setAutoOrbit((prev) => !prev)}
          >
            {orbiting ? "Pause Orbit" : "Auto Orbit"}
          </button>
        </div>
      </div>

      <div className="viz3d-hud-bar" role="status" aria-live="polite">
        <span>
          <b>Verified nodes:</b> {verifiedCount} / {nodes.length}
        </span>
        <span>
          <b>Cutoff blocked:</b> {blockedCount}
        </span>
        <span>
          <b>Active scenario:</b> {scenario}
        </span>
        <span>
          <b>Lineage state:</b> {lineageState}
        </span>
      </div>

      <div className="viz3d-canvas-wrap" ref={wrapRef}>
        <canvas
          ref={canvasRef}
          width={680}
          height={400}
          role="img"
          className={preset === "dag" ? "viz3d-canvas viz3d-canvas--flat" : "viz3d-canvas"}
          data-testid="canvas-evidence-3d"
          onClick={handleCanvasClick}
          onPointerDown={(e) => {
            dragRef.current = { active: true, moved: false, lastX: e.clientX, lastY: e.clientY };
          }}
          onPointerMove={(e) => {
            // The flat DAG has no camera to rotate; there the pointer only hovers.
            if (!dragRef.current.active || preset === "dag") {
              updateHover(e);
              return;
            }
            const dx = e.clientX - dragRef.current.lastX;
            const dy = e.clientY - dragRef.current.lastY;
            const moved = dragRef.current.moved || Math.hypot(dx, dy) > 4;
            dragRef.current = { active: true, moved, lastX: e.clientX, lastY: e.clientY };
            setAngles((prev) => ({
              yaw: prev.yaw + dx * 0.01,
              pitch: Math.max(-0.85, Math.min(0.85, prev.pitch + dy * 0.01)),
            }));
          }}
          onPointerUp={() => {
            dragRef.current.active = false;
          }}
          onPointerLeave={() => {
            dragRef.current.active = false;
            setPointerTarget("hover", null);
          }}
          aria-label="Interactive 3D canvas of filing spans, review gates, calculation nodes, and FY27 revenue output"
        />
        <div className="lg-labels" aria-hidden="true">
          {DAG_ROWS.map((layer) => (
            <span
              key={layer}
              ref={registerLabel(`layer-${layer}`)}
              className="lg-caption"
              data-lineage-label={`layer-${layer}`}
            >
              {LAYER_CAPTIONS[layer]}
            </span>
          ))}
          {nodes.map((node) => (
            <span
              key={node.id}
              ref={registerLabel(node.id)}
              className="lg-label"
              data-lineage-label={node.id}
              data-state={node.state}
              data-selected={node.id === selectedNodeId ? "" : undefined}
            >
              <span className="lg-label-full">{node.label}</span>
              <span className="lg-label-short">{node.shortLabel}</span>
            </span>
          ))}
        </div>
      </div>

      <div className="viz3d-scrubber">
        <label htmlFor={cutoffInputId}>
          <span>
            Point-in-time cutoff (<code>published_at &lt;= effective_as_of</code>):{" "}
            <strong data-testid="text-viz3d-cutoff-label">{cutoffInfo.label}</strong>
          </span>
          <small>{cutoffInfo.description}</small>
        </label>
        <input
          id={cutoffInputId}
          data-testid="input-viz3d-cutoff"
          type="range"
          min={0}
          max={2}
          step={1}
          value={cutoffStep}
          onChange={(e) => setCutoffStep(Number(e.target.value) as 0 | 1 | 2)}
        />
      </div>

      <div className="viz3d-node-pills" role="group" aria-label="Inspect provenance node">
        {nodes.map((node) => {
          const palette = nodeColor(node.state);
          return (
            <button
              key={node.id}
              type="button"
              data-testid={`button-viz3d-node-${node.id}`}
              className="viz3d-pill"
              aria-pressed={selectedNode.id === node.id}
              onClick={() => selectNode(node.id)}
              onFocus={() => setPointerTarget("focus", node.id)}
              onBlur={() => setPointerTarget("focus", null)}
              onMouseEnter={() => setPointerTarget("hover", node.id)}
              onMouseLeave={() => setPointerTarget("hover", null)}
            >
              <span
                className="viz3d-dot"
                style={{ backgroundColor: palette.ring }}
                aria-hidden="true"
              />
              {node.label}
            </button>
          );
        })}
      </div>

      <aside
        className="viz3d-inspector"
        data-testid="viz3d-node-inspector"
        aria-label="Selected 3D node provenance details"
      >
        <div>
          <small>{layerTitle(selectedNode.layer)}</small>
          <h4 data-testid="text-viz3d-selected-title">{selectedNode.label}</h4>
          <p>{selectedNode.sublabel}</p>
        </div>
        <dl className="viz3d-meta">
          <div>
            <dt>Status</dt>
            <dd data-testid="text-viz3d-selected-status">{nodeColor(selectedNode.state).badge}</dd>
          </div>
          <div>
            <dt>Published at</dt>
            <dd>
              <code>{selectedNode.publishedAt}</code>
            </dd>
          </div>
          <div>
            <dt>Formula / Hash</dt>
            <dd>
              <code>{selectedNode.formulaOrHash}</code>
            </dd>
          </div>
        </dl>
      </aside>
    </section>
  );
}
