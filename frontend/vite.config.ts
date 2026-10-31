import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The backend (uv run uvicorn backend.main:app --port 8000) serves everything under /api.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { '/api': 'http://localhost:8000' } },
  // Pre-bundle pdf.js and its viewer together so they always share one copy of the library.
  optimizeDeps: { include: ['pdfjs-dist', 'pdfjs-dist/web/pdf_viewer.mjs'] },
})
