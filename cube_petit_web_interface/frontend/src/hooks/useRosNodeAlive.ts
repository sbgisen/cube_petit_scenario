import { useEffect, useState } from 'react';

const API_URL = 'http://localhost:8000';

export function useSpeechServerAlive(namespace: string): boolean {
  const [alive, setAlive] = useState(false);

  useEffect(() => {
    const actionName = `/${namespace}/speech_action_server`;
    const check = async () => {
      try {
        const res = await fetch(`${API_URL}/action/exists?name=${encodeURIComponent(actionName)}`);
        const data = await res.json();
        setAlive(data.exists === true);
      } catch {
        setAlive(false);
      }
    };

    check();
    const interval = setInterval(check, 5000);
    return () => clearInterval(interval);
  }, [namespace]);

  return alive;
}
