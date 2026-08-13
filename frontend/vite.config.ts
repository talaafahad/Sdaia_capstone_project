import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Pinned: the backend's CORS allowlist names :5173 explicitly, so silently
    // falling back to :5174 when the port is busy would break every API call
    // with an opaque CORS error rather than an obvious "port in use".
    port: 5173,
    strictPort: true,
  },
})
