import fs from 'node:fs'
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  // Slack requires an https redirect, so dev runs on https (`make certs`) and proxies /api
  server: {
    port: 3000,
    strictPort: true,
    https: {
      cert: fs.readFileSync('.certs/localhost.pem'),
      key: fs.readFileSync('.certs/localhost-key.pem'),
    },
    proxy: { '/api': process.env.API_URL ?? 'http://localhost:8000' },
  },
})
