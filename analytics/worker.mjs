const json = (body, status = 200) => Response.json(body, {status, headers: {'Cache-Control': 'no-store'}});
export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    if (path === '/health' && request.method === 'GET') return json({ok: true});
    if (path === '/totals' && request.method === 'GET') {
      // Fail closed if the secret has not been configured.
      if (!env.ADMIN_TOKEN || request.headers.get('Authorization') !== `Bearer ${env.ADMIN_TOKEN}`) return json({error: 'unauthorized'}, 401);
      const totals = {};
      for (const kind of ['installation', 'pet_generation']) totals[kind] = await env.COUNTERS.getByName(kind).count();
      return json({totals, as_of: new Date().toISOString(), scope: 'Opted-in reported events; not unique people.'});
    }
    if (path !== '/events' || request.method !== 'POST') return json({error: 'not_found'}, 404);
    if (!(request.headers.get('Content-Type') || '').startsWith('application/json')) return json({error: 'content_type'}, 415);
    // Bound actual streamed bytes, even if Content-Length is omitted or forged.
    const reader = request.body?.getReader();
    if (!reader) return json({error: 'invalid_event'}, 400);
    let size = 0; const chunks = [];
    while (true) {
      const {done, value} = await reader.read(); if (done) break;
      size += value.length;
      if (size > 512) { await reader.cancel(); return json({error: 'too_large'}, 413); }
      chunks.push(value);
    }
    const bytes = new Uint8Array(size); let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
    let event;
    try { event = JSON.parse(new TextDecoder().decode(bytes)); } catch { return json({error: 'invalid_event'}, 400); }
    if (!event || typeof event !== 'object' || Array.isArray(event) || Object.keys(event).sort().join(',') !== 'event_id,kind' ||
        !['installation', 'pet_generation'].includes(event.kind) || typeof event.event_id !== 'string' ||
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(event.event_id)) return json({error: 'invalid_event'}, 400);
    // A public client cannot hold a secret. Apply edge throttling, never store IPs.
    if (env.EVENT_LIMITER) {
      const {success} = await env.EVENT_LIMITER.limit({key: request.headers.get('CF-Connecting-IP') || 'unknown'});
      if (!success) return json({error: 'rate_limited'}, 429);
    }
    await env.COUNTERS.getByName(event.kind).record(event.event_id);
    return json({ok: true}, 202);
  }
};
