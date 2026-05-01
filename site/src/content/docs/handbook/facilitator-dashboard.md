---
title: Facilitator Dashboard
description: The /app/facilitator/runs/ surface — live cohort monitoring, kill switch, REST API.
sidebar:
  order: 6
---

The facilitator dashboard is the browser-side surface for monitoring an in-progress workshop cohort. It lives at `/xrpl-lab/app/facilitator/runs/` once `xrpl-lab serve` is running, and it is the only place where you can see all in-flight learner runs side-by-side without poking the API directly.

This page documents the runs surface and the underlying REST API. Audience split: workshop facilitators on the first three sections, integration users (custom monitoring tools, external dashboards) on the **GET /api/runs** section.

## 1. Overview — what the runs page shows

Open `http://localhost:4321/xrpl-lab/app/facilitator/runs/` in dev (with `xrpl-lab serve` and `cd site && npm run dev` both running) or hit the production-build path at whatever host/port `xrpl-lab serve` is bound to.

The page renders one card per known run. Each card shows:

| Field | What it tells you |
|-------|-------------------|
| **Module ID** | Which module the learner is running (e.g., `trust-lines-101`) |
| **Status badge** | One of ACTIVE / DONE / FAILED / CANCELLED — icon + color + text label so the signal survives projectors and color-blind users |
| **Dry-run badge** | Present when the run is in offline-sandbox mode. Useful for spotting "this learner is in dry-run when they meant to be on testnet" |
| **Elapsed time** | Seconds-or-minutes since the run started — drives your "is this learner stuck?" intuition |
| **Queue depth** | Pending message count for that run's WebSocket queue. Non-zero usually means the dashboard is keeping up; persistent backlog is a signal |
| **Run ID (short)** | First 8 chars of the run UUID, with the full ID in the title attribute for hover. Copy-paste this into `DELETE /api/runs/{run_id}` if you need to cancel from curl |
| **Capacity badge** | Top-right of the page. Reports `<active>/<max> active` — the rate-limit cap (`_MAX_CONCURRENT_RUNS`) versus how many are running right now |

The page **auto-refreshes every 5 seconds while the tab is visible**. When the tab is backgrounded (`document.visibilityState === 'hidden'`), polling pauses entirely — workshops where you leave this open all day don't burn API capacity in the background, and battery life is preserved on facilitator laptops. Polling resumes immediately when the tab returns to foreground, with an extra refresh up front so you see current state without waiting for the next tick.

The page lists both active (`running`) sessions and recently-completed sessions (`completed` / `failed` / `cancelled`). Completed sessions are pruned by a grace-period cleanup task in the WS handler, so the list naturally settles back to active runs only over time.

## 2. The Kill button — DELETE semantics

The Kill button only renders for runs in the `running` status. The other three terminal statuses (completed, failed, cancelled) hide the button — there's nothing to cancel.

Clicking Kill:

