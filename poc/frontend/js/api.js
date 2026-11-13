async function request(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      if (data.detail) detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  config: () => request('GET', '/api/config'),
  cameras: () => request('GET', '/api/cameras'),
  addCamera: (body) => request('POST', '/api/cameras', body),
  updateCamera: (id, body) => request('PUT', `/api/cameras/${id}`, body),
  deleteCamera: (id) => request('DELETE', `/api/cameras/${id}`),
  saveZone: (id, points) => request('PUT', `/api/cameras/${id}/zone`, { points }),
  events: () => request('GET', '/api/events'),
};
