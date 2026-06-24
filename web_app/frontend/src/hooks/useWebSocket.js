import { useEffect, useRef } from 'react';
import { authApi } from '../services/api';

export function useWebSocket(url, onMessage) {
  const wsRef = useRef(null);
  
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const token = authApi.getToken();
    const separator = url.includes('?') ? '&' : '?';
    const authSuffix = token ? `${separator}token=${encodeURIComponent(token)}` : '';
    const wsUrl = `${protocol}//${window.location.host}${url}${authSuffix}`;
    
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    
    ws.onopen = () => console.log('WebSocket connected');
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      onMessage(data);
    };
    ws.onerror = (error) => console.error('WebSocket error:', error);
    ws.onclose = () => {
      console.log('WebSocket closed');
      // Reconnect after 3 seconds
      setTimeout(() => {
        if (wsRef.current === ws) {
          ws.close();
        }
      }, 3000);
    };
    
    return () => {
      ws.close();
    };
  }, [url]);
}
