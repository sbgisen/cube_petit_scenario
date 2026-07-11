import { useEffect, useRef, useState } from 'react';
import * as ROSLIB from 'roslib';

export interface RosTopicOptions {
  // rosbridge側で間引く間隔(ms)。指定するとその間隔より短い周期のメッセージは送られてこない
  throttleRate?: number;
  // rosbridge側の購読キュー長。1にすると常に最新メッセージのみ配信され、
  // 処理が追いつかない時に古いフレームが溜まって後から再生される事故を防げる
  queueLength?: number;
}

export function useRosTopic<T>(
  ros: ROSLIB.Ros | null,
  name: string,
  messageType: string,
  enabled = true,
  options?: RosTopicOptions,
) {
  const [message, setMessage] = useState<T | null>(null);
  const topicRef = useRef<ROSLIB.Topic | null>(null);
  const throttleRate = options?.throttleRate;
  const queueLength = options?.queueLength;

  useEffect(() => {
    if (!ros || !enabled) {
      setMessage(null);
      return;
    }

    const topic = new ROSLIB.Topic({
      ros,
      name,
      messageType,
      ...(throttleRate !== undefined ? { throttle_rate: throttleRate } : {}),
      ...(queueLength !== undefined ? { queue_length: queueLength } : {}),
    });
    topicRef.current = topic;
    topic.subscribe((msg: unknown) => setMessage(msg as T));

    return () => {
      topic.unsubscribe();
    };
  }, [ros, name, messageType, enabled, throttleRate, queueLength]);

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
