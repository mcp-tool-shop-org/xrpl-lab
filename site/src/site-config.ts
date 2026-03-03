import type { SiteConfig } from '@mcptoolshop/site-theme';

export const config: SiteConfig = {
  title: 'XRPL Lab',
  description: 'XRPL training workbook — learn by doing, prove by artifact',
  logoBadge: 'XL',
  brandName: 'XRPL Lab',
  repoUrl: 'https://github.com/mcp-tool-shop-org/xrpl-lab',
  footerText: 'MIT Licensed — built by <a href="https://mcp-tool-shop.github.io/" style="color:var(--color-muted);text-decoration:underline">MCP Tool Shop</a>',

  hero: {
    badge: 'Open source',
    headline: 'XRPL Lab',
    headlineAccent: 'learn by doing.',
    description: 'CLI training workbook for the XRP Ledger. 12 hands-on modules — each one teaches a skill and produces a verifiable artifact. No accounts, no fluff.',
    primaryCta: { href: '#usage', label: 'Get started' },
    secondaryCta: { href: '#modules', label: 'See modules' },
    previews: [
      { label: 'Install', code: 'pipx install xrpl-lab' },
      { label: 'Start', code: 'xrpl-lab start' },
      { label: 'Offline', code: 'xrpl-lab start --dry-run' },
    ],
  },

  sections: [
    {
      kind: 'features',
      id: 'features',
      title: 'Why XRPL Lab',
      subtitle: 'Real skills, real receipts.',
      features: [
        { title: 'Artifact-driven', desc: 'Every module produces a verifiable artifact — transaction IDs, audit packs, proof packs with SHA-256 integrity.' },
        { title: 'Offline-first', desc: 'Full dry-run mode with simulated transactions. Learn the workflow without touching the network.' },
        { title: '228 tests', desc: 'Deterministic test suite covers every module, action, and transport path. Strategy track included.' },
      ],
    },
    {
      kind: 'data-table',
      id: 'modules',
      title: 'Modules',
      subtitle: '12 modules across three tracks.',
      columns: ['Module', 'Track', 'What you prove'],
      rows: [
        ['Receipt Literacy', 'Beginner', 'txid + verification report'],
        ['Failure Literacy', 'Beginner', 'failed + fixed txid trail'],
        ['Trust Lines 101', 'Beginner', 'trust line + token balance'],
        ['Debugging Trust Lines', 'Beginner', 'error → fix txid trail'],
        ['DEX Literacy', 'Intermediate', 'offer create + cancel txids'],
        ['Reserves 101', 'Intermediate', 'before/after snapshot delta'],
        ['Account Hygiene', 'Intermediate', 'cleanup verification report'],
        ['Receipt Audit', 'Intermediate', 'audit pack (MD + CSV + JSON)'],
        ['AMM Liquidity 101', 'Advanced', 'AMM lifecycle txids'],
        ['DEX Market Making 101', 'Advanced', 'strategy txids + hygiene report'],
        ['Inventory Guardrails', 'Advanced', 'inventory check + guarded txids'],
        ['DEX vs AMM Risk Literacy', 'Advanced', 'comparison report + audit trail'],
      ],
    },
    {
      kind: 'code-cards',
      id: 'usage',
      title: 'Usage',
      cards: [
        { title: 'Install', code: 'pipx install xrpl-lab' },
        { title: 'Start learning', code: 'xrpl-lab start\n# or offline:\nxrpl-lab start --dry-run' },
        { title: 'Run a module', code: 'xrpl-lab run receipt_literacy' },
        { title: 'Verify your work', code: 'xrpl-lab audit --txids .xrpl-lab/last_run_txids.txt \\\n  --expect presets/strategy_mm101.json' },
      ],
    },
    {
      kind: 'features',
      id: 'artifacts',
      title: 'Artifacts',
      subtitle: 'What you walk away with.',
      features: [
        { title: 'Proof packs', desc: 'Shareable JSON with completed modules, transaction IDs, and explorer links. SHA-256 integrity hash. No secrets.' },
        { title: 'Audit packs', desc: 'Batch verification results in Markdown, CSV, and JSON. Expectation configs for type, memo, and result code checks.' },
        { title: 'Certificates', desc: 'Slim completion records. Soft-linked to XRPL Camp for ecosystem integration.' },
      ],
    },
  ],
};
