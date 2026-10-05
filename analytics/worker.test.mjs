import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import worker from './worker.mjs';
function setup() {
 const db = new DatabaseSync(':memory:'); db.exec(readFileSync(new URL('./schema.sql',import.meta.url),'utf8'));
 const env = {ADMIN_TOKEN: 'test-secret', COUNTERS: {getByName(kind) {return {
   async record(id) {db.prepare('INSERT OR IGNORE INTO events (event_id, kind) VALUES (?, ?)').run(id,kind)},
   async count() {return db.prepare('SELECT COUNT(*) AS count FROM events WHERE kind = ?').get(kind).count}
 }}}};
 return env;
}
const event = {event_id:'11111111-1111-4111-8111-111111111111',kind:'installation'};
const post = data => new Request('https://test/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
test('private totals, deduplication, and real SQLite counts',async()=>{
 const env=setup();
 assert.equal((await worker.fetch(new Request('https://test/totals'),env)).status,401);
 await worker.fetch(post(event),env);await worker.fetch(post(event),env);
 await worker.fetch(post({...event,event_id:'22222222-2222-4222-8222-222222222222',kind:'pet_generation'}),env);
 const response=await worker.fetch(new Request('https://test/totals',{headers:{Authorization:'Bearer test-secret'}}),env);
 assert.deepEqual((await response.json()).totals,{installation:1,pet_generation:1});
 assert.equal(response.headers.get('Cache-Control'),'no-store');
 delete env.ADMIN_TOKEN;
 assert.equal((await worker.fetch(new Request('https://test/totals',{headers:{Authorization:'Bearer undefined'}}),env)).status,401);
});
test('reject malformed, extra private fields, oversized payloads and throttled requests',async()=>{
 const env=setup();
 for(const data of [null,[],{}, {...event,path:'/private/file'}, {...event,kind:'anything'}, {...event,event_id:12}]) assert.equal((await worker.fetch(post(data),env)).status,400);
 assert.equal((await worker.fetch(post('x'.repeat(600)),env)).status,413);
 env.EVENT_LIMITER={limit:async()=>({success:false})};
 assert.equal((await worker.fetch(post(event),env)).status,429);
});
