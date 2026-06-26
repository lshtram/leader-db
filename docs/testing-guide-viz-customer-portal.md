# Testing guide — visualization customer portal

This runbook is the authoritative operational note for the customer-facing
visualization portal at `https://viz.chopsworkshop.com`.

The portal uses one Cloudflare-protected hostname with path-based routing:

| URL path | Served by | Purpose |
|---|---|---|
| `/superset/` | Superset app container through nginx | Interactive Superset BI UI and dashboards |
| `/reports/` | nginx static files | Customer-facing report landing page |
| `/reports/country-metrics-dashboard.html` | nginx static file | Standalone country metrics dashboard generated ahead of time |
| `/reports/briefs/us-equity-ownership.html` | bind mount from `markets-research` | Static research brief |
| `/reports/briefs/us-market-size-baseline.html` | bind mount from `markets-research` | Static research brief |
| `/visualizations/...` | bind mount from `markets-research` | Pre-rendered PNG graphs used by the briefs |
| `/reports/visualizations/...` | same image bind mount | Compatibility route for alternate relative links |

## Graph generation model

There are two different graph models:

1. **Market-research brief graphs are generated ahead of time.**
   The brief HTML files contain ordinary `<img>` tags such as
   `../../visualizations/us-equity-ownership/05_market_cap_ladder.png`.
   nginx serves those PNG files from the original market-research checkout:

   ```text
   /home/liorshtram/projects/markets-research/reports/visualizations/
   ```

   They are not generated on page load by this repository. Regenerate them in
   the `markets-research` project, then refresh the browser.

2. **`/reports/country-metrics-dashboard.html` is also generated ahead of time,**
   but it is interactive in the browser. Run:

   ```bash
   python scripts/build_static_country_dashboard.py
   ```

   The script reads
   `data/processed/viz/country-year-chronicle/superset_viz.sqlite` and embeds the
   selected metric rows as JSON inside the HTML file. At page-view time the
   browser renders the selector, cards, and SVG charts from that embedded JSON.
   No backend route or Superset API is called for the standalone dashboard.

## Runtime architecture

`infra/superset/docker-compose.yml` starts four relevant services:

- `superset-db`: PostgreSQL metadata database for Superset.
- `superset-redis`: Redis for Superset.
- `superset-app`: Apache Superset itself, listening only inside the compose
  network. It does **not** publish host port `8088` directly. The service is
  intentionally not named `superset`, because the existing Cloudflare tunnel may
  target `http://superset:8088`; that DNS name must resolve to the nginx proxy.
- `superset-proxy`: nginx, published on `127.0.0.1:8088`. This is the only local
  service Cloudflare should target.

nginx config lives at:

```text
infra/superset/nginx-conf/default.conf
```

The proxy mounts:

```text
infra/superset/reports/                                      -> /usr/share/nginx/html/reports
$MARKET_RESEARCH_ROOT/reports/briefs/html                    -> /usr/share/nginx/html/briefs
$MARKET_RESEARCH_ROOT/reports/visualizations                 -> /usr/share/nginx/html/visualizations
```

`MARKET_RESEARCH_ROOT` defaults to:

```text
/home/liorshtram/projects/markets-research
```

Override it in `infra/superset/superset.env` if the checkout is elsewhere.

## Start / restart

Prerequisites:

- `infra/superset/superset.env` exists and contains real secrets copied from
  `infra/superset/superset.env.template`.
- `MARKET_RESEARCH_ROOT` points at a checkout containing:
  - `reports/briefs/html/us-equity-ownership.html`
  - `reports/briefs/html/us-market-size-baseline.html`
  - `reports/visualizations/us-equity-ownership/*.png`
  - `reports/visualizations/us-market-size-baseline/*.png`

Start or restart:

```bash
docker compose --env-file infra/superset/superset.env \
  -f infra/superset/docker-compose.yml up -d
```

If only nginx config or static mounts changed:

```bash
docker compose --env-file infra/superset/superset.env \
  -f infra/superset/docker-compose.yml up -d superset-proxy
```

Do **not** run a separate manual `docker run` proxy unless debugging. The compose
service is the permanent runtime definition.

