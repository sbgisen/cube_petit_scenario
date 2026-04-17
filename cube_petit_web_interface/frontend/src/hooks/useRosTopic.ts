import { useEffect, useRef, useState } from 'react';
import * as ROSLIB from 'roslib';

export function useRosTopic<T>(
  ros: ROSLIB.Ros | null,
  name: string,
  messageType: string,
  enabled = true,
) {
  const [message, setMessage] = useState<T | null>(null);
  const topicRef = useRef<ROSLIB.Topic | null>(null);

  useEffect(() => {
    if (!ros || !enabled) {
      setMessage(null);
      return;
    }

    const topic = new ROSLIB.Topic({ ros, name, messageType });
    topicRef.current = topic;
    topic.subscribe((msg: unknown) => setMessage(msg as T));

    return () => {
      topic.unsubscribe();
    };
  }, [ros, name, messageType, enabled]);

  return message;
}

export function useRosPublisher(
  ros: ROSLIB.Ros | null,
  name: string,
  messageType: string,
) {
  const topicRef = useRef<ROSLIB.Topic | null>(null);

  useEffect(() => {
    if (!ros) return;
    topicRef.current = new ROSLIB.Topic({ ros, name, messageType });
    return () => {
      topicRef.current?.unadvertise();
    };
  }, [ros, name, messageType]);

  const publish = (message: object) => {
    topicRef.current?.publish(message as never);
  };

  return publish;
}
