export function connectWs(onMessage, onStatus) {
  let ws = null;
  let closed = false;

  function open() {
    if (closed) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => onStatus(true);
    ws.onclose = () => {
      onStatus(false);
      if (!closed) setTimeout(open, 2000);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data));
      } catch (err) {
        console.error('WS parse error', err);
      }
    };
  }

  open();
  return () => {
    closed = true;
    ws?.close();
  };
}
