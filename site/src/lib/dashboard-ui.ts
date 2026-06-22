/**
 * Shared dashboard UI helpers — ported from the Claude Design redesign
 * ("calm instrument panel"). Icons, status/health badges, the branded
 * alertdialog modal, and the live-region announcer. The DashboardLayout
 * provides the required DOM hooks (#modal-root, #announcer); pages import
 * what they need and feed these helpers REAL API data.
 *
 * Status is encoded as shape + glyph + label + hue — never hue alone.
 */

export const esc = (s: unknown): string =>
  String(s ?? '').replace(/[&<>"]/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] as string
  ));

export const elFrom = (html: string): HTMLElement => {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild as HTMLElement;
};

export const fmtElapsed = (s: number): string => {
  s = Math.max(0, Math.round(s));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return m ? `${m}m ${r}s` : `${r}s`;
};

export const fmtClock = (iso: string): string => {
  try { return new Date(iso).toISOString().slice(11, 19) + ' UTC'; } catch { return iso; }
};

export const skeleton = (h: string, w = '100%'): string =>
  `<div class="skeleton" style="height:${h};width:${w}"></div>`;

/* ---------- inline icons (stroke = currentColor) ---------- */
export const icons = {
  dash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>',
  play: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M6 4.5l13 7.5-13 7.5z"/></svg>',
  board: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16M4 12h16M4 19h16"/><circle cx="8" cy="5" r="1.6" fill="currentColor" stroke="none"/><circle cx="15" cy="12" r="1.6" fill="currentColor" stroke="none"/><circle cx="11" cy="19" r="1.6" fill="currentColor" stroke="none"/></svg>',
  seal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 4v5c0 4.4-3 7.6-7 9-4-1.4-7-4.6-7-9V7z"/><path d="M9 12l2 2 4-4"/></svg>',
  book: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z"/><path d="M5 17a3 3 0 0 1 3-3h11"/></svg>',
  doctor: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3v5a4 4 0 0 0 8 0V3"/><path d="M10 16a5 5 0 0 0 10 0v-2"/><circle cx="20" cy="11" r="2"/></svg>',
  wallet: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="6" width="18" height="13" rx="2.5"/><path d="M16 12h2"/><path d="M3 9h13a2 2 0 0 1 0 4"/></svg>',
  net: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.4 2.5 15.6 0 18M12 3c-2.5 2.4-2.5 15.6 0 18"/></svg>',
  clip: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 4v1.5H9z"/><path d="M9 11h6M9 15h4"/></svg>',
  ban: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/></svg>',
  alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l9.5 16.5h-19z"/><path d="M12 9.5v4.5"/><circle cx="12" cy="17.3" r="0.4" fill="currentColor"/></svg>',
  reload: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 12a8.5 8.5 0 0 1 14.5-6l2 2"/><path d="M20 4v4h-4"/><path d="M20.5 12a8.5 8.5 0 0 1-14.5 6l-2-2"/><path d="M4 20v-4h4"/></svg>',
  award: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="9" r="6"/><path d="M9 14.5L7.5 22 12 19.5 16.5 22 15 14.5"/></svg>',
  file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h8l5 5v13H6z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h6"/></svg>',
  inbox: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 13l3-8h12l3 8v6H3z"/><path d="M3 13h5l1.5 2.5h5L16 13h5"/></svg>',
} as const;

/* ---------- status badges (run states) ---------- */
const RUN_BADGE: Record<string, { cls: string; glyph: string; label: string }> = {
  running:   { cls: 'active',    glyph: '',  label: 'ACTIVE' },
  completed: { cls: 'done',      glyph: '✓', label: 'DONE' },
  failed:    { cls: 'failed',    glyph: '✗', label: 'FAILED' },
  cancelled: { cls: 'cancelled', glyph: '⊘', label: 'CANCELLED' },
};

export function runBadge(status: string): string {
  const b = RUN_BADGE[status] || RUN_BADGE.cancelled;
  const glyph = b.cls === 'active'
    ? '<span class="badge__glyph" aria-hidden="true"></span>'
    : `<span class="badge__glyph" aria-hidden="true">${b.glyph}</span>`;
  return `<span class="badge badge--${b.cls}" role="status">${glyph}<span>${b.label}</span></span>`;
}

/* ---------- verify badges (live tx verdicts: PASS | FAIL | SKIPPED) ---------- */
// Reuses the run-state .badge--{done,failed,cancelled} styling so the verify
// page's per-tx table reads with the SAME shape+glyph+label+hue vocabulary as
// the run page's status pills — never hue alone. PASS → done (✓), FAIL →
// failed (✗), SKIPPED → cancelled (⊘, "no on-ledger anchor", not an error).
const VERIFY_BADGE: Record<string, { cls: string; glyph: string; label: string }> = {
  PASS:    { cls: 'done',      glyph: '✓', label: 'PASS' },
  FAIL:    { cls: 'failed',    glyph: '✗', label: 'FAIL' },
  SKIPPED: { cls: 'cancelled', glyph: '⊘', label: 'SKIPPED' },
};

