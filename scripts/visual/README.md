# Visual QA

`shoot.mjs` takes screenshots with the Google Chrome already on the machine,
over the DevTools protocol. No Playwright, no Puppeteer, no browser download.

```sh
node scripts/visual/shoot.mjs <outdir> <jobs.json>
```

`jobs.json` is a list of `{ url, name, width, height, mobile, full, scale, wait, auth, before, afterWait }`.
`full` scrolls the page first so reveal-on-scroll sections are drawn, then
captures the whole height. `auth` signs in first with `QA_EMAIL` and
`QA_PASSWORD` and sets the session cookies. `ORIGIN` picks the site
(defaults to production).

To look at a change before it ships, run the web app locally against the
production API through the same-origin proxy:

```sh
cd apps/web
NEXT_PUBLIC_API_URL= NOEMA_API_ORIGIN=https://api-production-3ab4.up.railway.app npx next dev -p 3100
ORIGIN=http://localhost:3100 node ../../scripts/visual/shoot.mjs out jobs.json
```

`NEXT_PUBLIC_API_URL=` (empty) matters: without it, development builds call
`http://localhost:8000` directly instead of the proxy.

A full-page capture of the landing shows reveal-on-scroll sections empty on
mobile; that is the capture, not the page. Shoot the viewport at real scroll
positions (`before` with a scroll loop) to judge those.
