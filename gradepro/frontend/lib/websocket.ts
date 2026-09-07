export function connectJobWebSocket(
  jobId: string,
  onMessage: (data: any) => void,
  onError?: (err: any) => void,
) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = process.env.NEXT_PUBLIC_WS_URL || `${protocol}//${window.location.host}/ws`;
  const wsUrl = `${host}/${jobId}`;

  let ws: WebSocket | null = new WebSocket(wsUrl);
  let reconnectAttempts = 0;
  let isClosed = false;

  ws.onopen = () => {
    reconnectAttempts = 0;
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (e) {
      onMessage(event.data);
    }
  };

  ws.onerror = (err) => {
    if (onError) onError(err);
  };

  ws.onclose = () => {
    if (!isClosed && reconnectAttempts < 5) {
      reconnectAttempts++;
      const timeout = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
      setTimeout(() => {
        if (!isClosed) {
          ws = connectJobWebSocket(jobId, onMessage, onError) as any;
        }
      }, timeout);
    }
  };

  return () => {
    isClosed = true;
    if (ws) ws.close();
  };
}
