/**
 * Pin Artifacts panels to live generate_proof_pack / generate_certificate keys
 * (F-db854b39 / Advisor F-a07efac7). Stale modules/generated/integrity/holder
 * must not drive the empty-state or under-render path.
 */
import { describe, expect, it } from 'vitest';
import { renderCertPanel, renderProofPanel, VERIFY_HREF } from './artifacts-panels';

/** Shape mirrored from xrpl_lab.reporting.generate_proof_pack */
const LIVE_PROOF = {
  xrpl_lab_proof_pack: true,
  version: '2.4.0',
  network: 'testnet',
  endpoint: 'https://s.altnet.rippletest.net:51234',
  address: 'rExampleWallet1111111111111111111',
  generated_at: '2026-08-25T12:00:00+00:00',
  completed_modules: [
    {
      module_id: 'trust_lines_101',
      completed_at: '2026-08-25T11:00:00+00:00',
      txids: ['ABCDEF0123456789'],
      verified: true,
      kb_source: '',
      explorer_urls: [],
    },
  ],
  capstone: false,
  all_verified: true,
  transactions: [],
  receipt_table: [],
  total_transactions: 1,
  successful_transactions: 1,
  failed_transactions: 0,
  sha256: 'deadbeefcafebabe0123456789abcdef0123456789abcdef0123456789abcdef',
};

/** Shape mirrored from xrpl_lab.reporting.generate_certificate */
const LIVE_CERT = {
  xrpl_lab_certificate: true,
  version: '2.4.0',
  network: 'testnet',
  address: 'rExampleWallet1111111111111111111',
  generated_at: '2026-08-25T12:00:00+00:00',
  modules_completed: ['trust_lines_101'],
  module_titles: { trust_lines_101: 'Trust Lines 101' },
  total_modules: 1,
  total_transactions: 1,
  successful_transactions: 1,
  summary_line: 'Completed 1 module with 1 transaction.',
  sha256: 'cafebabedeadbeef0123456789abcdef0123456789abcdef0123456789abcdef',
};

describe('renderProofPanel — live generate_proof_pack keys', () => {
  it('renders completed_modules / generated_at / sha256 (not modules/generated/integrity)', () => {
    const html = renderProofPanel(LIVE_PROOF);
    expect(html).not.toContain('No proof pack yet');
    expect(html).not.toContain('No modules recorded in this proof pack');
    expect(html).toContain('trust_lines_101');
    expect(html).toContain('deadbeefcafebabe');
    expect(html).toContain('Integrity · SHA-256');
    // Must not require the stale field names to show content
    expect(html).not.toMatch(/\bundefined\b/);
  });

  it('surfaces all_verified === false as UNVERIFIED', () => {
    const html = renderProofPanel({ ...LIVE_PROOF, all_verified: false });
    expect(html).toContain('UNVERIFIED');
  });

  it('includes Verify handoff link', () => {
    const html = renderProofPanel(LIVE_PROOF);
    expect(html).toContain(VERIFY_HREF);
  });

  it('does not treat a live pack as empty when only stale keys are missing', () => {
    const html = renderProofPanel(LIVE_PROOF);
    expect(html).toContain('Proof pack · v2.4.0');
  });
});

describe('renderCertPanel — live generate_certificate keys', () => {
  it('renders address / generated_at / sha256 (not holder/issued/hash)', () => {
    const html = renderCertPanel(LIVE_CERT);
    expect(html).not.toContain('No certificate yet');
    expect(html).toContain('rExampleWallet1111111111111111111');
    expect(html).toContain('trust_lines_101');
    expect(html).toContain('cafebabedeadbeef');
  });

  it('includes Verify handoff link', () => {
    const html = renderCertPanel(LIVE_CERT);
    expect(html).toContain(VERIFY_HREF);
  });

  it('empty-states only when there is no live certificate marker/address', () => {
    expect(renderCertPanel(null)).toContain('No certificate yet');
    expect(renderCertPanel({})).toContain('No certificate yet');
  });
});
