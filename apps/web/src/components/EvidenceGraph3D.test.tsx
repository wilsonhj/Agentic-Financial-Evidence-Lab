import { readFileSync } from "node:fs";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { findAll, findOne } from "../lib/test-support/shallow-tree";

const hooks = vi.hoisted(() => ({
  index: 0,
  values: [] as unknown[],
  effects: [] as (() => (() => void) | void)[],
}));

vi.mock("react", async (load) => ({
  ...(await load<typeof import("react")>()),
  useId() {
    return "test-cutoff-id";
  },
  useMemo(factory: () => unknown) {
    return factory();
  },
  useState(initial: unknown) {
    const i = hooks.index++;
    if (!Object.hasOwn(hooks.values, i))
      hooks.values[i] = typeof initial === "function" ? initial() : initial;
    return [
      hooks.values[i],
      (next: unknown) => {
        hooks.values[i] = typeof next === "function" ? next(hooks.values[i]) : next;
      },
    ];
  },
  useRef(initial: unknown) {
    const i = hooks.index++;
    return (hooks.values[i] ??= { current: initial });
  },
  useEffect(effect: () => (() => void) | void) {
    hooks.effects.push(effect);
  },
}));

import {
  buildEpistemicGraph,
  canvasHeightFor,
  dagLayout,
  EvidenceGraph3D,
  LABEL_HEIGHT,
  labelBoxWidth,
  placeLabels,
  WIDE_DAG_MIN_WIDTH,
} from "./EvidenceGraph3D";
import type { GuidanceApproval, ReviewDecision } from "../app/desk/desk-state";

const PENDING_APPROVALS: GuidanceApproval[] = [
  { claimId: "C-109-revenue", approved: false },
  { claimId: "C-109-gross-margin", approved: false },
];

const COMPLETED_APPROVALS: GuidanceApproval[] = [
  { claimId: "C-109-revenue", approved: true },
  { claimId: "C-109-gross-margin", approved: true },
];

const DECISION_10Q: ReviewDecision = {
  conflictId: "C-104",
  sourceId: "sec-10q-nrr",
  rationale: "Filed 10-Q disclosure is the authoritative modeled metric.",
};

const DECISION_CALL: ReviewDecision = {
  conflictId: "C-104",
  sourceId: "call-turn-48",
  rationale: "Earnings call transcript turn 48 reflects updated point-in-time NRR.",
};

const props = (node: ReactElement) => node.props as Record<string, unknown>;

