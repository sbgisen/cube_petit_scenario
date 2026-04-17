import { useEffect, useRef, useState } from 'react';
import * as ROSLIB from 'roslib';

export interface TFTransform {
  translation: { x: number; y: number; z: number };
  rotation: { x: number; y: number; z: number; w: number };
}

interface TFMsg {
  transforms: Array<{
    header: { frame_id: string };
    child_frame_id: string;
    transform: TFTransform;
  }>;
}

function quatToYaw(q: { z: number; w: number }) {
  return 2 * Math.atan2(q.z, q.w);
}

// T_A_C = T_A_B * T_B_C (2D compose)
function compose(tab: TFTransform, tbc: TFTransform): TFTransform {
  const yaw_ab = quatToYaw(tab.rotation);
  const cos_a = Math.cos(yaw_ab);
  const sin_a = Math.sin(yaw_ab);
  const tx = tab.translation.x + cos_a * tbc.translation.x - sin_a * tbc.translation.y;
  const ty = tab.translation.y + sin_a * tbc.translation.x + cos_a * tbc.translation.y;
  const yaw_bc = quatToYaw(tbc.rotation);
  const yaw_ac = yaw_ab + yaw_bc;
  return {
    translation: { x: tx, y: ty, z: 0 },
    rotation: { x: 0, y: 0, z: Math.sin(yaw_ac / 2), w: Math.cos(yaw_ac / 2) },
  };
}

// /tf を直接購読して fixedFrame→targetFrame の変換を返す
export function useRosTf(
  ros: ROSLIB.Ros | null,
  fixedFrame: string,
  targetFrame: string,
  enabled: boolean
): TFTransform | null {
  const [transform, setTransform] = useState<TFTransform | null>(null);
  // frame_id → Map<child_frame_id, TFTransform>
  const tfTreeRef = useRef<Map<string, Map<string, TFTransform>>>(new Map());

  useEffect(() => {
    if (!ros || !enabled) {
      setTransform(null);
      return;
    }

    function storeTF(msg: TFMsg) {
      let changed = false;
      for (const t of msg.transforms) {
        const parent = t.header.frame_id;
        const child = t.child_frame_id;
        if (!tfTreeRef.current.has(parent)) {
          tfTreeRef.current.set(parent, new Map());
        }
        tfTreeRef.current.get(parent)!.set(child, t.transform);
        changed = true;
      }
      if (!changed) return;

      // fixedFrame→targetFrame をBFSで探索
      const result = lookup(tfTreeRef.current, fixedFrame, targetFrame);
      if (result) setTransform(result);
    }

    const tfTopic = new ROSLIB.Topic({
      ros,
      name: '/tf',
      messageType: 'tf2_msgs/TFMessage',
    });
    const tfStaticTopic = new ROSLIB.Topic({
      ros,
      name: '/tf_static',
      messageType: 'tf2_msgs/TFMessage',
    });

    tfTopic.subscribe(storeTF as (msg: ROSLIB.Message) => void);
    tfStaticTopic.subscribe(storeTF as (msg: ROSLIB.Message) => void);

    return () => {
      try { tfTopic.unsubscribe(); tfStaticTopic.unsubscribe(); } catch {}
      tfTreeRef.current.clear();
      setTransform(null);
    };
  }, [ros, fixedFrame, targetFrame, enabled]);

  return transform;
}

// BFSでfixedFrame→targetFrameのパスを探してtransformを合成
function lookup(
  tree: Map<string, Map<string, TFTransform>>,
  from: string,
  to: string
): TFTransform | null {
  if (from === to) {
    return { translation: { x: 0, y: 0, z: 0 }, rotation: { x: 0, y: 0, z: 0, w: 1 } };
  }
  const visited = new Set<string>([from]);
  const queue: Array<{ frame: string; tf: TFTransform }> = [
    { frame: from, tf: { translation: { x: 0, y: 0, z: 0 }, rotation: { x: 0, y: 0, z: 0, w: 1 } } },
  ];
  while (queue.length > 0) {
    const { frame, tf } = queue.shift()!;
    const children = tree.get(frame);
    if (children) {
      for (const [child, childTf] of children) {
        if (visited.has(child)) continue;
        const composed = compose(tf, childTf);
        if (child === to) return composed;
        visited.add(child);
        queue.push({ frame: child, tf: composed });
      }
    }
  }
  return null;
}
