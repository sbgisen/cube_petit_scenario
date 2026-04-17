import { useEffect, useRef, useState } from 'react';
import * as ROSLIB from 'roslib';

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

const RECONNECT_INTERVAL_MS = 3000;
const DISCONNECT_DISPLAY_DELAY_MS = 2000; // 短い切断はUIに表示しない

export function useRosConnection(url: string) {
  const [ros, setRos] = useState<ROSLIB.Ros | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const statusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeRef = useRef(true);

  useEffect(() => {
    activeRef.current = true;

    function setStatusDelayed(s: ConnectionStatus) {
      if (statusTimerRef.current) clearTimeout(statusTimerRef.current);
      if (s === 'disconnected' || s === 'error') {
        // 切断はすぐ表示せず少し待ってから表示（再接続で解消すれば表示しない）
        statusTimerRef.current = setTimeout(() => setStatus(s), DISCONNECT_DISPLAY_DELAY_MS);
      } else {
        setStatus(s);
      }
    }

    function connect() {
      if (!activeRef.current) return;
      setStatusDelayed('connecting');

      const instance = new ROSLIB.Ros({ url });

      instance.on('connection', () => {
        if (!activeRef.current) { instance.close(); return; }
        setRos(instance);
        if (statusTimerRef.current) clearTimeout(statusTimerRef.current);
        setStatus('connected');
      });

      instance.on('error', () => {
        if (!activeRef.current) return;
        setStatusDelayed('error');
      });

      instance.on('close', () => {
        if (!activeRef.current) return;
        setRos(null);
        setStatusDelayed('disconnected');
        timerRef.current = setTimeout(connect, RECONNECT_INTERVAL_MS);
      });
    }

    connect();

    return () => {
      activeRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
      if (statusTimerRef.current) clearTimeout(statusTimerRef.current);
    };
  }, [url]);

  return { ros, status };
}