## Cloudflare configuration

Cloudflare has two layers:

1. **Cloudflare Access application** for `viz.chopsworkshop.com`.
   - Type: Self-hosted.
   - Policy: explicit allowlist of client/operator emails.
   - No broad `Everyone`, domain-wide, or bypass policy.

2. **Cloudflare Tunnel public hostname route**.
   - Hostname: `viz.chopsworkshop.com`.
   - Service type: HTTP.
   - Service URL when `cloudflared` runs in Docker here:

     ```text
     host.docker.internal:8088
     ```

   - Service URL if `cloudflared` runs directly on the host:

     ```text
     localhost:8088
     ```

The committed `infra/cloudflare/docker-compose.yml` runs the token-managed
`cloudflared` container without publishing inbound ports. It includes the Linux
`host.docker.internal` mapping so the tunnel can reach nginx at host port 8088.

Start cloudflared after `infra/cloudflare/cloudflared.env` contains the tunnel
token:

```bash
docker compose --env-file infra/cloudflare/cloudflared.env \
  -f infra/cloudflare/docker-compose.yml up -d
```

## Health check

Run the local report health check:

```bash
python scripts/check_viz_reports.py
```

This verifies:

- `/reports/` returns HTTP 200.
- `/reports/country-metrics-dashboard.html` returns HTTP 200.
- both market-research brief pages return HTTP 200.
- every `<img>` referenced by both brief pages returns HTTP 200 and a non-trivial
  response body.

For a Cloudflare URL check from a session that can already pass Access, run:

```bash
python scripts/check_viz_reports.py https://viz.chopsworkshop.com
```

For browser-level verification use Playwright and inspect image dimensions:

```javascript
await page.goto('https://viz.chopsworkshop.com/reports/briefs/us-equity-ownership.html');
await Promise.all([...document.images].map(img => img.complete ? Promise.resolve() : new Promise(r => { img.onload = img.onerror = r; })));
[...document.images].filter(img => !img.naturalWidth || !img.naturalHeight);
```

The broken-image array must be empty.

## Updating customer content

### Update market-research briefs

Edit or regenerate files in the source project, not in this repository:

```text
/home/liorshtram/projects/markets-research/reports/briefs/html/
/home/liorshtram/projects/markets-research/reports/visualizations/
```

Because nginx bind-mounts those directories read-only, changes in that checkout
are visible through `viz.chopsworkshop.com` after browser cache refresh. The proxy
sends `Cache-Control: no-store, must-revalidate` on report and image routes to
avoid stale 404s during iteration.

### Update the report landing page

Edit:

```text
infra/superset/reports/index.html
```

Then run:

```bash
python scripts/check_viz_reports.py
```

### Update the standalone country metrics dashboard

Rebuild the Superset SQLite artifact first if the underlying data changed:

```bash
leaders-db viz-build-superset-db
```

Then regenerate the static dashboard:

```bash
python scripts/build_static_country_dashboard.py
```

## Troubleshooting

### `/reports/` returns 404

Check that the proxy is running from compose and that the reports directory is
mounted:

```bash
docker compose --env-file infra/superset/superset.env \
  -f infra/superset/docker-compose.yml ps

docker exec superset-superset-proxy-1 ls -lah /usr/share/nginx/html/reports
```

Container names can differ between compose v1 and v2; use `docker ps` if needed.

### Brief pages load but graphs are broken

Check both image routes:

```bash
curl -I http://127.0.0.1:8088/visualizations/us-equity-ownership/05_market_cap_ladder.png
curl -I http://127.0.0.1:8088/reports/visualizations/us-equity-ownership/05_market_cap_ladder.png
```

Both should return `200 OK` and `Content-Type: image/png`.

If not, confirm `MARKET_RESEARCH_ROOT` and the image files exist in the
market-research checkout.

### Superset works locally but Cloudflare shows the wrong route

Confirm Cloudflare Tunnel targets the nginx proxy, not the Superset app:

```text
host.docker.internal:8088  # Docker cloudflared
localhost:8088             # host cloudflared
```

The Superset container itself should not publish `127.0.0.1:8088`; only nginx
should publish that port.
