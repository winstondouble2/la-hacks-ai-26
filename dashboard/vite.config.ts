import { createReadStream, existsSync, statSync } from 'node:fs'
import { resolve, sep } from 'node:path'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, type Plugin } from 'vite'

// Serves a repo folder (runs/, programs/) at /<name>, so the dashboard can read
// runs/<id>/events.jsonl and programs/<name>/v<N>.yaml before A's API exists.
function serveRepoDir(name: string, contentType: string): Plugin {
  const dir = resolve(import.meta.dirname, '..', name)
  return {
    name: `serve-${name}`,
    configureServer(server) {
      server.middlewares.use(`/${name}`, (req, res, next) => {
        const file = resolve(dir, '.' + decodeURIComponent(req.url ?? '/').split('?')[0])
        if (!file.startsWith(dir + sep) || !existsSync(file) || !statSync(file).isFile()) return next()
        res.setHeader('Content-Type', `${contentType}; charset=utf-8`)
        createReadStream(file).pipe(res)
      })
    },
  }
}

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    serveRepoDir('runs', 'application/x-ndjson'),
    serveRepoDir('programs', 'text/yaml'),
  ],
})
