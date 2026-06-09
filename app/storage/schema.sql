CREATE TABLE IF NOT EXISTS gateways (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    host TEXT NOT NULL UNIQUE,
    ssh_login TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    country TEXT NOT NULL DEFAULT '',
    profile TEXT NOT NULL DEFAULT 'standard'
);

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gateway_host TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    overall_status TEXT NOT NULL,
    health_score INTEGER NOT NULL DEFAULT 0,
    ssh_status TEXT NOT NULL,
    docker_status TEXT NOT NULL,
    postgres_status TEXT NOT NULL,
    pipeline_status TEXT NOT NULL,
    hardware_status TEXT NOT NULL,
    mirth_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    payload_json TEXT NOT NULL DEFAULT '{}',
    error_message TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_snapshots_host ON snapshots(gateway_host);
CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON snapshots(timestamp);
