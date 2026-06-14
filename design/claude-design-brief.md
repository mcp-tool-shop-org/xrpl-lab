# Claude Design handoff brief — XRPL Lab dashboard redesign

**For:** https://claude.ai/design (attach `dashboard-before.html` from this folder as the input file).
**Goal:** redesign the XRPL Lab web dashboard to be **more human-friendly and accessible**, keeping every data contract and behavior intact.
**Round-trip:** Claude Design produces the redesigned standalone HTML → hand back to Claude Code, which re-implements the visual layer in the Astro components (`site/src/pages/app/*`, `site/src/layouts/DashboardLayout.astro`) and re-runs the test suite + a Lighthouse/axe pass.

---

## Paste this prompt into Claude Design

> You are redesigning the **XRPL Lab** web dashboard. XRPL Lab is a **testnet-only XRP Ledger training workbook** — adult learners run hands-on modules (send a payment, set a trust line, make markets on the DEX, provide AMM liquidity) and earn verifiable artifacts (a SHA-256-sealed proof pack, a certificate, audit reports). The dashboard has two audiences: **a learner** running modules and reading their progress, and **a workshop facilitator** monitoring a room of concurrent learner runs on a second screen.
>
> The attached `dashboard-before.html` is the CURRENT dashboard (three core screens — Overview, Live Runner, Facilitator · Runs — switchable via the top tabs). Redesign it to feel **calm, confident, and legible-at-a-glance**, suitable for a classroom projector AND a laptop. Keep it **dark-first** with the existing emerald accent, but you may evolve the palette, type, spacing, and components.
>
> **Make these the redesign priorities (in order):**
> 1. **Typography & hierarchy** — introduce a real type scale (distinct display / heading / body / mono); the current system-font flatness makes everything read at one level. Tighten vertical rhythm and spacing.
> 2. **Status legibility** — status is shown as dot + icon + text today (keep that triple-encoding — never color alone). Make the four run states (ACTIVE / DONE / FAILED / CANCELLED) and the three health states (ok / warn / error) instantly distinguishable by **shape + label**, not hue, at projector distance.
> 3. **Replace the native `confirm()` / `alert()` dialogs** (the facilitator "Kill run" confirmation and error alerts) with a **branded modal** — `role="alertdialog"`, focus-trapped, Escape to cancel, Enter to confirm, visible focus ring.
> 4. **The Live Runner** is the emotional centre — a learner watches their transaction land. Elevate the terminal/output (monospace, readable, scrollable, with a clear running/done/failed/stalled state), the step rail (○ pending, ◉ running, ✓ done, ✗ failed — distinct glyphs, not just color), and the completion banner (success / error / "connection stalled — reload"). Add a clear **loading** and **empty** state everywhere data is fetched.
> 5. **Facilitator · Runs** must read like an air-traffic board: capacity at a glance ("3 / 8 active"), one row per run with module, elapsed, queue depth, status, and the Kill action only on running rows.
> 6. **Accessibility to WCAG 2.1 AA** — verify text/background contrast ≥ 4.5:1 (the colored-pill badges are the risk: emerald/amber/red text on tinted backgrounds), full keyboard navigation with a visible focus ring, ARIA roles for the tablist (Artifacts page) and the live regions (status label, runs list), `aria-live="polite"` on streaming surfaces, and `alt`/labels on every icon-only control.
> 7. **Responsive** — graceful from 1920px (projector) down to 375px (phone); the sidebar collapses, grids stack, type stays readable.
>
> **HARD PRESERVATION LIST — do not change any of these (they are the contract with the backend; changing them breaks the app):**
> - Every data field rendered keeps its name and shape (see "Data contract" below). You may restyle and re-lay-out freely, but a field that is shown today must still be shown, by the same name.
> - The route/base path `/xrpl-lab/app/*` and the screen set (Overview, Modules, Module detail, Run, Doctor, Artifacts, Facilitator index, Facilitator runs, 404).
> - The WebSocket message types the Live Runner reacts to: `step`, `output`, `step_complete`, `tx`, `error`, `complete`, `ping` — and the behaviors keyed off them (live step progress, terminal append, tx list, completion banner, the 45-second liveness watchdog → "connection stalled" state, bounded reconnect).
> - The facilitator polling model (5s refresh, pause when tab hidden) and the Kill action targeting `DELETE /api/runs/{run_id}`.
> - Dark-mode-first (the product ships dark; a light theme is optional/additive, not a replacement).
>
> Deliver a single standalone HTML file (offline, no external resources — inline CSS/SVG/JS), keeping the three-screen tab switcher so the redesign is reviewable. Note any current bugs you spot without fixing them.

