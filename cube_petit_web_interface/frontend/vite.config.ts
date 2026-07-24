import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    host: true,
    // Leading-dot entries match any hostname ending in that suffix, so this
    // covers every individual (cube-petit-orange.local, cube-petit-pink.local,
    // ...) without hardcoding one robot's name into a shared source tree.
    allowedHosts: ['.local'],
  },
})
