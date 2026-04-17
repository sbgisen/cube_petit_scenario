import { useMemo } from 'react';
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

interface RosString {
  data: string;
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
    <div style={{ marginBottom: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
        <span style={{ color: 'var(--t-text-dim)', fontSize: 11 }}>{emoji} {label}</span>
        <span style={{ color, fontSize: 11, fontWeight: 'bold' }}>{pct.toFixed(1)}</span>
      </div>
      <div style={{ background: '#222', borderRadius: 4, height: 8, overflow: 'hidden' }}>
        <div style={{
          width: `${pct}%`, height: '100%', background: color,
          borderRadius: 4, transition: 'width 0.4s ease',
          boxShadow: `0 0 6px ${color}88`,
        }} />
      </div>
    </div>
  );
}

function Flag({ active, label, activeColor = '#00cc66' }: { active: boolean; label: string; activeColor?: string }) {
  return (
    <div style={{
      padding: '3px 8px', borderRadius: 10, fontSize: 11,
      background: active ? `${activeColor}33` : '#222',
      color: active ? activeColor : '#555',
      border: `1px solid ${active ? activeColor : 'var(--t-border)'}`,
    }}>
      {label}
    </div>
  );
}

export function AnimaPanel({ ros, namespace }: Props) {
  const raw = useRosTopic<RosString>(
    ros,
    `/${namespace}/internal_state_json`,
    'std_msgs/String',
    true,
  );

  const state = useMemo<InternalState | null>(() => {
    if (!raw) return null;
    try { return JSON.parse(raw.data) as InternalState; }
    catch { return null; }
  }, [raw]);

  return (
    <div style={{
      background: '#16162a', borderRadius: 8, padding: '10px 12px',
      border: '1px solid var(--t-surface2)', flexShrink: 0,
    }}>
      <div style={{ color: '#666', fontSize: 11, marginBottom: 8, letterSpacing: 1 }}>ANIMA</div>

      {state ? (
        <>
          {GAUGES.map(({ key, label, color, emoji }) => (
            <Gauge key={key} value={state[key] as number} color={color} label={label} emoji={emoji} />
          ))}
          <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
            <Flag active={state.human_detected} label="人検出" activeColor="#ff6644" />
            <Flag active={state.petit_detected} label="プチ検出" activeColor="#44aaff" />
            <Flag active={state.sleep_mode}     label="スリープ" activeColor="#9966ff" />
          </div>
          <div style={{ color: 'var(--t-border2)', fontSize: 10, marginTop: 6 }}>
            gen.{state.body_generation}
          </div>
        </>
      ) : (
        <div style={{ color: 'var(--t-border2)', fontSize: 12 }}>接続待ち...</div>
      )}
    </div>
  );
}
