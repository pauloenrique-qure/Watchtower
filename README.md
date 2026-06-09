# Watchtower

Local observability platform for isolated DCMIO Raspberry Pi gateways without outbound connectivity to Pulse.

Runs on MacBook Air / Mac mini. Queries remote gateways via Teleport (`tsh ssh`). Read-only — never modifies gateways.

---

## Architecture

```
MacBook Air / Mac mini
  └── FastAPI (localhost:8000)
        └── Scheduler (every 2min)
              └── TeleportAdapter → tsh ssh → Raspberry Pi
                    └── Read-only commands → SQLite local → Dashboard
```

---

## Requirements

- Python 3.12+
- `tsh` CLI installed and in PATH (`brew install teleport` or from teleport.dev)
- Active Teleport session (see below)

---

## Installation

```bash
cd Watchtower
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Teleport Login

Before running Watchtower, authenticate with Teleport:

```bash
tsh login --proxy=teleport.qure.ai --user=<your-username>
```

Watchtower will detect if your session expires and show a global warning. It will not attempt any remote checks until you re-authenticate.

---

## Run

```bash
python run.py
```

Open: [http://localhost:8000](http://localhost:8000)

---

## Edit gateways

Edit `config/gateways.yaml`. Restart the app to apply changes.

Fields:
- `name` — display name
- `host` — Teleport node hostname
- `ssh_login` — SSH user (usually `ubuntu`)
- `enabled` — set `false` to skip without deleting
- `profile` — `standard` or `extended` (informational, used for display)

---

## Status definitions

| Status   | Meaning                                        |
|----------|------------------------------------------------|
| OK       | All checks pass                                |
| WARNING  | Non-critical issue (high load, failed tasks)   |
| CRITICAL | Service down or unreachable                    |
| UNKNOWN  | Check could not run (no data yet)              |
| SKIPPED  | Check skipped because a prerequisite failed    |

---

## Health Score (0–100)

Weighted sum of component statuses:

| Component    | Weight | Cap rules                            |
|--------------|--------|--------------------------------------|
| SSH          | 25%    | Score = 0 if SSH DOWN                |
| Docker Core  | 20%    | Score max 50 if core DOWN            |
| PostgreSQL   | 15%    | Score max 60 if PG DOWN              |
| Workers      | 10%    |                                      |
| Pipeline     | 15%    |                                      |
| Hardware     | 10%    |                                      |
| Mirth        | 5%     | Only counted if Mirth is present     |

---

## Read-only guarantee

Watchtower never executes:
- `restart`, `stop`, `start`, `rm`, `kill`
- `docker restart`, `docker stop`, `docker compose up/down`
- Any `UPDATE`, `DELETE`, `INSERT`, `ALTER`, `DROP`, `TRUNCATE`
- Any interactive or streaming command

All remote access goes through `tsh ssh` with a fixed timeout. No credentials, OTPs, or private keys are stored.

---

## Troubleshooting

**`tsh not found in PATH`** — Install Teleport CLI: `brew install teleport`

**`Teleport Session Expired`** — Re-run: `tsh login --proxy=teleport.qure.ai --user=<user>`

**Gateway shows UNKNOWN with no data** — The first check cycle runs at startup. Wait ~10 seconds or click "Run Now".

**Gateway shows CRITICAL / SSH DOWN** — The gateway is unreachable via Teleport. Check if the node is registered: `tsh ls`

**PostgreSQL CRITICAL** — The `postgres_dcmio` container may be down, or `docker exec` is failing. Check Docker status on the detail page.

**High pending_older_2h** — Backlog is growing. Check worker count and pipeline status.
