import { useEffect, useState } from 'react';
import * as ROSLIB from 'roslib';

const WATCHED_NODES = [
  'ldlidar_publisher_ld06',
  'diff_drive_controller',
  'socket_can_receiver',
  'socket_can_sender',
  'speech_action_server',
  'text_to_jtalk',
  'realtime_gpt_chat',
  'respeaker_node',
  'robot_state_publisher',
];

interface Props {
  ros: ROSLIB.Ros | null;
  namespace: string;
  apiUrl: string;
  quickPhrases: string[];
  setQuickPhrases: (phrases: string[]) => void;
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ color: 'var(--t-text-muted)', fontSize: 14, fontWeight: 'bold', marginBottom: 8 }}>
      {children}
    </div>
  );
}

function VolumeSlider({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ color: 'var(--t-text)', fontSize: 13 }}>{label}</span>
        <span style={{ color: 'var(--t-text-muted)', fontSize: 13 }}>{value}%</span>
      </div>
      <input
        type="range" min={0} max={100} value={value}
        onChange={e => onChange(Number(e.target.value))}
        style={{ width: '100%', accentColor: '#ff6600' }}
      />
    </div>
  );
}

export function SystemPanel({ ros, namespace, apiUrl }: Props) {
  const [nodeList, setNodeList] = useState<string[]>([]);
  const [launchStatus, setLaunchStatus] = useState<Record<string, boolean>>({ bringup: false, demo: false });
  const [speakerVol, setSpeakerVol] = useState(80);
  const [micVol, setMicVol] = useState(60);

  // ノード一覧ポーリング
  useEffect(() => {
    if (!ros) return;
    const poll = () => ros.getNodes((nodes: string[]) => setNodeList(nodes));
    poll();
    const t = setInterval(poll, 3000);
    return () => clearInterval(t);
  }, [ros]);

  // 起動状態ポーリング
  useEffect(() => {
    const poll = () => {
      fetch(`${apiUrl}/launch/status`)
        .then(r => r.json())
        .then(d => setLaunchStatus(d))
        .catch(() => {});
    };
    poll();
    const t = setInterval(poll, 3000);
    return () => clearInterval(t);
  }, [apiUrl]);

  // 音量取得
  useEffect(() => {
    fetch(`${apiUrl}/audio/volume`)
      .then(r => r.json())
      .then(d => {
        if (d.speaker >= 0) setSpeakerVol(d.speaker);
        if (d.mic >= 0) setMicVol(d.mic);
      })
      .catch(() => {});
  }, [apiUrl]);

  const isAlive = (shortName: string) => nodeList.some(n => n.includes(shortName));

  const launchAction = async (target: 'bringup' | 'demo', action: 'start' | 'stop') => {
    await fetch(`${apiUrl}/launch/${target}/${action}`, { method: 'POST' });
    fetch(`${apiUrl}/launch/status`).then(r => r.json()).then(setLaunchStatus).catch(() => {});
  };

  const applyVolume = (type: 'speaker' | 'mic', value: number) => {
    fetch(`${apiUrl}/audio/volume?type=${type}&value=${value}`, { method: 'POST' }).catch(() => {});
  };

  return (
    <div style={{ display: 'flex', gap: 20, padding: 8, height: '100%', overflow: 'auto', flexWrap: 'wrap', alignContent: 'flex-start' }}>

      {/* ノード監視 */}
      <div style={{ minWidth: 220 }}>
        <SectionTitle>ノード監視 <span style={{ fontSize: 11, color: 'var(--t-text-dim)' }}>({namespace})</span></SectionTitle>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {WATCHED_NODES.map(node => (
            <div key={node} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{
                width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                background: isAlive(node) ? '#00cc66' : '#cc3333',
                boxShadow: isAlive(node) ? '0 0 4px #00cc6688' : 'none',
              }} />
              <span style={{ color: 'var(--t-text)', fontSize: 13 }}>{node}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 起動管理 */}
      <div style={{ minWidth: 220 }}>
        <SectionTitle>起動管理</SectionTitle>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {(['bringup', 'demo'] as const).map(target => (
            <div key={target} style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '8px 10px', borderRadius: 8, background: 'var(--t-overlay)',
            }}>
              <div style={{
                width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                background: launchStatus[target] ? '#00cc66' : '#555',
                boxShadow: launchStatus[target] ? '0 0 4px #00cc6688' : 'none',
              }} />
              <span style={{ color: 'var(--t-text)', fontSize: 13, flex: 1 }}>{target}</span>
              <button
                onClick={() => launchAction(target, 'start')}
                disabled={launchStatus[target]}
                style={{
                  padding: '4px 12px', borderRadius: 12, border: 'none', cursor: launchStatus[target] ? 'not-allowed' : 'pointer',
                  background: launchStatus[target] ? 'var(--t-border)' : '#00cc66',
                  color: 'var(--t-text)', fontSize: 12, opacity: launchStatus[target] ? 0.5 : 1,
                }}
              >起動</button>
              <button
                onClick={() => launchAction(target, 'stop')}
                disabled={!launchStatus[target]}
                style={{
                  padding: '4px 12px', borderRadius: 12, border: 'none', cursor: !launchStatus[target] ? 'not-allowed' : 'pointer',
                  background: !launchStatus[target] ? 'var(--t-border)' : '#cc3333',
                  color: 'var(--t-text)', fontSize: 12, opacity: !launchStatus[target] ? 0.5 : 1,
                }}
              >停止</button>
            </div>
          ))}
        </div>
      </div>

      {/* 音量 */}
      <div style={{ minWidth: 240 }}>
        <SectionTitle>音量</SectionTitle>
        <VolumeSlider
          label="スピーカー"
          value={speakerVol}
          onChange={v => { setSpeakerVol(v); applyVolume('speaker', v); }}
        />
        <VolumeSlider
          label="マイク"
          value={micVol}
          onChange={v => { setMicVol(v); applyVolume('mic', v); }}
        />
      </div>

    </div>
  );
}
