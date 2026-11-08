import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dev server proxies /api to the FastAPI backend, so no CORS setup is needed.
// host: true exposes the site on the local network so friends can open it.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
