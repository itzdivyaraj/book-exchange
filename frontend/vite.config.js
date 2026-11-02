// Vite = the tool that runs the site while you develop (npm run dev)
// and bundles it into plain HTML/JS/CSS files for Vercel (npm run build).
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173 },
})
