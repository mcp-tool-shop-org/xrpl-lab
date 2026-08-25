/**
 * Importable Artifacts proof/cert panel renderers.
 * Aligned to live generate_proof_pack / generate_certificate JSON
 * (F-db854b39 / Advisor F-a07efac7): completed_modules / generated_at /
 * sha256 / all_verified / address — not stale modules/generated/integrity/holder.
 */
import { esc, healthIcon, icons } from './dashboard-ui';
import type { Certificate, ProofModule, ProofPack } from './api';

const II = (svg: string) =>
  `<span style="display:inline-flex;width:16px;height:16px;color:var(--text-3)">${svg}</span>`;

export const VERIFY_HREF = '/xrpl-lab/app/verify/';

export function emptyArtifactHTML(icon: string, title: string, help: string): string {
  return `<div class="empty"><span class="empty__ic">${icon}</span>
    <div class="empty__t">${title}</div><div>${help}</div></div>`;
}

function hashboxHTML(hash: string): string {
  return `<div class="row" style="gap:10px;align-items:flex-start">
    <div class="hashbox" style="flex:1">${esc(hash)}</div>
    <button class="btn btn--sm copy-hash" type="button" data-hash="${esc(hash)}" style="flex:none">
      ${II(icons.clip)}<span>Copy</span></button>
  </div>`;
}

function verifyHandoffHTML(): string {
  return `<p style="margin-top:18px"><a class="btn btn--sm" href="${VERIFY_HREF}">${II(icons.seal)}<span>Verify on Verify page</span></a></p>`;
}

function unverifiedBannerHTML(): string {
  return `<div class="row" style="gap:10px;align-items:flex-start;margin-top:14px;padding:12px 14px;border:1px solid var(--warn-edge);border-radius:8px;background:var(--warn-fill)">
    <strong style="color:var(--warn-bright)">⚠ UNVERIFIED</strong>
    <div class="muted" style="font-size:13px">One or more completed modules failed their on-ledger verification. Integrity still passes (the file is intact), but not every lesson was proven — re-run the affected module(s) for a fully-verified pack.</div>
  </div>`;
}

/** True when the payload looks like a live generate_proof_pack object. */
export function isLiveProofPack(p: unknown): p is ProofPack {
  if (!p || typeof p !== 'object') return false;
  const o = p as Record<string, unknown>;
  return o.xrpl_lab_proof_pack === true
    || (typeof o.version === 'string' && Array.isArray(o.completed_modules));
}

/** True when the payload looks like a live generate_certificate object. */
export function isLiveCertificate(c: unknown): c is Certificate {
  if (!c || typeof c !== 'object') return false;
  const o = c as Record<string, unknown>;
  return o.xrpl_lab_certificate === true
    || (typeof o.version === 'string' && typeof o.address === 'string');
}

export function renderProofPanel(
  p: ProofPack | null | undefined,
  opts: { downloadBtnHtml?: string } = {},
): string {
  if (!isLiveProofPack(p)) {
    return emptyArtifactHTML(icons.seal, 'No proof pack yet',
      'Complete modules to generate a verifiable proof pack.');
  }
  const modules: ProofModule[] = Array.isArray(p.completed_modules) ? p.completed_modules : [];
  const generated = p.generated_at ? new Date(p.generated_at).toLocaleString() : 'unknown';
  const dl = opts.downloadBtnHtml ?? '';

  const integrity = p.sha256
    ? `<p class="eyebrow" style="margin-top:18px">Integrity · SHA-256</p>${hashboxHTML(p.sha256)}`
    : '';

  const unverified = p.all_verified === false ? unverifiedBannerHTML() : '';

  const mods = modules.length
    ? `<p class="eyebrow" style="margin-top:18px">Modules</p>${modules.map((m) => {
        const txCount = Array.isArray(m.txids) ? m.txids.length : 0;
        const ok = m.verified !== false;
        return `<div class="proofmod">${healthIcon(ok ? 'pass' : 'warn')}
          <span class="proofmod__id">${esc(m.module_id)}</span>
          <span class="proofmod__tx">${txCount} tx${txCount === 1 ? '' : 's'}</span></div>`;
      }).join('')}`
    : `<p class="muted" style="margin-top:18px">No modules recorded in this proof pack.</p>`;

  const addressRow = p.address
    ? `<dt>${II(icons.wallet)} Address</dt><dd class="mono">${esc(p.address)}</dd>`
    : '';
  const networkRow = p.network
    ? `<dt>Network</dt><dd class="mono">${esc(p.network)}</dd>`
    : '';

  return `<div class="row" style="justify-content:space-between;align-items:flex-start;gap:12px">
      <p class="eyebrow" style="margin:0">Proof pack · v${esc(p.version)}</p>
      ${dl}
    </div>
    ${unverified}
    <dl class="kv" style="margin-top:12px">
      <dt>Generated</dt><dd class="mono">${esc(generated)}</dd>
      ${addressRow}
      ${networkRow}
    </dl>
    ${integrity}
    ${mods}
    ${verifyHandoffHTML()}`;
}

export function renderCertPanel(
  c: Certificate | null | undefined,
  opts: { downloadBtnHtml?: string } = {},
): string {
  if (!isLiveCertificate(c)) {
    return emptyArtifactHTML(icons.award, 'No certificate yet',
      'Finish the workbook to earn a completion certificate.');
  }
  const generated = c.generated_at ? new Date(c.generated_at).toLocaleString() : 'unknown';
  const mods = Array.isArray(c.modules_completed) ? c.modules_completed : [];
  const chips = mods.length
    ? mods.map((m) => `<span class="chip">${esc(m)}</span>`).join(' ')
    : '<span class="muted">none</span>';
  const dl = opts.downloadBtnHtml ?? '';

  const hashbox = c.sha256
    ? `<p class="eyebrow" style="margin-top:18px">Certificate hash</p>${hashboxHTML(c.sha256)}`
    : '';

  return `<div class="row" style="justify-content:space-between;align-items:flex-start;gap:12px">
      <p class="eyebrow" style="margin:0">Certificate of completion</p>
      ${dl}
    </div>
    <dl class="kv" style="margin-top:12px">
      <dt>${II(icons.award)} Address</dt><dd class="mono">${esc(c.address)}</dd>
      <dt>Issued</dt><dd class="mono">${esc(generated)}</dd>
      <dt>Modules completed</dt><dd>${chips}</dd>
      ${c.network ? `<dt>Network</dt><dd class="mono">${esc(c.network)}</dd>` : ''}
    </dl>
    ${hashbox}
    ${verifyHandoffHTML()}`;
}
