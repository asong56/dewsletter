CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,              -- hash(source_id + run_id)
    source_id TEXT NOT NULL,          -- URL (RSS / YouTube)
    title TEXT,
    content TEXT,
    created_at TEXT,
    run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    stage TEXT NOT NULL,              -- fetch / parse / store
    error_type TEXT NOT NULL,         -- timeout / network / format / unknown
    message TEXT
);
