import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 開發時 /api 轉給本機後端；正式環境由 nginx 轉。
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': { target: 'http://localhost:8000', rewrite: p => p.replace(/^\/api/, '') } } },
})
