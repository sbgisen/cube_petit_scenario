import * as ROSLIB from 'roslib';
import { useRosTopic } from '../hooks/useRosTopic';

interface DoaMsg {
  data: number;
}

interface Props {
  ros: ROSLIB.Ros | null;
  namespace: string;
  enabled: boolean;
  size: number;
}

export function DoaOverlay({ ros, namespace, enabled, size }: Props) {
  const doa = useRosTopic<DoaMsg>(ros, `/${namespace}/doa`, 'std_msgs/Int32', enabled);

  if (!enabled || doa === null) return null;

  const angle = (doa.data * Math.PI) / 180;
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 20;
  const x = cx + r * Math.sin(angle);
  const y = cy - r * Math.cos(angle);

  return (
    <svg
      width={size}
      height={size}
      style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}
    >
      <line x1={cx} y1={cy} x2={x} y2={y} stroke="#ffcc00" strokeWidth={3} />
      <circle cx={x} cy={y} r={8} fill="#ffcc00" />
      <text x={x + 10} y={y} fill="#ffcc00" fontSize={12}>
        {doa.data}°
      </text>
    </svg>
  );
}
