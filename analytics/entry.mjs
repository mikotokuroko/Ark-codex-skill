import { DurableObject } from 'cloudflare:workers';
import handler from './worker.mjs';

// Each event kind has its own strongly consistent counter and deduplication set.
export class AdoptionCounter extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    ctx.blockConcurrencyWhile(async () => {
      ctx.storage.sql.exec('CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)');
    });
  }
  record(eventId) {
    this.ctx.storage.sql.exec('INSERT OR IGNORE INTO events (event_id) VALUES (?)', eventId);
  }
  count() {
    return this.ctx.storage.sql.exec('SELECT COUNT(*) AS count FROM events').one().count;
  }
}
export default handler;
