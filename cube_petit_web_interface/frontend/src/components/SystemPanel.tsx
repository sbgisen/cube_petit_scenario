import { useEffect, useState } from 'react';

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

interface DeviceStatus {
  ip: string[];
  can0: boolean;
  can_stale?: boolean;
  can_errors?: number;
  lidar: boolean;
  imu: boolean;
  canable: boolean;
  realsense: boolean;
  oak: boolean;
}

interface Props {
  namespace: string;
  apiUrl: string;
  quickPhrases: string[];
  setQuickPhrases: (phrases: string[]) => void;
}

const cardStyle: React.CSSProperties = {
  background: 'var(--t-surface)',
  border: '1px solid var(--t-border)',
  borderRadius: 12,
  padding: '14px 16px',
  overflow: 'auto',
};

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ color: 'var(--t-text-muted)', fontSize: 13, fontWeight: 'bold', marginBottom: 10 }}>
      {children}
    </div>
  );
}

function Dot({ ok, dim }: { ok: boolean; dim?: boolean }) {
  return (
    <div style={{
      width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
      background: ok ? '#00cc66' : dim ? '#555' : '#cc3333',
      boxShadow: ok ? '0 0 4px #00cc6688' : 'none',
    }} />
  );
}

function DeviceRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <Dot ok={ok} />
      <span style={{ color: 'var(--t-text)', fontSize: 13 }}>{label}</span>
    </div>
  );
}

function LaunchRow({ label, running, onStart, onStop }: { label: string; running: boolean; onStart: () => void; onStop: () => void }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', borderRadius: 8, background: 'var(--t-overlay)' }}>
      <Dot ok={running} dim />
      <span style={{ color: 'var(--t-text)', fontSize: 13, flex: 1 }}>{label}</span>
      <button onClick={onStart} disabled={running}
        style={{ padding: '4px 12px', borderRadius: 12, border: 'none', cursor: running ? 'not-allowed' : 'pointer',
          background: running ? 'var(--t-border)' : '#00cc66', color: 'var(--t-text)', fontSize: 12, opacity: running ? 0.5 : 1 }}>起動</button>
      <button onClick={onStop} disabled={!running}
        style={{ padding: '4px 12px', borderRadius: 12, border: 'none', cursor: !running ? 'not-allowed' : 'pointer',
          background: !running ? 'var(--t-border)' : '#cc3333', color: 'var(--t-text)', fontSize: 12, opacity: !running ? 0.5 : 1 }}>停止</button>
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
        style={{ width: '100%', accentColor: 'var(--t-accent)' }}
      />
    </div>
  );
}

type LaunchTarget = 'bringup' | 'anima' | 'demo' | 'create_map' | 'navigation';

const SIMPLE_TARGETS: LaunchTarget[] = ['bringup', 'anima', 'demo', 'create_map'];

