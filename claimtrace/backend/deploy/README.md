# Backend deployment preparation

This is a **single-instance backend** deployment for local rehearsal and a future
Linux host. It builds Parser, Engine and Backend together; there is no frontend
service. The existing development Dockerfile and root Compose are unchanged.

The current JSON stores and locks require **one Uvicorn worker and one backend
container**. Do not scale this Compose service or share its data volume between
running instances. Database migration and multi-user authentication are separate
work. The API currently exposes a shared library; this configuration binds the
host port to loopback and is not a public multi-user launch configuration.

## Prerequisites and first start

- A running Linux Docker engine (Docker Desktop's Linux engine on Windows).
- Docker Compose v2 and network access during the image build.
- Python 3.11+ on the host only if running the acceptance script.
- Initial resource budget to test: 2 CPU cores, 4 GiB RAM, 10 GiB free disk.
  This is a planning estimate, not a measured capacity or concurrency guarantee.
  Record actual usage with `docker stats` before buying a host.

Run the following from the repository's `claimtrace/` directory. In PowerShell,
use `Copy-Item` for the first command instead of `cp` if preferred.

```sh
cp backend/deploy/.env.example backend/deploy/.env
docker compose --env-file backend/deploy/.env -f backend/deploy/compose.yaml config --quiet
docker compose --env-file backend/deploy/.env -f backend/deploy/compose.yaml build backend
docker compose --env-file backend/deploy/.env -f backend/deploy/compose.yaml up -d --no-build backend
docker compose --env-file backend/deploy/.env -f backend/deploy/compose.yaml ps
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

On Windows use `curl.exe` to avoid the older PowerShell curl alias. API docs are
at `http://127.0.0.1:8000/docs`. Edit `BACKEND_PORT` and `CORS_ORIGINS` in the deploy
`.env` to suit the environment. Compose reads this file for interpolation only;
the application explicitly opts out of discovering a developer's `.env`.

The production image uses Python 3.11, Java 17, CPU-only PyTorch, a non-root UID
10001, a read-only root filesystem, and a writable temporary filesystem. The
entrypoint checks local prerequisites and launches one worker without reload or
HTTP access logs. Docker rotates container logs at 10 MB with three files.
The container contains a resolved dependency snapshot at
`/opt/venv/installed-packages.txt`. The embedding stack is constrained in
`constraints.txt`; the entire transitive dependency graph and base image digest
are **not locked**. For an actual release, build once, tag the resulting image
with the Git commit, and retain that image/digest for updates and rollback.

## Readiness and paid AI

`/health` preserves its existing lightweight response. `/ready` returns 200 when
Java 11+, required package discovery and write probes pass; otherwise 503. The
response includes only boolean checks, not paths or credentials. The preflight
creates data/cache directories; readiness itself does not create them.

Neither check downloads a model, parses a PDF, queries publication databases or
calls an LLM. Package discovery does not prove that every native library loads;
the acceptance run below exercises real parsing. Embedding model availability
and actual inference require the optional warm-up below.

Compose explicitly supplies empty AI keys, so host/team environment variables
are not forwarded. This branch does not change the AI pipeline. Until Hongyang's
BYOK change is integrated, semantic citation verification reports its existing
unconfigured state, and reference enrichment uses its existing parser fallback.
Do not add team credentials just to make deployment checks pass.

## Data and model cache

| Volume | Container location | Contents |
| --- | --- | --- |
| `data` | `/data` | `uploads/papers.json`, uploaded PDF/Bib files, Verify-only sources, parsed JSON/Markdown, references, audits, deletion journals |
| `model-cache` | `/cache` | Hugging Face model cache; rebuildable and not included in the data backup |

Compose prefixes volume names with its project name. Keep the project name and
container data paths constant across releases: stored records contain absolute
container paths. `up --force-recreate` and `down` retain named volumes;
**`down --volumes` deletes data** and must never be used on a real deployment.
Existing development uploads are not automatically migrated into this new volume.

To pre-download the default embedding model and verify CPU inference:

```sh
docker compose --env-file backend/deploy/.env -f backend/deploy/compose.yaml run --rm --no-deps --entrypoint python backend -c "from engine.embedder import Embedder; e=Embedder(); print(e.encode(['deployment warm-up']).shape)"
```

This downloads model files, not paid AI tokens. It is optional for upload parsing,
but complete it before demonstrating semantic Verify. The default model is
currently `all-MiniLM-L6-v2`; deployment does not change Engine model selection.
Stop the main backend before this command if host memory is tight.

## Isolated acceptance rehearsal

```sh
python backend/deploy/smoke_deployment.py
# After the smoke image has already been built:
python backend/deploy/smoke_deployment.py --skip-build
# Or test a specific already-built release image without replacing it:
python backend/deploy/smoke_deployment.py --skip-build --image claimtrace-backend:local
```

The script builds `claimtrace-backend:smoke` by default, leaving the deployment's
image tag alone. It uses random, collision-checked Compose project names and port 18080,
creates a genuine PDF and BibTeX fixture, checks readiness and parsing, recreates
the container, backs up while stopped, and restores into a **second fresh data
volume**. It verifies the restored library, statuses and manuscript artifacts.
It never invokes paid AI or external publication lookup. At the end it removes
only its own test containers/data/cache volumes and temporary backup fixtures.
It does not use the real deployment's volumes. Choose another unused port with
`--port 18081` if necessary.

## Backup and restore

Backups contain uploaded research documents. Keep archives private and copy
them off the eventual server. Model caches and deploy secrets are not included.
Stop the backend to obtain a consistent snapshot across JSON and document files:

```sh
docker compose --env-file backend/deploy/.env -f backend/deploy/compose.yaml stop backend
docker compose --env-file backend/deploy/.env -f backend/deploy/compose.yaml run --rm --no-deps maintenance backup --archive /backups/backup-2026-10-03.tar.gz --offline
docker compose --env-file backend/deploy/.env -f backend/deploy/compose.yaml up -d --no-build backend
```

Use a unique dated archive name. Set `BACKUP_DIR` to an existing host directory
before running this command. Relative paths are relative to `backend/deploy/`.
On Linux prepare the directory with owner UID/GID 10001 and mode 0700 (for
example, `sudo install -d -m 0700 -o 10001 -g 10001 /srv/claimtrace-backups`).
On Windows, allow Docker Desktop access to the selected directory.

The tool stores SHA-256 checksums and rejects overwriting an existing archive.
Restore rejects non-empty destinations, links, unsafe paths, unexpected members
and checksum mismatches. `--offline` confirms that the backend using this data
has been stopped; it is an operator acknowledgement, not automatic stop detection.

To rehearse recovery, use a different Compose project with a fresh volume:

```sh
docker compose -p claimtrace-recovery --env-file backend/deploy/.env -f backend/deploy/compose.yaml run --rm --no-deps maintenance restore --archive /backups/backup-2026-10-03.tar.gz --offline
# Stop the original backend if both projects use the same host port.
docker compose -p claimtrace-recovery --env-file backend/deploy/.env -f backend/deploy/compose.yaml up -d --no-build backend
curl http://127.0.0.1:8000/ready
curl http://127.0.0.1:8000/api/papers
```

Do not start the recovery backend before restoring: preflight would create data
directories and the tool deliberately refuses a non-empty destination. Preserve
the original volume until the recovered deployment is checked. Use the recovery
project name consistently if it becomes the active deployment.

## Updates, logs and rollback

Build/tag an image per Git revision and set `BACKEND_IMAGE` accordingly. Before
updating, stop the backend and take a backup. Build the new image, then:

```sh
docker compose --env-file backend/deploy/.env -f backend/deploy/compose.yaml up -d --no-build --force-recreate backend
docker compose --env-file backend/deploy/.env -f backend/deploy/compose.yaml logs --tail 100 backend
docker compose --env-file backend/deploy/.env -f backend/deploy/compose.yaml ps
```

Check readiness, a real upload and existing records after each update. To roll
back code, set `BACKEND_IMAGE` to the retained previous tag and recreate without
building. If a future release changes stored schemas, an old image alone may
not suffice: restore its pre-update backup into a fresh volume as above.
Health failure marks the container unhealthy; `restart: unless-stopped` restarts
an exited process, **not merely an unhealthy container**. Read readiness checks
and logs to diagnose unhealthy services.

## Before exposure on a rented server

Keep the loopback binding and place an HTTPS reverse proxy/access gateway in
front of the backend. Configure its permitted users, upload size and request
timeouts, and set the frontend's actual origin in `CORS_ORIGINS`. CORS is not
authentication. Current Chrome-extension origins remain allowed by existing
backend middleware. Public access, user isolation/authentication, rate limits,
HTTPS/domain provisioning and resource sizing are still launch decisions.

Integrate Hongyang's API contract before exposing user credentials: confirm how
they are transmitted, that team-key fallback is absent, and that key-bearing
requests/provider errors are not logged. This deployment branch does not select
his credential storage or pipeline design. No servers are provisioned here.

## Evidence and references

See [VALIDATION.md](VALIDATION.md) for checks actually completed versus pending.
Docker semantics follow the official [Compose service reference](https://docs.docker.com/reference/compose-file/services/)
and [volume documentation](https://docs.docker.com/engine/storage/volumes/).