export function verifyBadge(status: string): string {
  const b = VERIFY_BADGE[status] || VERIFY_BADGE.SKIPPED;
  return `<span class="badge badge--${b.cls}" role="status"><span class="badge__glyph" aria-hidden="true">${b.glyph}</span><span>${esc(b.label)}</span></span>`;
}

/* ---------- file download (FT-PROOF-002 — artifact download) ---------- */
/**
 * Serialize an already-fetched object/string to a Blob and trigger a browser
 * download. No backend call — the data is already in the browser. Used by the
 * Artifacts page (proof pack / certificate as application/json, reports as
 * text/markdown) and any future "save this artifact" affordance.
 *
 * `data`  — a string (written verbatim) or any JSON-serializable value
 *           (pretty-printed with 2-space indent, matching the on-disk format
 *           written by reporting.write_proof_pack / write_certificate).
 * `filename` — the suggested download name (e.g. xrpl_lab_proof_pack.json).
 * `mime`  — the Blob type (application/json | text/markdown).
 */
export function downloadFile(
  data: unknown,
  filename: string,
  mime = 'application/json',
): void {
  const text = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  // Append → click → remove is the cross-browser-safe trigger; revoke the
  // object URL after a tick so the download has started before we free it.
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/* ---------- health icon (doctor checks: pass | warn | fail) ---------- */
export function healthIcon(status: string): string {
  const map: Record<string, [string, string, string]> = {
    pass: ['pass', '✓', 'pass'],
    warn: ['warn', '!', 'warning'],
    fail: ['fail', '✕', 'fail'],
  };
  const [cls, g, label] = map[status] || map.warn;
  return `<span class="hicon hicon--${cls}" role="img" aria-label="${label}"><span aria-hidden="true">${g}</span></span>`;
}

/* ============================================================ BRANDED MODAL */

let modalReturn: HTMLElement | null = null;

export interface ModalOpts {
  variant?: 'danger' | 'error' | 'ok';
  icon?: string;
  title: string;
  body: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm?: () => void;
  returnTo?: HTMLElement;
}

/**
 * Open a branded alertdialog modal — the accessible replacement for native
 * confirm()/alert(): focus-trapped, Escape cancels, Enter confirms, backdrop
 * click cancels, focus returns to the trigger on close.
 */
export function openModal(opts: ModalOpts): void {
  const {
    variant = 'danger', icon, title, body,
    confirmLabel = 'Confirm', cancelLabel = 'Cancel', onConfirm, returnTo,
  } = opts;
  closeModal();
  modalReturn = returnTo || (document.activeElement as HTMLElement);
  const root = document.getElementById('modal-root');
  if (!root) return;
  const overlay = elFrom(
    `<div class="modal-overlay"><div class="modal" role="alertdialog" aria-modal="true" aria-labelledby="mTitle" aria-describedby="mBody">
        <div class="modal__ic ${variant === 'ok' ? 'modal__ic--ok' : ''}">${icon || icons.alert}</div>
        <h2 class="modal__title" id="mTitle">${title}</h2>
        <p class="modal__body" id="mBody">${body}</p>
        <div class="modal__actions">
          <button class="btn" data-act="cancel">${esc(cancelLabel)}</button>
          <button class="btn ${variant === 'ok' ? 'btn--primary' : 'btn--danger'}" data-act="confirm">${esc(confirmLabel)}</button>
        </div>
      </div></div>`,
  );
  root.appendChild(overlay);
  const confirmBtn = overlay.querySelector('[data-act="confirm"]') as HTMLButtonElement;
  const cancelBtn = overlay.querySelector('[data-act="cancel"]') as HTMLButtonElement;
  const done = (run: boolean) => { closeModal(); if (run && onConfirm) onConfirm(); };
  confirmBtn.addEventListener('click', () => done(true));
  cancelBtn.addEventListener('click', () => done(false));
  overlay.addEventListener('mousedown', (e) => { if (e.target === overlay) done(false); });
  overlay.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { e.preventDefault(); done(false); }
    else if (e.key === 'Enter') { e.preventDefault(); done(true); }
    else if (e.key === 'Tab') {
      const f = [cancelBtn, confirmBtn];
      const idx = f.indexOf(document.activeElement as HTMLButtonElement);
      e.preventDefault();
      f[(idx + (e.shiftKey ? f.length - 1 : 1)) % f.length].focus();
    }
  });
  requestAnimationFrame(() => confirmBtn.focus());
}

export function closeModal(): void {
  const o = document.querySelector('#modal-root .modal-overlay');
  if (o) o.remove();
  if (modalReturn && modalReturn.focus) { modalReturn.focus(); modalReturn = null; }
}

/** Announce a message to screen readers via the layout's live region. */
export function announce(msg: string): void {
  const a = document.getElementById('announcer');
  if (a) { a.textContent = ''; setTimeout(() => { a.textContent = msg; }, 30); }
}
