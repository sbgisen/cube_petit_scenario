import { useEffect, useState } from 'react';
import { Icon } from './Icon';

// 健全性チェック対象ノード一覧(bringup/demoのグループ分けはせず、丸の位置を揃えて
// 1本のグリッドで表示する)
const WATCHED_NODES: string[] = [
  'robot_state_publisher',
  'ldlidar_publisher_ld06',
  'diff_drive_controller',
  'socket_can_receiver',
  'socket_can_sender',
  'respeaker_node',
  'realtime_gpt_chat',
  'speech_action_server',
  'text_to_jtalk',
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

type LaunchTarget = 'bringup' | 'anima' | 'demo' | 'create_map' | 'navigation' | 'shared_controller_hub';

const SIMPLE_TARGETS: LaunchTarget[] = ['bringup', 'anima', 'demo'];

export function SystemPanel({ namespace, apiUrl }: Props) {
  const [nodeList, setNodeList] = useState<string[]>([]);
  const [launchStatus, setLaunchStatus] = useState<Record<string, boolean>>({});
  const [speakerVol, setSpeakerVol] = useState(80);
  const [micVol, setMicVol] = useState(60);
  const [devices, setDevices] = useState<DeviceStatus | null>(null);
  const [maps, setMaps] = useState<string[]>([]);
  const [selectedMap, setSelectedMap] = useState('');
  // create_map起動時、既存マップの続きからSLAMを再開する場合に選ぶ(空="新規作成")
  const [continueMap, setContinueMap] = useState('');
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

    // create_mapを「続きから」で起動した場合、slam_toolboxが立ち上がるのを待ってから
    // deserialize_mapを呼んでポーズグラフを読み込む(新規作成時は何もしない)
    if (action === 'start' && target === 'create_map' && continueMap && data.ok) {
      setTimeout(async () => {
        const r = await fetch(`${apiUrl}/map/slam/continue`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ map_name: continueMap }),
        }).then(r2 => r2.json()).catch(() => ({ ok: false, message: '通信エラー' }));
        const t2 = new Date().toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        setCmdLog(prev => [{ time: t2, msg: `マップ継続(${continueMap}) — ${r.message ?? ''}`, ok: !!r.ok }, ...prev].slice(0, 50));
      }, 5000);
    }
  };

  const applyVolume = (type: 'speaker' | 'mic', value: number) => {
    fetch(`${apiUrl}/audio/volume?type=${type}&value=${value}`, { method: 'POST' }).catch(() => {});
  };

  // コントローラのBluetooth接続状況。ペアリングボタンの表示・接続済み表示に使う
  const [connectedControllers, setConnectedControllers] = useState<{ mac: string; name: string; battery: number | null; connected: boolean }[]>([]);
  const [pairing, setPairing] = useState(false);
  useEffect(() => {
    const poll = () =>
      fetch(`${apiUrl}/system/bluetooth/controllers`).then(r => r.json())
        .then(d => setConnectedControllers(d.connected || [])).catch(() => {});
    poll();
    const t = setInterval(poll, 5000);
    return () => clearInterval(t);
  }, [apiUrl]);
  const disconnectController = async (mac: string) => {
    const res = await fetch(`${apiUrl}/system/bluetooth/disconnect?mac=${encodeURIComponent(mac)}`, { method: 'POST' })
      .then(r => r.json()).catch(() => ({ ok: false, message: '通信エラー' }));
    const time = new Date().toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setCmdLog(prev => [{ time, msg: `コントローラ切断 — ${res.message ?? ''}`, ok: !!res.ok }, ...prev].slice(0, 50));
    fetch(`${apiUrl}/system/bluetooth/controllers`).then(r => r.json())
      .then(d => setConnectedControllers(d.connected || [])).catch(() => {});
  };
  const pairController = async () => {
    setPairing(true);
    const res = await fetch(`${apiUrl}/system/bluetooth/pair`, { method: 'POST' })
      .then(r => r.json()).catch(() => ({ ok: false, message: '通信エラー' }));
    const time = new Date().toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setCmdLog(prev => [{ time, msg: `コントローラペアリング — ${res.message ?? ''}`, ok: !!res.ok }, ...prev].slice(0, 50));
    setPairing(false);
    fetch(`${apiUrl}/system/bluetooth/controllers`).then(r => r.json())
      .then(d => setConnectedControllers(d.connected || [])).catch(() => {});
  };

  const [canRestarting, setCanRestarting] = useState(false);
  const restartCan = async () => {
    setCanRestarting(true);
    const res = await fetch(`${apiUrl}/system/can/restart`, { method: 'POST' })
      .then(r => r.json()).catch(() => ({ ok: false, message: '通信エラー' }));
    const time = new Date().toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setCmdLog(prev => [{ time, msg: `CAN0再起動 — ${res.message ?? ''}`, ok: !!res.ok }, ...prev].slice(0, 50));
    setCanRestarting(false);
    fetch(`${apiUrl}/system/devices`).then(r => r.json()).then(setDevices).catch(() => {});
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 2fr', gridTemplateRows: '2fr 1fr', gap: 16, padding: 8, height: '100%', overflow: 'hidden' }}>

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

          {/* create_map: 続きから選択付き */}
          <div style={{ padding: '8px 10px', borderRadius: 8, background: 'var(--t-overlay)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <Dot ok={!!launchStatus['create_map']} dim />
              <span style={{ color: 'var(--t-text)', fontSize: 13, flex: 1 }}>create_map</span>
              <button onClick={() => launchAction('create_map', 'start')} disabled={!!launchStatus['create_map']}
                style={{ padding: '4px 12px', borderRadius: 12, border: 'none', cursor: launchStatus['create_map'] ? 'not-allowed' : 'pointer',
                  background: launchStatus['create_map'] ? 'var(--t-border)' : '#00cc66',
                  color: 'var(--t-text)', fontSize: 12, opacity: launchStatus['create_map'] ? 0.5 : 1 }}>起動</button>
              <button onClick={() => launchAction('create_map', 'stop')} disabled={!launchStatus['create_map']}
                style={{ padding: '4px 12px', borderRadius: 12, border: 'none', cursor: !launchStatus['create_map'] ? 'not-allowed' : 'pointer',
                  background: !launchStatus['create_map'] ? 'var(--t-border)' : '#cc3333',
                  color: 'var(--t-text)', fontSize: 12, opacity: !launchStatus['create_map'] ? 0.5 : 1 }}>停止</button>
            </div>
            <div style={{ paddingLeft: 16 }}>
              <div style={{ color: 'var(--t-text-dim)', fontSize: 11, marginBottom: 3 }}>続きから(空=新規作成)</div>
              <select value={continueMap} onChange={e => setContinueMap(e.target.value)}
                style={{ width: '100%', background: 'var(--t-input-bg)', color: 'var(--t-text)',
                  border: '1px solid var(--t-border2)', borderRadius: 6, padding: '4px 6px', fontSize: 12 }}>
                <option value="">新規作成</option>
                {maps.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          </div>

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

          {/* shared_controller_hub: 1台のコントローラを複数機で使い回す仕組みのhub役 */}
          <div style={{ padding: '8px 10px', borderRadius: 8, background: 'var(--t-overlay)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <Dot ok={!!launchStatus['shared_controller_hub']} dim />
              <span style={{ color: 'var(--t-text)', fontSize: 13, flex: 1 }}>共有コントローラ(hub)</span>
              <button onClick={() => launchAction('shared_controller_hub', 'start')} disabled={!!launchStatus['shared_controller_hub']}
                style={{ padding: '4px 12px', borderRadius: 12, border: 'none', cursor: launchStatus['shared_controller_hub'] ? 'not-allowed' : 'pointer',
                  background: launchStatus['shared_controller_hub'] ? 'var(--t-border)' : '#00cc66',
                  color: 'var(--t-text)', fontSize: 12, opacity: launchStatus['shared_controller_hub'] ? 0.5 : 1 }}>起動</button>
              <button onClick={() => launchAction('shared_controller_hub', 'stop')} disabled={!launchStatus['shared_controller_hub']}
                style={{ padding: '4px 12px', borderRadius: 12, border: 'none', cursor: !launchStatus['shared_controller_hub'] ? 'not-allowed' : 'pointer',
                  background: !launchStatus['shared_controller_hub'] ? 'var(--t-border)' : '#cc3333',
                  color: 'var(--t-text)', fontSize: 12, opacity: !launchStatus['shared_controller_hub'] ? 0.5 : 1 }}>停止</button>
            </div>
            <div style={{ paddingLeft: 16, color: 'var(--t-text-dim)', fontSize: 11, lineHeight: 1.6 }}>
              <div>この機体に接続したコントローラで他の機体を操作します(hub役)。</div>
              <div>この機体は常に他機から操作を受け付けています(receiver常時稼働中)。</div>
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

        <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--t-border)' }}>
          <div style={{ color: 'var(--t-text-muted)', fontSize: 12, marginBottom: 6 }}>コントローラ</div>
          {connectedControllers.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 8 }}>
              {connectedControllers.map(c => (
                <div key={c.mac} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Dot ok={c.connected} />
                  <span style={{ color: 'var(--t-text)', fontSize: 12, flex: 1 }}>
                    {c.name}{!c.connected && <span style={{ color: 'var(--t-text-dim)' }}>(ペア済み・未接続)</span>}
                  </span>
                  {c.battery !== null && (
                    <span style={{ display: 'flex', alignItems: 'center', gap: 2, color: 'var(--t-text-dim)', fontSize: 11 }}>
                      <Icon name="battery_full" size={13} />{c.battery}%
                    </span>
                  )}
                  <button onClick={() => disconnectController(c.mac)} title="切断" style={{
                    padding: '2px 8px', borderRadius: 10, border: 'none', cursor: 'pointer',
                    background: 'var(--t-border)', color: 'var(--t-text)', fontSize: 10,
                  }}>切断</button>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: 11, color: 'var(--t-text-dim)', marginBottom: 8 }}>未接続</div>
          )}
          <button
            onClick={pairController}
            disabled={pairing}
            title="コントローラをペアリングモード(PSボタン+SHAREボタン長押し)にしてから押してください"
            style={{
              display: 'flex', alignItems: 'center', gap: 4, padding: '4px 12px', borderRadius: 12, border: 'none',
              cursor: pairing ? 'not-allowed' : 'pointer', fontSize: 12,
              background: pairing ? 'var(--t-border)' : '#0088ff', color: '#fff', opacity: pairing ? 0.6 : 1,
            }}
          >
            <Icon name="bluetooth" size={14} />
            {pairing ? 'ペアリング中…' : 'コントローラ接続'}
          </button>
        </div>
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
      <div style={{ ...cardStyle, gridColumn: '1 / 2', gridRow: '2', overflow: 'auto' }}>
        <SectionTitle>デバイス</SectionTitle>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {devices && (
            <div style={{ color: 'var(--t-text-dim)', fontSize: 11 }}>
              {devices.ip.join('  ')}
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <Dot ok={devices?.can0 ?? false} />
            <span style={{ color: 'var(--t-text)', fontSize: 13 }}>CAN0</span>
            {devices?.can0 && devices?.can_stale && (
              <span style={{ fontSize: 11, color: '#ffaa00', background: 'rgba(255,170,0,0.15)', borderRadius: 4, padding: '1px 6px' }}>受信停止</span>
            )}
            {devices?.can0 && !devices?.can_stale && (devices?.can_errors ?? 0) > 0 && (
              <span style={{ fontSize: 11, color: '#ff6644', background: 'rgba(255,100,68,0.15)', borderRadius: 4, padding: '1px 6px' }}>エラー {devices.can_errors}</span>
            )}
            <div style={{ flex: 1 }} />
            <button
              onClick={restartCan}
              disabled={canRestarting}
              title="Canableが止まっている・CAN0が受信停止のときに再起動します(can@ttyCANable.service)"
              style={{
                display: 'flex', alignItems: 'center', gap: 4, padding: '3px 10px', borderRadius: 10, border: 'none',
                cursor: canRestarting ? 'not-allowed' : 'pointer', fontSize: 11,
                background: (!devices?.can0 || devices?.can_stale) ? '#cc3333' : 'var(--t-border)',
                color: '#fff', opacity: canRestarting ? 0.6 : 1,
              }}
            >
              <Icon name="restart_alt" size={13} />
              {canRestarting ? '再起動中...' : 'CAN再起動'}
            </button>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 18px' }}>
            <DeviceRow label="LiDAR"     ok={devices?.lidar     ?? false} />
            <DeviceRow label="IMU"       ok={devices?.imu       ?? false} />
            <DeviceRow label="CANable"   ok={devices?.canable   ?? false} />
            <DeviceRow label="RealSense" ok={devices?.realsense ?? false} />
            <DeviceRow label="OAK"       ok={devices?.oak       ?? false} />
          </div>
        </div>
      </div>

      {/* ノード監視: デバイスの右 3列。グリッドで丸の位置を縦に揃える */}
      <div style={{ ...cardStyle, gridColumn: '2 / 5', gridRow: '2', overflow: 'auto' }}>
        <SectionTitle>ノード監視 <span style={{ fontSize: 11, color: 'var(--t-text-dim)', fontWeight: 'normal' }}>({namespace})</span></SectionTitle>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: '6px 18px' }}>
          {WATCHED_NODES.map(node => (
            <div key={node} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Dot ok={isAlive(node)} />
              <span style={{ color: 'var(--t-text)', fontSize: 12 }}>{node}</span>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
