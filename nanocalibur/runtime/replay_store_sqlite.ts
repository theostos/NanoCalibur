declare const require: any;

interface SQLiteStatement {
  run(...args: any[]): any;
  get(...args: any[]): any;
}

interface SQLiteDatabase {
  exec(sql: string): void;
  prepare(sql: string): SQLiteStatement;
  close(): void;
}

interface SessionSeedStore {
  reserveSeed(sessionId: string, seed: string, metadata?: Record<string, any>): void;
  hasSeed(seed: string): boolean;
  appendEvent(
    sessionId: string,
    eventType: string,
    payload?: Record<string, any>,
    tick?: number,
  ): void;
}

function loadBetterSqlite3Ctor(): (new (filename: string) => SQLiteDatabase) {
  try {
    return require("better-sqlite3") as new (filename: string) => SQLiteDatabase;
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown module load error.";
    throw new Error(
      `ReplayStoreSQLite requires 'better-sqlite3' to be installed. (${message})`,
    );
  }
}

export class ReplayStoreSQLite implements SessionSeedStore {
  private readonly db: SQLiteDatabase;

  constructor(filename: string) {
    if (!filename || typeof filename !== "string") {
      throw new Error("ReplayStoreSQLite filename must be a non-empty string.");
    }
    const Ctor = loadBetterSqlite3Ctor();
    this.db = new Ctor(filename);
    this.db.exec(
      [
        "PRAGMA journal_mode = WAL;",
        "CREATE TABLE IF NOT EXISTS sessions (",
        "  session_id TEXT PRIMARY KEY,",
        "  seed TEXT NOT NULL UNIQUE,",
        "  metadata_json TEXT NOT NULL,",
        "  created_at INTEGER NOT NULL",
        ");",
        "CREATE TABLE IF NOT EXISTS events (",
        "  session_id TEXT NOT NULL,",
        "  seq INTEGER NOT NULL,",
        "  event_type TEXT NOT NULL,",
        "  payload_json TEXT NOT NULL,",
        "  tick INTEGER,",
        "  created_at INTEGER NOT NULL,",
        "  PRIMARY KEY (session_id, seq)",
        ");",
      ].join("\n"),
    );
  }

  reserveSeed(sessionId: string, seed: string, metadata: Record<string, any> = {}): void {
    this.db
      .prepare(
        "INSERT INTO sessions (session_id, seed, metadata_json, created_at) VALUES (?, ?, ?, ?)",
      )
      .run(sessionId, seed, JSON.stringify(metadata || {}), Date.now());
  }

  hasSeed(seed: string): boolean {
    const row = this.db
      .prepare("SELECT 1 AS found FROM sessions WHERE seed = ? LIMIT 1")
      .get(seed);
    return Boolean(row && row.found === 1);
  }

  appendEvent(
    sessionId: string,
    eventType: string,
    payload: Record<string, any> = {},
    tick?: number,
  ): void {
    const next = this.db
      .prepare("SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM events WHERE session_id = ?")
      .get(sessionId);
    const seq =
      next && typeof next.next_seq === "number" && Number.isFinite(next.next_seq)
        ? Math.trunc(next.next_seq)
        : 1;
    this.db
      .prepare(
        "INSERT INTO events (session_id, seq, event_type, payload_json, tick, created_at) VALUES (?, ?, ?, ?, ?, ?)",
      )
      .run(
        sessionId,
        seq,
        eventType,
        JSON.stringify(payload || {}),
        typeof tick === "number" && Number.isFinite(tick) ? Math.trunc(tick) : null,
        Date.now(),
      );
  }

  close(): void {
    this.db.close();
  }
}

export type { SessionSeedStore };
