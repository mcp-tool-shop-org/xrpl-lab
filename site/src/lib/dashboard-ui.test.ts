/**
 * Phase 7 wave 2 — first executable coverage for dashboard-ui.ts
 * (F-162ff030 / Advisor F-cdf586bf). Scope: esc, openModal, runBadge only.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { esc, openModal, closeModal, runBadge } from './dashboard-ui';

describe('esc', () => {
  it('escapes &, <, >, ", and \' for attribute-safe HTML', () => {
    expect(esc(`a&b<c>d"e'f`)).toBe('a&amp;b&lt;c&gt;d&quot;e&#39;f');
  });

  it('coerces nullish to empty string', () => {
    expect(esc(null)).toBe('');
    expect(esc(undefined)).toBe('');
  });

  it('stringifies non-strings', () => {
    expect(esc(42)).toBe('42');
  });
});

describe('runBadge', () => {
  it('renders ACTIVE for running', () => {
    const html = runBadge('running');
    expect(html).toContain('badge--active');
    expect(html).toContain('ACTIVE');
    expect(html).toContain('role="status"');
  });

  it('renders DONE for completed', () => {
    const html = runBadge('completed');
    expect(html).toContain('badge--done');
    expect(html).toContain('DONE');
    expect(html).toContain('✓');
  });

  it('renders FAILED for failed', () => {
    const html = runBadge('failed');
    expect(html).toContain('badge--failed');
    expect(html).toContain('FAILED');
    expect(html).toContain('✗');
  });

  it('falls back to CANCELLED for unknown status', () => {
    const html = runBadge('weird');
    expect(html).toContain('badge--cancelled');
    expect(html).toContain('CANCELLED');
  });
});

describe('openModal', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="modal-root"></div>';
    closeModal();
  });

  it('mounts an alertdialog with escaped title and body', () => {
    openModal({
      title: 'Delete <module>',
      body: 'Really remove "x" & \'y\'?',
      confirmLabel: 'Yes',
      cancelLabel: 'No',
    });
    const dialog = document.querySelector('#modal-root [role="alertdialog"]');
    expect(dialog).toBeTruthy();
    expect(dialog?.getAttribute('aria-modal')).toBe('true');
    const title = document.getElementById('mTitle');
    // < must stay escaped in the DOM so a title cannot inject markup.
    expect(title?.innerHTML).toBe('Delete &lt;module&gt;');
    expect(title?.textContent).toBe('Delete <module>');
    const body = document.getElementById('mBody');
    // jsdom decodes &quot;/&#39; in text nodes; assert visible text + no child tags.
    expect(body?.textContent).toBe('Really remove "x" & \'y\'?');
    expect(body?.children.length).toBe(0);
    expect(document.querySelector('[data-act="confirm"]')?.textContent).toBe('Yes');
    expect(document.querySelector('[data-act="cancel"]')?.textContent).toBe('No');
  });

  it('calls onConfirm when confirm is clicked', () => {
    const onConfirm = vi.fn();
    openModal({ title: 'Go', body: 'ok', onConfirm });
    (document.querySelector('[data-act="confirm"]') as HTMLButtonElement).click();
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(document.querySelector('#modal-root .modal-overlay')).toBeNull();
  });

  it('does not call onConfirm when cancel is clicked', () => {
    const onConfirm = vi.fn();
    openModal({ title: 'Go', body: 'ok', onConfirm });
    (document.querySelector('[data-act="cancel"]') as HTMLButtonElement).click();
    expect(onConfirm).not.toHaveBeenCalled();
    expect(document.querySelector('#modal-root .modal-overlay')).toBeNull();
  });
});
