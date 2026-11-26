import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
const fixture = (name: string) => fileURLToPath(new URL(name, import.meta.url));
export default defineConfig({
  plugins: [react()],
  optimizeDeps: { entries: ['tests/layout/index.html'] },
  resolve: { dedupe: ['react', 'react-dom'], alias: [
    { find: /^@ury\/ui$/, replacement: fixture('./ui.ts') },
    { find: /\.\.\/store\/pos-store$/, replacement: fixture('./store.ts') },
    { find: /\.\.\/i18n$/, replacement: fixture('./i18n.ts') },
    { find: /^\.\/CommentDialog$/, replacement: fixture('./CommentDialog.tsx') },
    { find: /\.\.\/lib\/category-icons$/, replacement: fixture('./icons.tsx') },
  ]},
  server: { fs: { allow: ['..'] } },
});
