import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// Em desenvolvimento, as chamadas /api vão para o backend Python (porta 8000).
// 127.0.0.1 e não "localhost": em alguns Windows "localhost" vira o IPv6 ::1, e o backend
// (--host 0.0.0.0) só escuta em IPv4 -> erro "connect ECONNREFUSED ::1:8000".
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
