import { createReadStream, existsSync, statSync } from 'node:fs'
import { resolve, sep } from 'node:path'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, type Plugin } from 'vite'

const RUNS_DIR = resolve(import.meta.dirname, '../runs')

// Serves the repo's runs/ folder at /runs, so the dashboard can read
// runs/<id>/events.jsonl before A's API exists.
function serveRuns(): Plugin {
  return {
    name: 'serve-runs',
    configureServer(server) {
      server.middlewares.use('/runs', (req, res, next) => {
        const file = resolve(RUNS_DIR, '.' + decodeURIComponent(req.url ?? '/').split('?')[0])
        if (!file.startsWith(RUNS_DIR + sep) || !existsSync(file) || !statSync(file).isFile()) return next()
        res.setHeader('Content-Type', 'application/x-ndjson; charset=utf-8')
        createReadStream(file).pipe(res)
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), serveRuns()],
})
