# Deployment validation record

Date: 2026-10-03 (Australia/Sydney). Branch: `backend/deployment-prep`.
Pre-push validation repeated on 2026-10-04 (Australia/Sydney).

This record distinguishes checks run on the host from Linux container acceptance.
No paid AI requests are part of this validation.

| Check | Result |
| --- | --- |
| Production Compose configuration | Passed `docker compose ... config --quiet` |
| Python lint and whitespace | Passed Ruff on backend source, tests and deploy scripts; `git diff --check` passed |
| Final backend regression | 264 tests passed, including all 16 new deployment tests; 2 existing FastAPI startup deprecation warnings; optional pytest cache disabled for the pre-push run |
| Final deployment tests | 16 tests passed after backup hard-link support and 2 added tests; includes a real generated PDF upload through the current Parser and loading its persisted manuscript |
| Python package builds | Backend, Parser and Engine wheels built successfully on the host |
| Host dependency consistency | `pip check` passed in the isolated test virtual environment |
| Local Linux Docker engine | Passed after path-layout repair; Engine 29.8.1 responds before and after a normal Desktop restart |
| Linux production image build | Passed on `linux/amd64`; Python 3.11.17 and image dependency `pip check` passed |
| Non-root Linux runtime and native libraries | Passed as UID/GID 10001 with read-only root, dropped capabilities and no network; Java 17.0.20.1, CPU PyTorch tensor and FAISS index checks passed |
| Runtime readiness / real PDF parsing / BibTeX upload | Passed in the production Compose service with real generated fixtures |
| Container recreation and fresh-volume recovery | Passed: records, parse status and manuscript artifacts survived recreation and offline archive recovery into a second fresh data volume |
| Isolated test cleanup | Passed: neither random test project has remaining containers, volumes or networks; built image and build cache were retained |
| Embedding model warm-up and capacity measurement | Not run; separate documented steps |
| Deployment CI rehearsal | Workflow added; not yet executed on GitHub |

Docker Desktop was upgraded from 4.43.2 to 4.93.0 using the verified official
installer after stopped-state backups of both WSL disks and settings. The upgrade
alone did not restore the engine: the startup bind error changed from
`dockerInference` to `sailor-ingest.sock`. WSL 2 and the `docker-desktop`
distribution are present; the distribution was stopped during the follow-up
checks. No factory reset, volume cleanup or disk restore was performed.

Follow-up socket probes found that `%LOCALAPPDATA%\Docker` was a junction to a
D-drive directory. Binding a uniquely named AF_UNIX socket directly inside the
physical D-drive `run` directory succeeded, while binding through the C-drive
junction path failed with the same address-in-use error.
Separate probes in the Windows temporary directory succeeded. These results
implicate the redirected path, not a general absence of Windows AF_UNIX support;
they do not establish that changing the path will resolve every startup issue.
The user then approved a small C-drive runtime directory, with large data kept
on D. The original root junction was preserved under a backup name. A real C-drive
Docker root/run directory now uses child junctions for the existing D-drive WSL
data, logs and tasks. No virtual disks were copied to C or restored; both original
disk hashes matched the stopped-state backups before startup. Engine 29.8.1 now
responds, including after a normal Desktop restart. This local workaround resolves
the observed bind failure but is not a supported-layout guarantee. WSL data and
logs remain physically on D. No existing containers or volumes were removed.

Host regression tests ran on Windows with Python 3.12.14 and CPU PyTorch 2.6.0,
sentence-transformers 3.4.1 and transformers 4.49.0. This is **not** the Linux
Python 3.11 image. The separate Linux acceptance below now covers image startup,
non-root UID permissions, real parsing and named-volume recovery. Unit test
success alone does not establish container readiness.
The final host run explicitly included the monorepo's Parser and Engine source
roots and used a fresh ignored D-drive test directory. An earlier optional
pytest-cache permission warning did not affect results; caching was disabled for
the pre-push run.

## Completed Linux acceptance

The isolated rehearsal returned `status: passed` and `paid_ai_calls: 0` after all
seven checks: runtime readiness, real PDF parsing, BibTeX upload, container
recreation, offline backup, restore into a new volume, and restored library and
manuscript artifacts. The archive contained six generated fixture files.
Projects `claimtrace-smoke-9fed9253` and `claimtrace-smoke-9fed9253-restore` were
cleaned up; label-filtered checks confirmed no remaining test containers, volumes
or networks. The image and build cache remain available for repeat tests on D.
No existing library data or paid AI was used. Temporary archive fixtures were
created in the ignored D-drive virtual-environment directory, not on C.

The 2026-10-04 pre-push run repeated all seven checks using the same already-built
image and returned `status: passed`, `paid_ai_calls: 0`. Its separate random
projects `claimtrace-smoke-e4aba728` and `claimtrace-smoke-e4aba728-restore` were
also removed, including their generated test data volumes and temporary archive.

Image: `claimtrace-backend:smoke` (`linux/amd64`, about 2.68 GB logical image size).
Local image ID:
`sha256:f29c361fdd883c019ed93e6da6f3231f46f4443d8b080c899baf5d14421aca19`.
The image is not published. Its native CPU checks passed in a separate disposable,
network-disabled, read-only container: PyTorch 2.6.0+cpu, FAISS 1.15.1,
sentence-transformers 3.4.1 and transformers 4.49.0. No embedding model was
downloaded, so semantic inference/model warm-up is still unvalidated.

To repeat from `claimtrace/`:

```sh
python backend/deploy/smoke_deployment.py --skip-build
```

Only a successful final `status: passed` proves the container/round-trip checks.
Rebuild without `--skip-build` after changing the source or image dependencies.
GitHub CI execution, Hongyang's BYOK integration, semantic model warm-up, capacity
measurement and public-launch security/access decisions remain separate work.
