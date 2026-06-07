# Vibe-Trading-KR Wiki

Static source for the **Vibe-Trading-KR** site (the Korean-market fork of
[Vibe-Trading](https://github.com/HKUDS/Vibe-Trading)).

> The original `https://vibetrading.wiki` domain belongs to the upstream project and is **not** served from
> this fork. This site is published to **GitHub Pages** at
> `https://pinehill99.github.io/Vibe-Trading-KR/`.

## Sub-path base

GitHub project Pages serve from a sub-path (`/Vibe-Trading-KR/`), so every internal link, asset, and
script reference is prefixed with `/Vibe-Trading-KR`. The docs single-page app derives this base
automatically from its own module URL (`import.meta.url`), so it keeps working if the repo is renamed or
later moved to a custom domain. If you rename the repo, update the literal `/Vibe-Trading-KR` prefixes in
the HTML (a find-and-replace) — the JavaScript adjusts on its own.

## Local preview

Because paths are prefixed, serve the site so it is reachable under `/Vibe-Trading-KR/`:

```bash
# from the repo root
mkdir -p /tmp/vtkr-preview
ln -snf "$PWD/wiki" /tmp/vtkr-preview/Vibe-Trading-KR
python3 -m http.server 8088 --directory /tmp/vtkr-preview
```

Open `http://localhost:8088/Vibe-Trading-KR/home/` for the landing page, plus
`/docs/`, `/tutorials/`, `/alpha-library/`, `/research-lab/` under the same prefix.

Direct docs URLs such as `/Vibe-Trading-KR/docs/latest/getting-started/vibe-trading-overview` are handled
on GitHub Pages by the `404.html` SPA fallback (generated during deploy). The plain Python server does not
apply that fallback, so use `/docs/` as the local entry point and navigate from there.

## Deploy (GitHub Pages)

Deployment runs from `.github/workflows/pages.yml` and publishes the `wiki/` directory.

One-time setup (fork maintainer):

1. Repo **Settings → Pages → Build and deployment → Source = "GitHub Actions"**.
2. Ensure **Actions** are enabled for the repository.
3. Push any change under `wiki/` to `main` (or run the workflow manually via **Actions → Deploy Wiki to
   GitHub Pages → Run workflow**).

The workflow copies `wiki/docs/index.html` to `wiki/404.html` (SPA fallback for docs deep links), then
uploads and deploys the site. No build step is required — the site is plain static HTML/CSS/JS.

The Cloudflare-only `_redirects` / `_headers` files are kept for an optional Cloudflare Pages deploy but
are ignored by GitHub Pages.
