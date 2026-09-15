import process from 'node:process'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The dev server doubles as the everyday way this app is used from a phone.
// Backgrounding the tab (or the phone sleeping) drops Vite's HMR socket, and
// when it reconnects Vite's client answers with a full page reload — so every
// app switch reloaded the page, and any request still in flight (an AI
// extraction, a generated question) was thrown away. DISABLE_HMR=1 turns the
// socket off entirely: no reconnect, no reload, but also no hot updates —
// refresh by hand after editing code.
const hmrDisabled = ['1', 'true'].includes(process.env.DISABLE_HMR?.toLowerCase())

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    allowedHosts: true,
    ...(hmrDisabled && { ws: false }),
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
