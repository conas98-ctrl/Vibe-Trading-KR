# Vibe-Trading-KR Wiki

Static source for the **Vibe-Trading-KR** site (the Korean-market fork of
[Vibe-Trading](https://github.com/HKUDS/Vibe-Trading)).

> The original `https://vibetrading.wiki` domain belongs to the upstream project and is **not** served from
> this fork. To publish this Korean-branded site, deploy this `wiki/` directory to your own Cloudflare Pages
> project (see below).

## Local preview

```bash
cd wiki
python3 -m http.server 8088
```

Open `http://localhost:8088/home/` for the landing page and these wiki sections:

- `http://localhost:8088/docs/`
- `http://localhost:8088/tutorials/`
- `http://localhost:8088/alpha-library/`
- `http://localhost:8088/research-lab/`

Direct docs URLs such as `/docs/latest/getting-started/vibe-trading-overview` are handled by Cloudflare Pages via `_redirects`. The simple Python preview server does not apply those rewrite rules, so use `/docs/` as the local entry point.

## Cloudflare Pages

- Project root: `wiki`
- Build command: leave empty
- Output directory: `.`
- Project name: `vibe-trading-kr-wiki` (must match `--project-name` in `.github/workflows/wiki-deploy.yml`)
- Custom domain: optional — otherwise the site is served at `https://vibe-trading-kr-wiki.pages.dev`

The site is intentionally static. No server, database, or build step is required. Internal links are
absolute (`/home/`, `/assets/...`), so it must be served from the domain root (Cloudflare Pages or a
custom domain), not from a sub-path.

## Enable automatic deploys (fork maintainer)

`Deploy Wiki` (`.github/workflows/wiki-deploy.yml`) is **opt-in** and stays disabled until you turn it on,
so CI is green by default. To publish on every push to `main` that touches `wiki/`:

1. Create a **Cloudflare Pages** project named `vibe-trading-kr-wiki` (direct/Wrangler upload, no Git build).
2. In this repo, add **Actions secrets**: `CLOUDFLARE_API_TOKEN` (Pages-edit scope) and `CLOUDFLARE_ACCOUNT_ID`.
3. Add an **Actions variable** `DEPLOY_WIKI` set to `true`.
4. Push a change under `wiki/` (or re-run the workflow). The action runs `wrangler pages deploy wiki`.

To deploy once by hand instead:

```bash
npx wrangler pages deploy wiki --project-name=vibe-trading-kr-wiki
```