1. Prompts for confirmation (browser `confirm()` dialog with the run's module ID + run ID)
2. Fires `DELETE /api/runs/{run_id}` against the API
3. The server cancels the underlying `asyncio` task, marks the run `status="cancelled"`, and emits a final `RUNTIME_CANCELLED` envelope onto the run's WebSocket queue
4. Any connected dashboard WebSocket sees that envelope as its terminal frame, then the WS handler closes the socket with code 1000 (normal closure) — facilitator-initiated cancel is not an error, so the close code stays in the success range
5. The dashboard force-refreshes the runs list so the row updates to CANCELLED

The cancel is **idempotent on already-terminated runs**. A double-click, a flaky network, or a confused facilitator firing the same DELETE twice returns 200 with `status="already_terminated"` rather than failing. A DELETE against a fully unknown `run_id` returns 404 with the structured `RUN_NOT_FOUND` envelope.

The dashboard's error handling treats 404 specially — it surfaces an alert that says "either the run already finished, or the cancel endpoint isn't available on this API; refresh to see latest state" rather than presenting it as a hard error. That's intentional: in mixed-version cohorts (one facilitator on a newer build, one on older) the message is actionable.

**When to use it in a workshop:** a learner's run is wedged on a slow testnet round-trip, or they walked away from a half-completed module, or they ran the wrong module by mistake. Free the concurrency slot without restarting the server. The learner can immediately start another run; their other modules' state is untouched.

## 3. GET /api/runs — for integration users

If you're building your own facilitator monitoring tool — a Slack bot, a side dashboard, a custom CLI — hit the same endpoint the runs page consumes:

```bash
curl http://localhost:8321/api/runs | jq
```

### Response shape

```json
{
  "runs": [
    {
      "run_id": "5f8a...uuid...",
      "module_id": "trust-lines-101",
      "status": "running",
      "created_at": "2026-04-30T10:14:22.831Z",
      "elapsed_seconds": 47.2,
      "queue_size": 0,
      "dry_run": false
    }
  ],
  "max_concurrent": 8,
  "active_count": 1
}
```

### Field semantics

- **`runs[]`** — every known session, both active and recently-completed (within the cleanup grace window). Sort order is whatever the in-memory dict yields; sort client-side if you need stable ordering.
- **`runs[].status`** — exactly one of `running` / `completed` / `failed` / `cancelled`. Four-status schema; no `pending`, no `queued`, no `error` (the WS layer maps internal errors onto `failed` for this projection).
- **`runs[].queue_size`** — pending WebSocket messages for that run. Useful as a "is the consumer keeping up?" gauge but should not be treated as workshop-state truth.
- **`runs[].dry_run`** — `true` when the run was started with `--dry-run`. Worth surfacing in your custom UI so facilitators can spot dry-run-by-mistake cohorts.
- **`max_concurrent`** — the configured cap on simultaneous running sessions (`_MAX_CONCURRENT_RUNS` in the server). Treat as ground truth for the capacity metric — if you compute `active_count / max_concurrent` you get the headroom indicator the dashboard renders.
- **`active_count`** — the count of `runs[]` currently in `running` status. Cheaper than counting client-side and stays consistent with the server's own rate-limiter view.

The `runs[].run_id` is also the key for two related endpoints:

- `GET /api/runs/{run_id}` — same shape as a single `runs[]` element. 404 with `RUN_NOT_FOUND` if the run never existed or has been pruned.
- `DELETE /api/runs/{run_id}` — the cancel endpoint described above.

**Auth model:** the entire `/api/runs` surface inherits the same CORS gate as the rest of the HTTP API — `server.py` restricts to localhost. There is no token auth in v1.6.0; if you're exposing this surface beyond loopback (which the workshop threat model does not recommend), front it with your own auth layer.

## 4. Operational notes

### Polling discipline

The 5-second interval is set in the page script (`POLL_INTERVAL_MS`) and runs only while the tab is visible. Two consequences worth knowing:

- **Cohort capacity preserved** — eight facilitators with eight backgrounded tabs aren't compounding API load; only the visible tab polls.
- **First refresh is immediate** — when you switch back to the tab, the page calls `refresh()` synchronously before the next interval tick, so you don't see stale data for up to 5 seconds while waiting.

If you're embedding this surface in a custom integration, mirror the visibilityState pattern. Five-second polling against the JSON list is cheap; 100ms-busywait polling is rude to the same FastAPI process that's also driving live module runs.

### Cleanup on Astro client-side navigation

The page registers handlers on `astro:before-swap` so listeners and the polling timer are torn down cleanly when a facilitator navigates away (e.g., to the artifacts page) and re-mounted fresh on return. Practical effect: leaving this page open for 8 hours with intermittent navigation does not accumulate timers or memory.

If you fork the page or wire your own JavaScript into it, follow the same pattern — Astro's view transitions don't unload the page, so your cleanup logic has to be explicit.

### Status-schema canonicalization

The 4-status schema (`running` / `completed` / `failed` / `cancelled`) is canonical across both the API and the frontend. Two places where this matters:

- **Schema definition** — `xrpl_lab/api/schemas.py` defines `RunInfo.status` with that comment.
- **UI mapping** — the page's `statusBadge()` function has explicit handlers for all four values and a defensive fallback for anything else (which should not happen given the schema).

Don't introduce a fifth status without coordinating both ends — the runs page will fall back to a neutral badge for unknown values, which is functional but loses the semantic UI signal.

### Running it locally

In development:

```bash
# Terminal 1
xrpl-lab serve

# Terminal 2
cd site && npm run dev

# Browser
open http://localhost:4321/xrpl-lab/app/facilitator/runs/
```

In production (after `npm run build`), `xrpl-lab serve` alone is enough — it serves both the API and the built frontend.

---

For the broader facilitator workflow this dashboard supports, see the [Facilitator Guide](/xrpl-lab/handbook/facilitator-guide/). For the `xrpl-lab serve` flags themselves, see the [Commands](/xrpl-lab/handbook/commands/) reference.
