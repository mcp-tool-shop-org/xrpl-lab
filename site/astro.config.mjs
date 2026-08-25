// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  site: 'https://mcp-tool-shop-org.github.io',
  base: '/xrpl-lab',
  integrations: [
    starlight({
      title: 'XRPL Lab',
      description: 'XRPL Lab handbook',
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/mcp-tool-shop-org/xrpl-lab' },
      ],
      sidebar: [
        {
          label: 'Handbook',
          autogenerate: { directory: 'handbook' },
        },
      ],
      customCss: ['./src/styles/starlight-custom.css'],
      disable404Route: true,
    }),
  ],
  vite: {
    plugins: [tailwindcss()],
    // Vitest picks this up via Vite (F-162ff030) — no separate vitest.config.
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.ts'],
    },
  },
});