---

## Data contract (the hard preservation list, in detail)

A redesign restyles these; it must not rename or drop them. Source of truth: `site/src/lib/api.ts` + `xrpl_lab/api/schemas.py`.

| Screen | Endpoint | Fields the UI renders (keep all) |
|--------|----------|----------------------------------|
| Overview | `GET /api/status` | `modules_completed`, `modules_total`, `wallet_configured`, `wallet_address`, `last_run{module,timestamp,success}`, `network`, `version`, `track_progress[]`, `has_proof_pack`, `has_certificate`, `report_count` |
| Overview | `GET /api/doctor` | `overall` (healthy\|warning\|error), `checks[]{name,status(pass\|warn\|fail),message}` |
| Modules | `GET /api/modules` | `ModuleSummary[]`: `id,title,track,level,time_estimate,mode,completed,is_next` |
| Module detail | `GET /api/modules/{id}` | `ModuleDetail`: + `prerequisites[],artifacts[],description,steps[]` |
| Run | `POST /api/run/{id}?dry_run=` → `{run_id,status}`; `WS /api/run/{id}/ws?run_id=` | message types `step{action,index,total}`, `output{text}`, `step_complete{action,success}`, `tx{txid,result_code}`, `error{message}`, `complete{success,txids,report_path?}`, `ping` |
| Doctor | `GET /api/doctor` | as above |
| Artifacts | `GET /api/artifacts/{proof-pack,certificate,reports}` | `ProofPack{version,generated,modules[],integrity}`, `Certificate{holder,issued,modules_completed,hash}`, `Report[]{title,generated,content}` |
| Facilitator runs | `GET /api/runs`; `DELETE /api/runs/{run_id}` | `RunListResponse{runs[],max_concurrent,active_count}`; `RunInfo{run_id,module_id,status,created_at,elapsed_seconds,queue_size,dry_run}` |

**Error-state copy to keep (humanized):** timeout → "Request timed out. The API may be slow or restarting." · network down → "API is offline. Run `xrpl-lab serve`, then refresh." · stalled WS → "Connection stalled — the server isn't responding. Reload to reconnect."

## Brand starting point (evolve, don't discard)

- Name **XRPL Lab**, tagline *"learn by doing, prove by artifact."*, "XL" emerald badge.
- Palette: bg slate-900/950, panels slate-800, borders slate-700; accent **emerald-400 `#34d399`** / emerald-500 `#10b981`; warn amber-400 `#fbbf24`; error red-400 `#f87171`; text slate-100 / slate-400.
- Dark-first. Monospace for txids / code / terminal.

## Accessibility targets (what Claude Code will verify on the way back)

- WCAG 2.1 **AA** contrast on all text, **including pill badges on tinted fills**.
- Keyboard: every action reachable, visible focus ring, modal focus-trap (Esc/Enter).
- ARIA: `role="tablist"/"tab"/"tabpanel"` (Artifacts), `role="status"`+`aria-live="polite"` (run status, capacity), `role="region"` (runs list), labels on icon-only buttons (Kill, Run, Dry Run), step status in `aria-label`.
- No color-only signal anywhere (already mostly true — keep it).

## Round-trip back into the repo (Claude Code)

1. Take Claude Design's exported HTML as the visual reference.
2. Port the visual layer into the Astro components — `DashboardLayout.astro` (shell/nav/footer/type scale/tokens), then per-screen `site/src/pages/app/*` — **without touching** the `fetch`/WS/polling logic or the field names.
3. Add the branded modal component to replace `confirm()`/`alert()` on `facilitator/runs.astro` (and any `alert()` paths).
4. `cd site && npm run build` (verify base path + 404), run an axe/Lighthouse a11y pass, and re-run `uv run pytest` (the API-contract + schema-drift tests must stay green).
