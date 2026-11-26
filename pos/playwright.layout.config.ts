import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/layout',
  testMatch: '**/*.spec.ts',
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: 'http://127.0.0.1:4178', browserName: 'chromium', screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: { command: 'yarn vite --config tests/layout/vite.config.ts --host 127.0.0.1 --port 4178 --strictPort', url: 'http://127.0.0.1:4178/tests/layout/index.html', reuseExistingServer: !process.env.CI },
});