export function SystemPanel({ namespace, apiUrl }: Props) {
  const [nodeList, setNodeList] = useState<string[]>([]);
  const [launchStatus, setLaunchStatus] = useState<Record<string, boolean>>({});
  const [speakerVol, setSpeakerVol] = useState(80);
  const [micVol, setMicVol] = useState(60);
  const [devices, setDevices] = useState<DeviceStatus | null>(null);
  const [maps, setMaps] = useState<string[]>([]);
  const [selectedMap, setSelectedMap] = useState('');
  const [selectedKeeput, setSelectedKeeput] = useState('');
  const [cmdLog, setCmdLog] = useState<{ time: string; msg: string; ok: boolean }[]>([]);

  useEffect(() => {
    const poll = () => {
      fetch(`${apiUrl}/ros/nodes`)
        .then(r => r.json())
        .then(d => setNodeList(d.nodes || []))
        .catch(() => {});
    };
    poll();
    const t = setInterval(poll, 3000);
    return () => clearInterval(t);
  }, [apiUrl]);

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

  useEffect(() => {
    const poll = () => {
      fetch(`${apiUrl}/system/devices`)
        .then(r => r.json())
        .then(d => setDevices(d))
        .catch(() => {});
    };
    poll();
    const t = setInterval(poll, 5000);
    return () => clearInterval(t);
  }, [apiUrl]);

  useEffect(() => {
    fetch(`${apiUrl}/audio/volume`)
      .then(r => r.json())
      .then(d => {
        if (d.speaker >= 0) setSpeakerVol(d.speaker);
        if (d.mic >= 0) setMicVol(d.mic);
      })
      .catch(() => {});
  }, [apiUrl]);

  useEffect(() => {
    fetch(`${apiUrl}/map/list`)
      .then(r => r.json())
      .then(d => {
        const list: string[] = d.maps || [];
        setMaps(list);
        if (list.length > 0) { setSelectedMap(list[0]); setSelectedKeeput(list[0]); }
      })
      .catch(() => {});
  }, [apiUrl]);

  const isAlive = (shortName: string) => nodeList.some(n => n.includes(shortName));

  const launchAction = async (target: LaunchTarget, action: 'start' | 'stop') => {
    let url = `${apiUrl}/launch/${target}/${action}`;
    if (action === 'start' && target === 'navigation') {
      const params = new URLSearchParams();
      if (selectedMap) { params.set('map', selectedMap); localStorage.setItem('nav_selected_map', selectedMap); }
      if (selectedKeeput) params.set('keepout', selectedKeeput);
      url += `?${params}`;
    }
    const res = await fetch(url, { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    const time = new Date().toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const label = action === 'start' ? `起動: ${target}` : `停止: ${target}`;
    const detail = data.message || '';
    setCmdLog(prev => [{ time, msg: `${label}${detail ? ' — ' + detail : ''}`, ok: !!data.ok }, ...prev].slice(0, 50));
    fetch(`${apiUrl}/launch/status`).then(r => r.json()).then(setLaunchStatus).catch(() => {});
  };

  const applyVolume = (type: 'speaker' | 'mic', value: number) => {
    fetch(`${apiUrl}/audio/volume?type=${type}&value=${value}`, { method: 'POST' }).catch(() => {});
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 2fr', gridTemplateRows: '1fr 1fr', gap: 16, padding: 8, height: '100%', overflow: 'hidden' }}>

      {/* 起動管理: 左上 2列 */}
      <div style={{ ...cardStyle, gridColumn: '1 / 3', gridRow: '1' }}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 10 }}>
          <div style={{ color: 'var(--t-text-muted)', fontSize: 13, fontWeight: 'bold' }}>起動管理</div>
          <div style={{ flex: 1 }} />
          <button
            onClick={() => fetch(`${apiUrl}/launch/kill_all`, { method: 'POST' }).then(() =>
              fetch(`${apiUrl}/launch/status`).then(r => r.json()).then(setLaunchStatus)
            )}
            style={{
              padding: '4px 12px', borderRadius: 12, border: 'none', cursor: 'pointer',
              background: '#cc3333', color: '#fff', fontSize: 12, marginBottom: 2,
            }}
          >ROS一括停止</button>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {SIMPLE_TARGETS.map(target => (
            <LaunchRow key={target} label={target} running={!!launchStatus[target]}
              onStart={() => launchAction(target, 'start')}
              onStop={() => launchAction(target, 'stop')} />
          ))}

          {/* navigation: マップ選択付き */}
          <div style={{ padding: '8px 10px', borderRadius: 8, background: 'var(--t-overlay)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <Dot ok={!!launchStatus['navigation']} dim />
              <span style={{ color: 'var(--t-text)', fontSize: 13, flex: 1 }}>navigation</span>
              <button onClick={() => launchAction('navigation', 'start')} disabled={!!launchStatus['navigation']}
                style={{ padding: '4px 12px', borderRadius: 12, border: 'none', cursor: launchStatus['navigation'] ? 'not-allowed' : 'pointer',
                  background: launchStatus['navigation'] ? 'var(--t-border)' : '#00cc66',
                  color: 'var(--t-text)', fontSize: 12, opacity: launchStatus['navigation'] ? 0.5 : 1 }}>起動</button>
              <button onClick={() => launchAction('navigation', 'stop')} disabled={!launchStatus['navigation']}
                style={{ padding: '4px 12px', borderRadius: 12, border: 'none', cursor: !launchStatus['navigation'] ? 'not-allowed' : 'pointer',
                  background: !launchStatus['navigation'] ? 'var(--t-border)' : '#cc3333',
                  color: 'var(--t-text)', fontSize: 12, opacity: !launchStatus['navigation'] ? 0.5 : 1 }}>停止</button>
            </div>
            <div style={{ display: 'flex', gap: 8, paddingLeft: 16 }}>
              <div style={{ flex: 1 }}>
                <div style={{ color: 'var(--t-text-dim)', fontSize: 11, marginBottom: 3 }}>map</div>
                <select value={selectedMap} onChange={e => setSelectedMap(e.target.value)}
                  style={{ width: '100%', background: 'var(--t-input-bg)', color: 'var(--t-text)',
                    border: '1px solid var(--t-border2)', borderRadius: 6, padding: '4px 6px', fontSize: 12 }}>
                  {maps.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ color: 'var(--t-text-dim)', fontSize: 11, marginBottom: 3 }}>keepout</div>
                <select value={selectedKeeput} onChange={e => setSelectedKeeput(e.target.value)}
                  style={{ width: '100%', background: 'var(--t-input-bg)', color: 'var(--t-text)',
                    border: '1px solid var(--t-border2)', borderRadius: 6, padding: '4px 6px', fontSize: 12 }}>
                  <option value="">なし</option>
                  {maps.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 音量: 3列目 */}
      <div style={{ ...cardStyle, gridColumn: '3 / 4', gridRow: '1' }}>
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

      {/* コマンドログ: 4列目 */}
      <div style={{ ...cardStyle, gridColumn: '4 / 5', gridRow: '1', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <SectionTitle>コマンドログ</SectionTitle>
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {cmdLog.length === 0 && <div style={{ fontSize: 11, color: 'var(--t-text-dim)' }}>なし</div>}
          {cmdLog.map((entry, i) => (
            <div key={i} style={{ fontSize: 11, borderRadius: 6, padding: '4px 6px', background: 'var(--t-overlay)', lineHeight: 1.5 }}>
              <span style={{ color: 'var(--t-text-dim)', marginRight: 6 }}>{entry.time}</span>
              <span style={{ color: entry.ok ? 'var(--t-text)' : '#cc4444' }}>{entry.msg}</span>
            </div>
          ))}
        </div>
      </div>

      {/* デバイス: 左下 1列 */}
      <div style={{ ...cardStyle, gridColumn: '1 / 2', gridRow: '2' }}>
        <SectionTitle>デバイス</SectionTitle>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {devices && (
            <div style={{ color: 'var(--t-text-dim)', fontSize: 11, marginBottom: 4 }}>
              {devices.ip.join('  ')}
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Dot ok={devices?.can0 ?? false} />
            <span style={{ color: 'var(--t-text)', fontSize: 13 }}>CAN0</span>
            {devices?.can0 && devices?.can_stale && (
              <span style={{ fontSize: 11, color: '#ffaa00', background: 'rgba(255,170,0,0.15)', borderRadius: 4, padding: '1px 6px' }}>受信停止</span>
            )}
            {devices?.can0 && !devices?.can_stale && (devices?.can_errors ?? 0) > 0 && (
              <span style={{ fontSize: 11, color: '#ff6644', background: 'rgba(255,100,68,0.15)', borderRadius: 4, padding: '1px 6px' }}>エラー {devices.can_errors}</span>
            )}
          </div>
          <DeviceRow label="LiDAR"     ok={devices?.lidar     ?? false} />
          <DeviceRow label="IMU"       ok={devices?.imu       ?? false} />
          <DeviceRow label="CANable"   ok={devices?.canable   ?? false} />
          <DeviceRow label="RealSense" ok={devices?.realsense ?? false} />
          <DeviceRow label="OAK"       ok={devices?.oak       ?? false} />
        </div>
      </div>

      {/* ノード監視: デバイスの右 3列 */}
      <div style={{ ...cardStyle, gridColumn: '2 / 5', gridRow: '2' }}>
        <SectionTitle>ノード監視 <span style={{ fontSize: 11, color: 'var(--t-text-dim)', fontWeight: 'normal' }}>({namespace})</span></SectionTitle>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 24px' }}>
          {WATCHED_NODES.map(node => (
            <div key={node} style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 200 }}>
              <Dot ok={isAlive(node)} />
              <span style={{ color: 'var(--t-text)', fontSize: 13 }}>{node}</span>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
