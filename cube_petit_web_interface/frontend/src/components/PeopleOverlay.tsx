import * as ROSLIB from 'roslib';
import { useRosTopic } from '../hooks/useRosTopic';

interface Marker {
  ns: string;
  pose: { position: { x: number; y: number } };
  color: { r: number; g: number; b: number; a: number };
}

interface MarkerArray {
  markers: Marker[];
}

interface Props {
  ros: ROSLIB.Ros | null;
  enabled: boolean;
  size: number;
  scale: number;
}

export function PeopleOverlay({ ros, enabled, size, scale }: Props) {
  const markerArray = useRosTopic<MarkerArray>(
    ros,
    '/object_detection/laser/marker',
    'visualization_msgs/MarkerArray',
    enabled,
  );

  if (!enabled || !markerArray) return null;

  const cx = size / 2;
  const cy = size / 2;

  const legs = markerArray.markers.filter((m) => m.ns === 'PEOPLE');

  return (
    <svg
      width={size}
      height={size}
      style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}
    >
      {legs.map((m, i) => {
        const x = cx + m.pose.position.x * scale;
        const y = cy - m.pose.position.y * scale;
        return (
          <g key={i}>
            <circle cx={x} cy={y} r={10} fill="rgba(255,100,100,0.7)" stroke="#ff4444" strokeWidth={2} />
            <text x={x} y={y - 14} fill="#ff4444" fontSize={11} textAnchor="middle">人</text>
          </g>
        );
      })}
    </svg>
  );
}