beforeEach(() => {
  hooks.index = 0;
  hooks.values = [];
  hooks.effects = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("buildEpistemicGraph", () => {
  it("marks C-104 as conflict before decision and verified once resolved", () => {
    const unresolved = buildEpistemicGraph({
      scenario: "Base",
      source: null,
      decision: null,
      approvals: PENDING_APPROVALS,
      applied: false,
      cutoffStep: 2,
    });
    const gateBefore = unresolved.nodes.find((n) => n.id === "gate-c104");
    expect(gateBefore?.state).toBe("conflict");

    const resolved = buildEpistemicGraph({
      scenario: "Bull",
      source: "sec-10q-nrr",
      decision: DECISION_10Q,
      approvals: COMPLETED_APPROVALS,
      applied: true,
      cutoffStep: 2,
    });
    const gateAfter = resolved.nodes.find((n) => n.id === "gate-c104");
    expect(gateAfter?.state).toBe("verified");
    const output = resolved.nodes.find((n) => n.id === "output-fy27-rev");
    expect(output?.label).toContain("$857.1m");
    expect(output?.state).toBe("verified");
  });

  it("enforces point-in-time cutoff by blocking future-published nodes and decisions", () => {
    const atFiling = buildEpistemicGraph({
      scenario: "Bear",
      source: "call-turn-48",
      decision: DECISION_CALL,
      approvals: COMPLETED_APPROVALS,
      applied: true,
      cutoffStep: 1,
    });
    const callNode = atFiling.nodes.find((n) => n.id === "call-turn-48");
    const filingNode = atFiling.nodes.find((n) => n.id === "sec-10q-nrr");
    const gateNode = atFiling.nodes.find((n) => n.id === "gate-c104");
    const outputNode = atFiling.nodes.find((n) => n.id === "output-fy27-rev");
    expect(callNode?.state).toBe("cutoff-blocked");
    expect(filingNode?.state).toBe("fixture");
    expect(gateNode?.state).toBe("conflict");
    expect(outputNode?.state).toBe("pending");
    const gateToArrEdge = atFiling.edges.find(
      (e) => e.from === "gate-c104" && e.to === "calc-driver-arr",
    );
    expect(gateToArrEdge?.active).toBe(false);

    const preClose = buildEpistemicGraph({
      scenario: "Base",
      source: null,
      decision: null,
      approvals: PENDING_APPROVALS,
      applied: false,
      cutoffStep: 0,
    });
    expect(preClose.nodes.find((n) => n.id === "sec-10q-nrr")?.state).toBe("cutoff-blocked");
    expect(preClose.nodes.find((n) => n.id === "calc-scenario")?.state).toBe("override");
    expect(
      preClose.edges.find((e) => e.from === "calc-scenario" && e.to === "output-fy27-rev")?.active,
    ).toBe(false);
  });
});

describe("fixture copy is not presented as evidence", () => {
  it("carries no made-up hashes and never says verified lineage", () => {
    for (const applied of [false, true]) {
      for (const decision of [null, DECISION_10Q, DECISION_CALL]) {
        const { nodes } = buildEpistemicGraph({
          scenario: "Base",
          source: decision?.sourceId ?? null,
          decision,
          approvals: COMPLETED_APPROVALS,
          applied,
          cutoffStep: 2,
        });
        for (const node of nodes) {
          const copy = `${node.sublabel} ${node.formulaOrHash}`;
          expect(copy, node.id).not.toMatch(/sha256/i);
          expect(copy, node.id).not.toMatch(/verified lineage/i);
          if (node.layer === "reported" || node.id === "calc-driver-arr") {
            expect(node.state, node.id).not.toBe("verified");
          }
        }
      }
    }
  });

  it("labels the applied, admissible view a fixture schematic in the inspector", () => {
    const markup = renderToStaticMarkup(
      <EvidenceGraph3D
        scenario="Base"
        source="sec-10q-nrr"
        decision={DECISION_10Q}
        approvals={COMPLETED_APPROVALS}
        applied
      />,
    );
    expect(markup).toContain("Illustrative fixture schematic");
    expect(markup).toContain("Staged in this session · fixture schematic");
    expect(markup).not.toContain("sha256=");
    expect(markup).not.toContain("sha256:");
    expect(markup).not.toContain("verified lineage");
  });

  it("shows Verified only for a gate the admissibility rule painted", () => {
    hooks.index = 0;
    const tree = EvidenceGraph3D({
      scenario: "Base",
      source: "sec-10q-nrr",
      decision: DECISION_10Q,
      approvals: COMPLETED_APPROVALS,
      applied: true,
    });
    const status = () =>
      props(findOne(tree, (e) => props(e)["data-testid"] === "text-viz3d-selected-status"))
        .children;
    expect(status()).toBe("Verified");
    const spanPill = findOne(
      tree,
      (e) => props(e)["data-testid"] === "button-viz3d-node-sec-10q-nrr",
    );
    (props(spanPill).onClick as () => void)();
    hooks.index = 0;
    const after = EvidenceGraph3D({
      scenario: "Base",
      source: "sec-10q-nrr",
      decision: DECISION_10Q,
      approvals: COMPLETED_APPROVALS,
      applied: true,
    });
    expect(
      props(findOne(after, (e) => props(e)["data-testid"] === "text-viz3d-selected-status"))
        .children,
    ).toBe("Fixture");
  });
});

describe("EvidenceGraph3D component", () => {
  it("renders the 3D canvas, camera preset controls, cutoff scrubber, and node inspector", () => {
    const markup = renderToStaticMarkup(
      <EvidenceGraph3D
        scenario="Base"
        source={null}
        decision={null}
        approvals={PENDING_APPROVALS}
        applied={false}
      />,
    );
    expect(markup).toContain('data-testid="evidence-graph-3d"');
    expect(markup).toContain('data-testid="canvas-evidence-3d"');
    expect(markup).toContain('data-testid="input-viz3d-cutoff"');
    expect(markup).toContain("3D Evidence &amp; Calculation Lineage Explorer");
    expect(markup).toContain("FY27 Revenue · $842.4m");
    expect(markup).toContain("C-104 conflict active");
  });

  it("does not report unlocked gates after the cutoff blocks an applied decision", () => {
    const render = () => {
      hooks.index = 0;
      return EvidenceGraph3D({
        scenario: "Base",
        source: "sec-10q-nrr",
        decision: DECISION_10Q,
        approvals: COMPLETED_APPROVALS,
        applied: true,
      });
    };
    const initial = render();
    expect(renderToStaticMarkup(initial)).toContain("All gates unlocked");
    const slider = findOne(initial, (e) => props(e)["data-testid"] === "input-viz3d-cutoff");
    (props(slider).onChange as (e: unknown) => void)({ target: { value: "0" } });
    const blockedMarkup = renderToStaticMarkup(render());
    expect(blockedMarkup).toContain("Blocked (Future)");
    expect(blockedMarkup).toContain("Review gates blocked by cutoff");
    expect(blockedMarkup).not.toContain("All gates unlocked");
    (props(slider).onChange as (e: unknown) => void)({ target: { value: "2" } });
    expect(renderToStaticMarkup(render())).toContain("All gates unlocked");
  });

  it.each([false, true])(
    "does not report a future call decision as resolved at filing cutoff (applied=%s)",
    (applied) => {
      const render = () => {
        hooks.index = 0;
        return EvidenceGraph3D({
          scenario: "Base",
          source: "call-turn-48",
          decision: DECISION_CALL,
          approvals: COMPLETED_APPROVALS,
          applied,
        });
      };
      const slider = findOne(render(), (e) => props(e)["data-testid"] === "input-viz3d-cutoff");
      (props(slider).onChange as (e: unknown) => void)({ target: { value: "1" } });
      const blockedMarkup = renderToStaticMarkup(render());
      expect(blockedMarkup).toContain("Review gates blocked by cutoff");
      expect(blockedMarkup).not.toContain("All gates unlocked");
      expect(blockedMarkup).not.toContain("NRR resolved · awaiting guidance");
      (props(slider).onChange as (e: unknown) => void)({ target: { value: "2" } });
      expect(renderToStaticMarkup(render())).toContain(
        applied ? "All gates unlocked" : "NRR resolved · awaiting guidance",
      );
    },
  );

  it("does not report unlocked gates when guidance approvals are incomplete", () => {
    const markup = renderToStaticMarkup(
      <EvidenceGraph3D
        scenario="Base"
        source="sec-10q-nrr"
        decision={DECISION_10Q}
        approvals={PENDING_APPROVALS}
        applied
      />,
    );
    expect(markup).toContain("Pending Review");
    expect(markup).toContain("NRR resolved · awaiting guidance");
    expect(markup).not.toContain("All gates unlocked");
  });

  it("drives the 3D canvas render loop, camera presets, pointer orbit/click, cutoff slider, and node pills", () => {
    const mockCtx = {
      clearRect: vi.fn(),
      createLinearGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
      createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
      fillRect: vi.fn(),
      strokeRect: vi.fn(),
      save: vi.fn(),
      restore: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      closePath: vi.fn(),
      stroke: vi.fn(),
      fill: vi.fn(),
      arc: vi.fn(),
      setLineDash: vi.fn(),
      setTransform: vi.fn(),
      bezierCurveTo: vi.fn(),
      fillText: vi.fn(),
      measureText: vi.fn(() => ({ width: 48 })),
      fillStyle: "",
      strokeStyle: "",
      lineWidth: 1,
      font: "",
    };

    const rafCallbacks: FrameRequestCallback[] = [];
    vi.stubGlobal("window", {
      matchMedia: () => ({ matches: false }),
      requestAnimationFrame: (cb: FrameRequestCallback) => {
        rafCallbacks.push(cb);
        return rafCallbacks.length;
      },
      cancelAnimationFrame: vi.fn(),
    });

    const onSelectNode = vi.fn();
    const tree = () => {
      hooks.index = 0;
      return EvidenceGraph3D({
        scenario: "Bull",
        source: "call-turn-48",
        decision: DECISION_CALL,
        approvals: COMPLETED_APPROVALS,
        applied: true,
        onSelectNode,
      });
    };

    tree();
    // Attach mock canvas to canvasRef (hook index 5)
    const canvasRef = hooks.values[5] as { current: unknown };
    canvasRef.current = {
      width: 680,
      height: 400,
      getContext: () => mockCtx,
      getBoundingClientRect: () => ({ left: 0, top: 0, width: 680, height: 400 }),
    };

    // Run effect to draw 3D frame and schedule animation frame
    const cleanup = hooks.effects[0]?.();
    expect(mockCtx.clearRect).toHaveBeenCalled();
    expect(mockCtx.arc).toHaveBeenCalled();
    expect(rafCallbacks.length).toBeGreaterThan(0);
    cleanup?.();

    // Exercise preset buttons ("dag", "temporal", "constellation") and orbit toggle
    for (const presetId of ["dag", "temporal", "constellation"]) {
      const btn = findOne(
        tree(),
        (e) => props(e)["data-testid"] === `button-viz3d-preset-${presetId}`,
      );
      (props(btn).onClick as () => void)();
    }
    const orbitBtn = findOne(tree(), (e) => props(e)["data-testid"] === "button-viz3d-orbit");
    (props(orbitBtn).onClick as () => void)();

    // Exercise cutoff slider
    const slider = findOne(tree(), (e) => props(e)["data-testid"] === "input-viz3d-cutoff");
    (props(slider).onChange as (e: unknown) => void)({ target: { value: "0" } });
    const root = tree();
    // Re-run effect with cutoffStep = 0 so "cutoff-blocked" node colors are painted
    hooks.effects[hooks.effects.length - 1]?.();

    // Exercise node pill selection
    const gatePill = findOne(
      root,
      (e) => props(e)["data-testid"] === "button-viz3d-node-gate-c104",
    );
    (props(gatePill).onClick as () => void)();
    expect(onSelectNode).toHaveBeenCalledWith("gate-c104");

    const scenarioPill = findOne(
      tree(),
      (e) => props(e)["data-testid"] === "button-viz3d-node-calc-scenario",
    );
    (props(scenarioPill).onClick as () => void)();

    const spanPill = findOne(
      tree(),
      (e) => props(e)["data-testid"] === "button-viz3d-node-sec-10q-nrr",
    );
    (props(spanPill).onClick as () => void)();

    // Exercise canvas pointer drag and click hit-testing
    const canvasEl = findOne(tree(), (e) => props(e)["data-testid"] === "canvas-evidence-3d");
    const projectedRef = hooks.values[9] as {
      current: { id: string; sx: number; sy: number; r: number; depth: number }[];
    };
    const targetHit = projectedRef.current[0]!;
    (props(canvasEl).onClick as (e: unknown) => void)({
      clientX: targetHit.sx,
      clientY: targetHit.sy,
    });

    // Pointer drag gesture (> 4px suppresses click selection)
    (props(canvasEl).onPointerDown as (e: unknown) => void)({ clientX: 100, clientY: 100 });
    (props(canvasEl).onPointerMove as (e: unknown) => void)({ clientX: 120, clientY: 115 });
    (props(canvasEl).onPointerUp as () => void)();
    (props(canvasEl).onClick as (e: unknown) => void)({
      clientX: targetHit.sx,
      clientY: targetHit.sy,
    });
    (props(canvasEl).onPointerLeave as () => void)();
    expect(findAll(tree(), (e) => e.type === "button").length).toBeGreaterThan(5);
  });

  describe("label layout on the canvas", () => {
    // Roughly the advance of 12px semibold sans text, so widths are realistic.
    const ctx2d = new Proxy(
      { measureText: (text: string) => ({ width: text.length * 7 }) },
      {
        get: (target, key) =>
          key in target
            ? target[key as keyof typeof target]
            : key === "createLinearGradient" || key === "createRadialGradient"
              ? () => ({ addColorStop: () => undefined })
              : () => undefined,
        set: () => true,
      },
    );
    type Placement = { id: string; form: string; x: number; y: number; w: number; h: number };
    const overlaps = (a: Placement, b: Placement) =>
      a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

    const mount = (wrapWidth: number | null) => {
      // Reduced motion paints exactly one frame and schedules no animation.
      vi.stubGlobal("window", { matchMedia: () => ({ matches: true }), devicePixelRatio: 2 });
      const tree = () => {
        hooks.index = 0;
        return EvidenceGraph3D({
          // Bull lifts the output node highest; the near L0 spans set the bottom.
          scenario: "Bull",
          source: null,
          decision: null,
          approvals: PENDING_APPROVALS,
          applied: false,
        });
      };
      tree();
      const canvas = {
        width: 680,
        height: 400,
        style: {} as Record<string, string>,
        getContext: () => ctx2d,
      };
      (hooks.values[5] as { current: unknown }).current = canvas;
      if (wrapWidth !== null) {
        (hooks.values[10] as { current: unknown }).current = { clientWidth: wrapWidth };
      }
      return {
        tree,
        canvas,
        orbitYawOffset: hooks.values[7] as { current: number },
        projected: hooks.values[9] as {
          current: { id: string; sx: number; sy: number; r: number }[];
        },
        placements: hooks.values[12] as { current: Map<string, Placement> },
        size: hooks.values[15] as { current: { width: number; height: number } },
      };
    };

    it.each([
      ["the legacy 680x400 canvas", null],
      ["a 1440px desktop card", 869],
      ["a 390px phone card", 316],
    ])("keeps nodes and labels in frame and never overlaps labels on %s", (_name, wrapWidth) => {
      const { tree, canvas, orbitYawOffset, projected, placements, size } = mount(wrapWidth);
      for (const presetId of ["constellation", "dag", "temporal"]) {
        const btn = findOne(
          tree(),
          (e) => props(e)["data-testid"] === `button-viz3d-preset-${presetId}`,
        );
        (props(btn).onClick as () => void)();
        for (const selected of ["output-fy27-rev", "sec-10q-actuals", "calc-jacobi-scc"]) {
          const pill = findOne(
            tree(),
            (e) => props(e)["data-testid"] === `button-viz3d-node-${selected}`,
          );
          (props(pill).onClick as () => void)();
          tree();
          const paint = hooks.effects[hooks.effects.length - 1]!;
          for (let step = 0; step < 24; step += 1) {
            orbitYawOffset.current = (step * Math.PI) / 12;
            paint();
            const { width, height } = size.current;
            if (wrapWidth !== null) {
              expect(width).toBe(wrapWidth);
              expect(canvas.width).toBe(wrapWidth * 2);
              expect(canvas.style.height).toBe(`${height}px`);
            }
            expect(projected.current).toHaveLength(11);
            for (const { id, sx, sy, r } of projected.current) {
              const where = `${presetId} yaw+${step}/24 ${id}`;
              // r is the hit radius (sphere + 6), which covers the selection ring.
              expect(sy - r, where).toBeGreaterThanOrEqual(0);
              expect(sy + r, where).toBeLessThanOrEqual(height);
              expect(sx - r, where).toBeGreaterThanOrEqual(0);
              expect(sx + r, where).toBeLessThanOrEqual(width);
            }
            const all = [...placements.current.values()];
            const nodeLabels = all.filter((p) => !p.id.startsWith("layer-"));
            expect(nodeLabels).toHaveLength(11);
            expect(placements.current.get(selected)?.form, `${presetId} ${selected}`).toBe("full");
            const shown = all.filter((p) => p.form !== "hidden");
            for (const p of shown) {
              const where = `${presetId} yaw+${step}/24 ${p.id}`;
              expect(p.x, where).toBeGreaterThanOrEqual(0);
              expect(p.y, where).toBeGreaterThanOrEqual(0);
              expect(p.x + p.w, where).toBeLessThanOrEqual(width);
              expect(p.y + p.h, where).toBeLessThanOrEqual(height);
            }
            for (let i = 0; i < shown.length; i += 1) {
              for (let j = i + 1; j < shown.length; j += 1) {
                expect(
                  overlaps(shown[i]!, shown[j]!),
                  `${presetId} yaw+${step}/24 ${shown[i]!.id} x ${shown[j]!.id}`,
                ).toBe(false);
              }
            }
            if (presetId === "dag") break; // the flat layout ignores yaw
          }
        }
      }
    });

    it("moves the HTML label pills and repaints for hover and keyboard focus", () => {
      const { tree, placements } = mount(869);
      const fakeEls = new Map<
        string,
        { dataset: Record<string, string>; style: Record<string, string> }
      >();
      for (const span of findAll(tree(), (e) => props(e)["data-lineage-label"] !== undefined)) {
        const id = props(span)["data-lineage-label"] as string;
        const el = { dataset: {}, style: {} };
        fakeEls.set(id, el);
        (props(span) as { ref: (el: unknown) => void }).ref(el);
      }
      expect(fakeEls.size).toBe(15);
      tree();
      hooks.effects[hooks.effects.length - 1]!();
      const output = fakeEls.get("output-fy27-rev")!;
      expect(output.dataset.form).toBe("full");
      const placed = placements.current.get("output-fy27-rev")!;
      expect(output.style.transform).toBe(
        `translate(${Math.round(placed.x)}px, ${Math.round(placed.y)}px)`,
      );
      expect(output.style.width).toBe(`${placed.w}px`);

      // Focusing or hovering a chip repaints with that node prioritised.
      const pill = findOne(
        tree(),
        (e) => props(e)["data-testid"] === "button-viz3d-node-call-turn-48",
      );
      (props(pill).onFocus as () => void)();
      (props(pill).onMouseEnter as () => void)();
      expect(placements.current.get("call-turn-48")?.form).toBe("full");
      (props(pill).onMouseLeave as () => void)();
      (props(pill).onBlur as () => void)();

      // In the flat DAG the pointer hovers instead of rotating the camera.
      const canvasEl = findOne(tree(), (e) => props(e)["data-testid"] === "canvas-evidence-3d");
      (hooks.values[5] as { current: Record<string, unknown> }).current.getBoundingClientRect =
        () => ({ left: 0, top: 0, width: 869, height: 504 });
      (props(canvasEl).onPointerDown as (e: unknown) => void)({ clientX: 0, clientY: 0 });
      (props(canvasEl).onPointerMove as (e: unknown) => void)({
        clientX: placed.x + 2,
        clientY: placed.y + 2,
      });
      expect((hooks.values[13] as { current: { hover: string | null } }).current.hover).toBe(
        "output-fy27-rev",
      );
      // Clicking a label selects its node.
      const actuals = placements.current.get("sec-10q-actuals")!;
      (props(canvasEl).onClick as (e: unknown) => void)({
        clientX: actuals.x + 2,
        clientY: actuals.y + 2,
      });
      expect(hooks.values[2]).toBe("sec-10q-actuals");
      (props(canvasEl).onPointerLeave as () => void)();
      expect((hooks.values[13] as { current: { hover: string | null } }).current.hover).toBe(null);
      for (const span of findAll(tree(), (e) => props(e)["data-lineage-label"] !== undefined)) {
        (props(span) as { ref: (el: unknown) => void }).ref(null);
      }
    });
  });

  it("opens in the Layered DAG with orbit off, and orbits only on request in 3D Orbit", () => {
    const rafCallbacks: FrameRequestCallback[] = [];
    vi.stubGlobal("window", {
      matchMedia: () => ({ matches: false }),
      requestAnimationFrame: (cb: FrameRequestCallback) => rafCallbacks.push(cb),
      cancelAnimationFrame: vi.fn(),
    });
    const render = () => {
      hooks.index = 0;
      return EvidenceGraph3D({
        scenario: "Base",
        source: null,
        decision: null,
        approvals: PENDING_APPROVALS,
        applied: false,
      });
    };
    const byTestId = (id: string) => findOne(render(), (e) => props(e)["data-testid"] === id);
    const ctx2d = new Proxy(
      { measureText: () => ({ width: 48 }) },
      {
        get: (target, key) =>
          key in target
            ? target[key as keyof typeof target]
            : key === "createLinearGradient" || key === "createRadialGradient"
              ? () => ({ addColorStop: () => undefined })
              : () => undefined,
        set: () => true,
      },
    );
    render();
    (hooks.values[5] as { current: unknown }).current = {
      width: 680,
      height: 400,
      getContext: () => ctx2d,
    };
    const yaw = hooks.values[7] as { current: number };
    const frame = () => {
      render();
      const cleanup = hooks.effects[hooks.effects.length - 1]!();
      cleanup?.();
    };

    expect(props(byTestId("button-viz3d-preset-dag"))["aria-pressed"]).toBe(true);
    expect(props(byTestId("button-viz3d-preset-constellation"))["aria-pressed"]).toBe(false);
    const orbitOff = byTestId("button-viz3d-orbit");
    expect(props(orbitOff)["aria-pressed"]).toBe(false);
    expect(props(orbitOff).disabled).toBe(true);
    expect(props(orbitOff).children).toBe("Auto Orbit");
    frame();
    expect(yaw.current).toBe(0);

    (props(byTestId("button-viz3d-preset-constellation")).onClick as () => void)();
    expect(props(byTestId("button-viz3d-orbit")).disabled).toBe(false);
    frame();
    expect(yaw.current).toBe(0);

    (props(byTestId("button-viz3d-orbit")).onClick as () => void)();
    const orbitOn = byTestId("button-viz3d-orbit");
    expect(props(orbitOn)["aria-pressed"]).toBe(true);
    expect(props(orbitOn).children).toBe("Pause Orbit");
    frame();
    expect(yaw.current).toBeGreaterThan(0);

    // Leaving the 3D Orbit view stops the orbit; coming back does not restart it.
    (props(byTestId("button-viz3d-preset-temporal")).onClick as () => void)();
    expect(props(byTestId("button-viz3d-orbit"))["aria-pressed"]).toBe(false);
    frame();
    expect(yaw.current).toBe(0);
    (props(byTestId("button-viz3d-preset-constellation")).onClick as () => void)();
    expect(props(byTestId("button-viz3d-orbit"))["aria-pressed"]).toBe(false);
  });

  it("ships valid UTF-8 and control-character-free SVG architecture diagrams", () => {
    const svgFiles = [
      "../../../../docs/architecture/assets/system-overview.svg",
      "../../../../docs/architecture/assets/evidence-to-model-pipeline.svg",
      "../../../../docs/architecture/assets/hybrid-retrieval-and-extraction-fsm.svg",
      "../../../../docs/architecture/assets/calculation-dag-and-provenance.svg",
    ];
    for (const rel of svgFiles) {
      const content = readFileSync(new URL(rel, import.meta.url), "utf8");
      expect(content.startsWith("<svg")).toBe(true);
      expect(content.trimEnd().endsWith("</svg>")).toBe(true);
      const hasControlChar = [...content].some((ch) => {
        const code = ch.charCodeAt(0);
        return code < 32 && code !== 9 && code !== 10 && code !== 13;
      });
      expect(hasControlChar).toBe(false);
    }
  });
});

describe("placeLabels", () => {
  const anchor = (id: string, x: number, y: number) => ({ id, x, y, r: 10 });
  const request = (id: string, x: number, y: number, tier: 0 | 1 | 2, full = 160) => ({
    anchor: anchor(id, x, y),
    fullWidth: full,
    shortWidth: 60,
    tier,
  });

  it("gives the selected label its full text and shrinks or drops the rest in a crowd", () => {
    // Five nodes on top of each other in a canvas with room for only a few rows.
    const requests = [
      request("sel", 100, 60, 0),
      request("a", 102, 60, 1),
      request("b", 98, 62, 2),
      request("c", 100, 58, 2),
      request("d", 101, 61, 2),
    ];
    const placements = placeLabels({
      width: 200,
      height: 120,
      side: "below",
      requests,
      obstacles: requests.map((r) => r.anchor),
      captions: [{ id: "layer-x", x: 4, y: 4, w: 190, h: 14 }],
    });
    const byId = new Map(placements.map((p) => [p.id, p]));
    expect(byId.get("sel")?.form).toBe("full");
    expect(placements.some((p) => p.form === "short")).toBe(true);
    expect(placements.some((p) => p.form === "hidden")).toBe(true);
    const shown = placements.filter((p) => p.form !== "hidden");
    for (const p of shown) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.x + p.w).toBeLessThanOrEqual(200);
      expect(p.y + p.h).toBeLessThanOrEqual(120);
    }
    for (let i = 0; i < shown.length; i += 1)
      for (let j = i + 1; j < shown.length; j += 1) {
        const [a, b] = [shown[i]!, shown[j]!];
        expect(a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h).toBe(
          false,
        );
      }
  });

  it("puts labels beside nodes in the wide DAG and keeps last frame's spot when still free", () => {
    const requests = [request("n", 100, 100, 2, 120)];
    const first = placeLabels({
      width: 600,
      height: 400,
      side: "right",
      requests,
      obstacles: requests.map((r) => r.anchor),
    });
    expect(first[0]).toMatchObject({ form: "full", key: "right", leader: false, h: LABEL_HEIGHT });
    expect(first[0]!.x).toBeGreaterThan(110);

    const previous = new Map([["n", { ...first[0]!, key: "below" }]]);
    const second = placeLabels({
      width: 600,
      height: 400,
      side: "right",
      requests,
      obstacles: requests.map((r) => r.anchor),
      previous,
    });
    expect(second[0]?.key).toBe("below");
  });

  it("draws a leader line for a label pushed away from its node", () => {
    const requests = [request("sel", 100, 100, 0, 180), request("n", 100, 100, 1, 180)];
    // Both nodes at the same spot with no short form room: the second label must move away.
    const placements = placeLabels({
      width: 200,
      height: 400,
      side: "below",
      requests: requests.map((r) => ({ ...r, shortWidth: 180 })),
      obstacles: requests.map((r) => r.anchor),
    });
    expect(placements[0]?.leader).toBe(false);
    expect(placements[1]?.form).toBe("full");
  });

  it("sizes the canvas and lays the DAG out by layer", () => {
    expect(canvasHeightFor(320)).toBe(400);
    expect(canvasHeightFor(869)).toBe(504);
    expect(canvasHeightFor(2000)).toBe(520);
    expect(labelBoxWidth(100.2)).toBe(120);
    const { nodes } = buildEpistemicGraph({
      scenario: "Base",
      source: null,
      decision: null,
      approvals: PENDING_APPROVALS,
      applied: false,
      cutoffStep: 2,
    });
    const wide = dagLayout(nodes, WIDE_DAG_MIN_WIDTH, 400);
    const narrow = dagLayout(nodes, 316, 400);
    expect(wide.side).toBe("right");
    expect(narrow.side).toBe("below");
    const y = (id: string) => wide.positions.get(id)!.y;
    expect(y("output-fy27-rev")).toBeLessThan(y("calc-jacobi-scc"));
    expect(y("calc-jacobi-scc")).toBeLessThan(y("gate-c104"));
    expect(y("gate-c104")).toBeLessThan(y("sec-10q-nrr"));
    for (const node of nodes) {
      const p = narrow.positions.get(node.id)!;
      expect(p.x).toBeGreaterThan(0);
      expect(p.x).toBeLessThan(316);
    }
  });
});
