import { useCallback, useRef, useState } from 'react';
import * as ROSLIB from 'roslib';
import { useRosPublisher } from '../hooks/useRosTopic';

interface Props {
  ros: ROSLIB.Ros | null;
  namespace: string;
  maxLinear?: number;
  maxAngular?: number;
}

export function Joystick({ ros, namespace, maxLinear = 0.3, maxAngular = 4.0 }: Props) {
  const publish = useRosPublisher(ros, `/${namespace}/diff_drive_controller/cmd_vel`, 'geometry_msgs/TwistStamped');
  const containerRef = useRef<HTMLDivElement>(null);
  const [knobPos, setKnobPos] = useState({ x: 0, y: 0 });
  const activeRef = useRef(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const velRef = useRef({ linear: 0, angular: 0 });

  const SIZE = 160;
  const KNOB = 48;
  const MAX_R = SIZE / 2 - KNOB / 2;

  const startPublishing = useCallback(() => {
    if (intervalRef.current) return;
    intervalRef.current = setInterval(() => {
      publish({
        header: { stamp: { sec: 0, nanosec: 0 }, frame_id: '' },
        twist: {
          linear: { x: velRef.current.linear, y: 0, z: 0 },
          angular: { x: 0, y: 0, z: velRef.current.angular },
        },
      });
    }, 100);
  }, [publish]);

  const stopPublishing = useCallback(() => {
    activeRef.current = false;
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    publish({ header: { stamp: { sec: 0, nanosec: 0 }, frame_id: '' }, twist: { linear: { x: 0, y: 0, z: 0 }, angular: { x: 0, y: 0, z: 0 } } });
    setKnobPos({ x: 0, y: 0 });
    velRef.current = { linear: 0, angular: 0 };
  }, [publish]);

  const handleMove = useCallback((clientX: number, clientY: number) => {
    if (!activeRef.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const dx = clientX - (rect.left + SIZE / 2);
    const dy = clientY - (rect.top + SIZE / 2);
    const dist = Math.sqrt(dx * dx + dy * dy);
    const clamped = Math.min(dist, MAX_R);
    const angle = Math.atan2(dy, dx);
    const nx = clamped * Math.cos(angle);
    const ny = clamped * Math.sin(angle);
    setKnobPos({ x: nx, y: ny });
    velRef.current = {
      linear: (-ny / MAX_R) * maxLinear,
      angular: (-nx / MAX_R) * maxAngular,
    };
  }, [MAX_R, maxLinear, maxAngular]);

  return (
    <div
      ref={containerRef}
      style={{
        width: SIZE, height: SIZE, borderRadius: '50%',
        background: 'var(--t-knob-bg)', border: '2px solid var(--t-knob-border)',
        position: 'relative', userSelect: 'none', touchAction: 'none', flexShrink: 0,
      }}
      onPointerDown={(e) => {
        activeRef.current = true;
        (e.target as HTMLElement).setPointerCapture(e.pointerId);
        handleMove(e.clientX, e.clientY);
        startPublishing();
      }}
      onPointerMove={(e) => handleMove(e.clientX, e.clientY)}
      onPointerUp={stopPublishing}
      onPointerCancel={stopPublishing}
    >
      <div style={{
        width: KNOB, height: KNOB, borderRadius: '50%',
        background: 'var(--t-accent)', position: 'absolute',
        left: SIZE / 2 - KNOB / 2 + knobPos.x,
        top: SIZE / 2 - KNOB / 2 + knobPos.y,
        pointerEvents: 'none',
        boxShadow: '0 0 10px rgba(255,102,0,0.8)',
      }} />
    </div>
  );
}
