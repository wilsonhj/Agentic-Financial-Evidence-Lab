import { submitQueryAction } from "../lib/observatory/actions";
import {
  FILTER_MAX_ITEMS,
  QUESTION_MAX,
  TOP_K_DEFAULT,
  TOP_K_MAX,
  TOP_K_MIN,
} from "../lib/observatory/controls";
import { LANE_LABELS, LANES } from "../lib/observatory/trace-view";

/**
 * Bounded query controls. Native input constraints keep values within the
 * frozen contract bounds (top_k 1..100, question length, unique lanes); the
 * server action re-validates before creating a query. Optional parentQueryId
 * links a control-changed query to its parent for comparison.
 */
export function ObservatoryControls({
  parentQueryId,
  error,
}: {
  parentQueryId?: string;
  error?: string;
}) {
  return (
    <form
      className="obs-controls"
      action={submitQueryAction}
      aria-labelledby="obs-controls-heading"
    >
      <h2 id="obs-controls-heading">
        {parentQueryId ? "Rerun with changed controls" : "New query"}
      </h2>
      {error && (
        <p className="reader-banner citation-error" role="alert">
          Action failed: {error}
        </p>
      )}
      {parentQueryId && <input type="hidden" name="parentQueryId" value={parentQueryId} />}

      <label htmlFor="obs-question">Question</label>
      <textarea
        id="obs-question"
        name="question"
        required
        maxLength={QUESTION_MAX}
        rows={2}
        defaultValue=""
        placeholder="e.g. What was total revenue for Q1 2026?"
        aria-describedby="obs-question-hint"
      />
      <p id="obs-question-hint" className="obs-hint">
        Ask about the filings in this workspace. Up to {QUESTION_MAX} characters.
      </p>

      <fieldset aria-describedby="obs-lanes-hint">
        <legend>Lanes</legend>
        {LANES.map((lane) => (
          <label key={lane} className="obs-check">
            <input type="checkbox" name="lanes" value={lane} defaultChecked />
            {LANE_LABELS[lane]}
          </label>
        ))}
      </fieldset>
      <p id="obs-lanes-hint" className="obs-hint">
        All four lanes run by default; leaving every box clear also runs all four.
      </p>

      <label htmlFor="obs-topk">
        Top-k ({TOP_K_MIN}–{TOP_K_MAX})
      </label>
      <input
        id="obs-topk"
        name="topK"
        type="number"
        min={TOP_K_MIN}
        max={TOP_K_MAX}
        step={1}
        inputMode="numeric"
        placeholder={String(TOP_K_DEFAULT)}
        aria-describedby="obs-topk-hint"
      />
      <p id="obs-topk-hint" className="obs-hint">
        Leave blank to use the server default of {TOP_K_DEFAULT}.
      </p>

      <label htmlFor="obs-asof">Cutoff (as-of)</label>
      <input id="obs-asof" name="asOf" type="datetime-local" aria-describedby="obs-asof-hint" />
      <p id="obs-asof-hint" className="obs-hint">
        Leave blank to use the workspace cutoff. Times are read as UTC; a cutoff later than the
        workspace&apos;s is rejected.
      </p>

      <label htmlFor="obs-forms">Form filters (max {FILTER_MAX_ITEMS}, comma-separated)</label>
      <input
        id="obs-forms"
        name="forms"
        type="text"
        placeholder="e.g. 10-Q, 10-K"
        aria-describedby="obs-forms-hint"
      />
      <p id="obs-forms-hint" className="obs-hint">
        Leave blank to search all forms.
      </p>

      <label htmlFor="obs-periods">Period filters (max {FILTER_MAX_ITEMS}, comma-separated)</label>
      <input
        id="obs-periods"
        name="periods"
        type="text"
        placeholder="e.g. 2026-Q1"
        aria-describedby="obs-periods-hint"
      />
      <p id="obs-periods-hint" className="obs-hint">
        Leave blank to search all periods.
      </p>

      <button type="submit" className="retry-button">
        Run query
      </button>
    </form>
  );
}
