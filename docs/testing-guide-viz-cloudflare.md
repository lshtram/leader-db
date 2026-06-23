# Testing guide — visualization Cloudflare client access

This guide covers Visualization Increment 5: exposing the local Superset UI at
`https://viz.chopsworkshop.com` through Cloudflare Tunnel and Cloudflare Access.

## Safety model

Do **not** create the public hostname route until the Cloudflare Access
application and explicit allowlist policy exist. Cloudflare's Access docs state
that Access applications are deny-by-default only after an application/policy is
configured; a tunnel route without Access can expose the origin publicly.

The expected security posture is:

- Superset continues to listen locally on `127.0.0.1:8088`.
- `cloudflared` creates outbound-only connections to Cloudflare; no inbound port
  is opened on this machine.
- `viz.chopsworkshop.com` is protected by a Cloudflare Access self-hosted
  application.
- The Access policy is an explicit email allowlist for the client and internal
  operators.
- Superset itself still requires login; Cloudflare Access is not the only
  authentication layer.
- Superset connects only to the read-only analytic SQLite mount documented in
  `docs/testing-guide-viz-superset.md`.

## Automated repository checks

Run:

```bash
.venv/bin/pytest tests/test_viz_cloudflare_templates.py -q
```

What this verifies:

- Cloudflare secret-bearing files are ignored.
- The committed tunnel template targets `viz.chopsworkshop.com` and includes the
  required catch-all `http_status:404` ingress rule.
- The Docker Compose template does not publish inbound ports and requires a
  `TUNNEL_TOKEN` supplied from the ignored env file.

## Manual activation checklist

Prerequisites:

- `viz.chopsworkshop.com` is in the `chopsworkshop.com` Cloudflare zone.
- Superset is already running locally per `docs/testing-guide-viz-superset.md`.
- `leaders-db viz-build-superset-db` has refreshed the read-only analytic SQLite
  artifact.
- You have the final client/internal email allowlist.

### 1. Create the Access application first

In Cloudflare Zero Trust:

1. Go to **Access controls → Applications**.
2. Create a **Self-hosted** application.
3. Public hostname/domain: `viz.chopsworkshop.com`.
4. Add an **Allow** policy with explicit emails only.
5. Confirm there is no broad `Everyone`, domain-wide, or bypass policy.

### 2. Create the tunnel and public hostname route

In Cloudflare Zero Trust:

1. Go to **Networks → Tunnels**.
2. Create a tunnel for this host.
3. Add a public hostname route:

   | Field | Value |
   |---|---|
   | Hostname | `viz.chopsworkshop.com` |
   | Service type | HTTP |
   | Service URL | `host.docker.internal:8088` for Docker cloudflared, or `localhost:8088` for host cloudflared |

4. Enable Cloudflare Access protection / token validation for the hostname when
   available in the tunnel settings.
5. Copy the tunnel token.

### 3. Start cloudflared locally

```bash
cp infra/cloudflare/cloudflared.env.template infra/cloudflare/cloudflared.env
$EDITOR infra/cloudflare/cloudflared.env  # paste TUNNEL_TOKEN only

docker compose --env-file infra/cloudflare/cloudflared.env \
  -f infra/cloudflare/docker-compose.yml up -d
```

If your host only has legacy `docker-compose`, run the equivalent command after
exporting `TUNNEL_TOKEN` in your shell or using the legacy compose env-file
syntax supported on that host.

### 4. Verify from a non-allowlisted browser/session

Expected result:

- `https://viz.chopsworkshop.com` shows Cloudflare Access login/denial.
- It must not show the Superset login page directly.

### 5. Verify from an allowlisted client account

Expected result:

1. `https://viz.chopsworkshop.com` prompts through Cloudflare Access.
2. After Access succeeds, Superset login appears.
3. Superset login succeeds using a non-default Superset account.
4. The Superset database is the read-only SQLite URI:
   `sqlite:////leaders-db-viz/superset_viz.sqlite`.
5. The first dashboard charts load.

### 6. Shutdown

```bash
docker compose --env-file infra/cloudflare/cloudflared.env \
  -f infra/cloudflare/docker-compose.yml down
```

## Rollback

If anything looks public or misconfigured:

1. Stop `cloudflared` locally.
2. Remove the tunnel public hostname route.
3. Disable or delete the Access application.
4. Rotate the tunnel token if it may have been exposed.

## References checked during setup

- Cloudflare self-hosted application docs: create Access application/policy and
  publish via tunnel; Access applications require an allow policy before users
  are granted access.
- Cloudflare Tunnel setup docs: public hostname route maps a hostname to a local
  service; tunnel ingress requires a final catch-all rule such as
  `http_status:404` for local-managed configs.
