/**
 * Single source of truth for module IDs at BUILD time.
 *
 * FRONTEND-A-001: the static routes (`/app/modules/[id]` and `/app/run/[id]`)
 * must pre-render one page per curriculum module so they don't 404 on GitHub
 * Pages. Previously each route hardcoded the list of 12 IDs, so the four
 * v1.8.0 modules (nft_minting_101, mpt_issuance_101, escrow_101, did_101)
 * were never built. Now BOTH routes derive their IDs from the repo-root
 * `modules/` directory — the same place the backend reads — so the page set
 * can never drift from the curriculum again.
 *
 * Each `modules/<id>.md` file's basename (sans `.md`) is the module ID, which
 * matches the backend's loader. Runs at build time only (Node frontmatter /
 * getStaticPaths), so the synchronous fs read is safe and never ships to the
 * client.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

/** Read every module ID from the repo-root `modules/` directory, sorted. */
export function getModuleIds(): string[] {
  // Resolve relative to THIS file, not process.cwd(), so the path is stable
  // regardless of where `astro build` is invoked from. This file lives at
  // site/src/lib/, so the repo-root modules/ dir is three levels up.
  const here = path.dirname(fileURLToPath(import.meta.url));
  const modulesDir = path.resolve(here, '../../../modules');
  return fs
    .readdirSync(modulesDir)
    .filter((f) => f.endsWith('.md'))
    .map((f) => f.slice(0, -'.md'.length))
    .sort();
}
