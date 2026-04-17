import * as ROSLIB from 'roslib';
import { useRosTopic } from '../hooks/useRosTopic';

interface InternalState {
  curiosity: number;
  boredom: number;
  energy: number;
  silence_bias: number;
  body_generation: number;
  human_detected: boolean;
  petit_detected: boolean;
  sleep_mode: boolean;
}

interface Props {
  ros: ROSLIB.Ros | null;
  namespace: string;
}

const GAUGES: { key: keyof InternalState; label: string; color: string; emoji: string }[] = [
  { key: 'curiosity',    label: '好奇心',    color: '#ffcc00', emoji: '✨' },
  { key: 'boredom',      label: '退屈',      color: '#888',    emoji: '💤' },
  { key: 'energy',       label: 'エネルギー', color: '#00cc66', emoji: '⚡' },
  { key: 'silence_bias', label: '沈黙傾向',  color: '#9966ff', emoji: '🤫' },
];

function Gauge({ value, color, label, emoji }: { value: number; color: string; label: string; emoji: string }) {
  const pct = Math.min(100, Math.max(0, value));
  return (
    <div style={{ marginBottom: 3 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
        <span style={{ color: 'var(--t-text)', fontSize: 10 }}>{emoji} {label}</span>
        <span style={{ color, fontSize: 10, fontWeight: 'bold' }}>{pct.toFixed(1)}</span>
      </div>
      <div style={{ background: '#222', borderRadius: 3, height: 5, overflow: 'hidden' }}>
        <div style={{
          width: `${pct}%`, height: '100%', background: color,
          borderRadius: 3, transition: 'width 0.4s ease',
          boxShadow: `0 0 4px ${color}88`,
        }} />
      </div>
    </div>
  );
}

function Flag({ active, label, activeColor = '#00cc66' }: { active: boolean; label: string; activeColor?: string }) {
  return (
    <div style={{
      padding: '2px 6px', borderRadius: 10, fontSize: 10,
      background: active ? `${activeColor}33` : '#222',
      color: active ? activeColor : '#555',
      border: `1px solid ${active ? activeColor : 'var(--t-border)'}`,
    }}>
      {label}
    </div>
  );
}

export function AnimaPanel({ ros, namespace }: Props) {
  const state = useRosTopic<InternalState>(
    ros,
    `/${namespace}/internal_state`,
    'cube_petit_scenario_msgs/InternalState',
    true,
  );

  return (
    <div style={{
      background: '#16162a', borderRadius: 8, padding: '6px 10px',
      border: '1px solid var(--t-surface2)', flexShrink: 0,
    }}>
      <div style={{ color: '#666', fontSize: 10, marginBottom: 5, letterSpacing: 1 }}>ANIMA</div>

      {state ? (
        <>
          {GAUGES.map(({ key, label, color, emoji }) => (
            <Gauge key={key} value={state[key] as number} color={color} label={label} emoji={emoji} />
          ))}
          <div style={{ display: 'flex', gap: 4, marginTop: 5, flexWrap: 'wrap' }}>
            <Flag active={state.human_detected} label="人検出" activeColor="#ff6644" />
            <Flag active={state.petit_detected} label="プチ検出" activeColor="#44aaff" />
            <Flag active={state.sleep_mode}     label="スリープ" activeColor="#9966ff" />
          </div>
          <div style={{ color: 'var(--t-border2)', fontSize: 10, marginTop: 4 }}>
            gen.{state.body_generation}
          </div>
        </>
      ) : (
        <div style={{ color: 'var(--t-border2)', fontSize: 12 }}>接続待ち...</div>
      )}
    </div>
  );
}
