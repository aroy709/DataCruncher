import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/upload':    { target: 'http://127.0.0.1:8000', changeOrigin: true, secure: false },
      '/status':    { target: 'http://127.0.0.1:8000', changeOrigin: true, secure: false },
      '/analysis':  { target: 'http://127.0.0.1:8000', changeOrigin: true, secure: false },
      '/results':   { target: 'http://127.0.0.1:8000', changeOrigin: true, secure: false },
      '/reanalyze': { target: 'http://127.0.0.1:8000', changeOrigin: true, secure: false },
      '/export':    { target: 'http://127.0.0.1:8000', changeOrigin: true, secure: false },
      '/columns':   { target: 'http://127.0.0.1:8000', changeOrigin: true, secure: false },
    },
  },
})
