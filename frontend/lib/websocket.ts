const WS_BASE =
  (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000")
    .replace(/^http/, "ws");

type MessageHandler = (data: any) => void;

class WebSocketClient {
  private sockets: Map<string, WebSocket> = new Map();
  private listeners: Map<string, Set<MessageHandler>> = new Map();
  private reconnectTimers: Map<string, any> = new Map();

  connect(channel: string, onMessage?: MessageHandler): () => void {
    if (!this.listeners.has(channel)) {
      this.listeners.set(channel, new Set());
    }
    if (onMessage) {
      this.listeners.get(channel)!.add(onMessage);
    }

    this.ensureConnection(channel);

    // Return cleanup function
    return () => {
      if (onMessage) {
        this.listeners.get(channel)?.delete(onMessage);
      }
    };
  }

  private ensureConnection(channel: string) {
    const existing = this.sockets.get(channel);
    if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
      return;
    }

    try {
      const url = `${WS_BASE}/ws/${channel}`;
      const socket = new WebSocket(url);

      socket.onopen = () => {
        // Connected
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const channelListeners = this.listeners.get(channel);
          if (channelListeners) {
            channelListeners.forEach((fn) => fn(data));
          }
        } catch (e) {
          // ignore non-json
        }
      };

      socket.onclose = () => {
        this.sockets.delete(channel);
        // Attempt reconnect in 3 seconds
        if (!this.reconnectTimers.has(channel)) {
          const timer = setTimeout(() => {
            this.reconnectTimers.delete(channel);
            if ((this.listeners.get(channel)?.size || 0) > 0) {
              this.ensureConnection(channel);
            }
          }, 3000);
          this.reconnectTimers.set(channel, timer);
        }
      };

      socket.onerror = () => {
        socket.close();
      };

      this.sockets.set(channel, socket);
    } catch (err) {
      // Ignore initial connection errors and let reconnect loop retry
    }
  }

  disconnectAll() {
    this.sockets.forEach((s) => s.close());
    this.sockets.clear();
    this.reconnectTimers.forEach((t) => clearTimeout(t));
    this.reconnectTimers.clear();
    this.listeners.clear();
  }
}

export const wsClient = new WebSocketClient();
