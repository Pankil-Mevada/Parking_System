import { defineConfig } from 'vite';
export default defineConfig({
  optimizeDeps: { entries: ['index.html'] },
  server: {
    port: 5173, strictPort: true,
    watch: { ignored: ['**/.tools/**', '**/build/**', '**/dist/**'] },
    fs: { deny: ['.env', '.env.*', '*.{crt,pem}', '**/.git/**', '**/.tools/**'] },
    proxy: { '/api': 'http://127.0.0.1:8080' }
  },
  build: { outDir: 'dist' }
});
