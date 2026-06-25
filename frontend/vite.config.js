import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/upload': 'http://localhost:8000',
      '/status': 'http://localhost:8000',
      '/analysis': 'http://localhost:8000',
      '/results': 'http://localhost:8000',
      '/reanalyze': 'http://localhost:8000',
      '/export': 'http://localhost:8000',
      '/columns': 'http://localhost:8000',
    },
  },
})
