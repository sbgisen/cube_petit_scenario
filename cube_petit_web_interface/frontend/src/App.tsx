import { useEffect, useRef, useState } from 'react';
import { useRosConnection } from './hooks/useRosConnection';
import { OperationTab } from './components/OperationTab';
import { TalkTab } from './components/TalkTab';
import { SystemPanel } from './components/SystemPanel';
import { CustomTab } from './components/CustomTab';
import { MapTab } from './components/MapTab';
import type { RobotConfig } from './types/ros';

const DEFAULT_HOST = window.location.hostname;
const NAMESPACE = 'cube_petit_orange';

const DARK_VARS: Record<string, string> = {
  '--t-bg':          '#0d0d1a',
  '--t-surface':     '#1a1a2e',
  '--t-surface2':    '#2a2a4a',
  '--t-border':      '#333333',
  '--t-border2':     '#444444',
  '--t-text':        '#ffffff',
  '--t-text-muted':  '#cccccc',
  '--t-text-dim':    '#888888',
  '--t-input-bg':    '#1a1a2e',
  '--t-overlay':     'rgba(0,0,0,0.3)',
  '--t-knob-bg':     'rgba(255,255,255,0.1)',
  '--t-knob-border': 'rgba(255,255,255,0.3)',
  '--t-btn-ghost':   'rgba(255,255,255,0.15)',
};
const LIGHT_VARS: Record<string, string> = {
  '--t-bg':          '#f0f2f5',
  '--t-surface':     '#ffffff',
  '--t-surface2':    '#e2e5ef',
  '--t-border':      '#cccccc',
  '--t-border2':     '#bbbbbb',
  '--t-text':        '#111111',
  '--t-text-muted':  '#444444',
  '--t-text-dim':    '#777777',
  '--t-input-bg':    '#ffffff',
  '--t-overlay':     'rgba(0,0,0,0.06)',
  '--t-knob-bg':     'rgba(0,0,0,0.08)',
  '--t-knob-border': 'rgba(0,0,0,0.2)',
  '--t-btn-ghost':   'rgba(0,0,0,0.1)',
};

function applyTheme(dark: boolean) {
  const vars = dark ? DARK_VARS : LIGHT_VARS;
  Object.entries(vars).forEach(([k, v]) => document.documentElement.style.setProperty(k, v));
}

applyTheme(localStorage.getItem('theme') !== 'light');

const DEFAULT_QUICK_PHRASES = ['こんにちは', 'こっちきて', 'オレンジプチです', '仲良くしてね'];
const QUICK_PHRASES_KEY = 'quick_phrases';

function loadQuickPhrases(): string[] {
  try {
    const raw = localStorage.getItem(QUICK_PHRASES_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch { /* ignore */ }
  return [...DEFAULT_QUICK_PHRASES];
}

type Tab = 'operation' | 'talk' | 'map' | 'system' | 'custom';

const TABS: { id: Tab; label: string }[] = [
  { id: 'operation', label: '操作' },
  { id: 'talk',      label: '会話' },
  { id: 'system',    label: 'システム' },
  { id: 'custom',    label: 'カスタム会話' },
  { id: 'map',       label: 'カスタムマップ' },
];

export default function App() {
  const [host, setHost] = useState<string>(() => localStorage.getItem('robot_host') || DEFAULT_HOST);
  const [inputHost, setInputHost] = useState<string>(host);
  const inputRef = useRef<HTMLInputElement>(null);

  const robot: RobotConfig = {
    name: 'オレンジプチ',
    namespace: NAMESPACE,
    rosbridgeUrl: `ws://${host}:9090`,
  };
  const apiUrl = `http://${host}:8000`;

  const [tab, setTab] = useState<Tab>('operation');
  const { ros, status } = useRosConnection(robot.rosbridgeUrl);
  const [isDark, setIsDark] = useState(() => localStorage.getItem('theme') !== 'light');

  useEffect(() => {
    applyTheme(isDark);
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  const [rosbridgeRunning, setRosbridgeRunning] = useState(false);
  useEffect(() => {
    const poll = () =>
      fetch(`${apiUrl}/launch/status`).then(r => r.json()).then(d => setRosbridgeRunning(!!d.rosbridge)).catch(() => {});
    poll();
    const t = setInterval(poll, 3000);
    return () => clearInterval(t);
  }, [apiUrl]);
  const toggleRosbridge = async () => {
    const action = rosbridgeRunning ? 'stop' : 'start';
    await fetch(`${apiUrl}/launch/rosbridge/${action}`, { method: 'POST' }).catch(() => {});
    setTimeout(() => fetch(`${apiUrl}/launch/status`).then(r => r.json()).then(d => setRosbridgeRunning(!!d.rosbridge)).catch(() => {}), 1500);
  };

  const [quickPhrases, setQuickPhrasesState] = useState<string[]>(loadQuickPhrases);
  const setQuickPhrases = (phrases: string[]) => {
    setQuickPhrasesState(phrases);
    localStorage.setItem(QUICK_PHRASES_KEY, JSON.stringify(phrases));
  };

  const connect = () => {
    const trimmed = inputHost.trim();
    if (!trimmed) return;
    setHost(trimmed);
    localStorage.setItem('robot_host', trimmed);
    inputRef.current?.blur();
  };

  const statusColor = {
    connected: '#00cc66',
    connecting: '#ffcc00',
    disconnected: '#888',
    error: '#cc3333',
  }[status];

  const hostChanged = inputHost.trim() !== host;

  return (
    <div style={{
      height: '100dvh', background: 'var(--t-bg)', color: 'var(--t-text)',
      display: 'flex', flexDirection: 'column', fontFamily: 'sans-serif',
      padding: 0, margin: 0, boxSizing: 'border-box',
    }}>
      {/* ヘッダー */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: 'calc(env(safe-area-inset-top) + 8px) 16px 8px',
        background: 'var(--t-surface)', borderBottom: '1px solid var(--t-border)',
        flexShrink: 0,
      }}>
        {/* ロボット名 */}
        <span style={{ fontSize: 14, color: 'var(--t-text)', whiteSpace: 'nowrap' }}>
          オレンジプチ
        </span>

        {/* IP入力 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <input
            ref={inputRef}
            value={inputHost}
            onChange={e => setInputHost(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && connect()}
            placeholder="192.168.1.x"
            style={{
              width: 130, padding: '5px 8px', borderRadius: 8, fontSize: 13,
              background: 'var(--t-input-bg)', color: 'var(--t-text)',
              border: `1px solid ${hostChanged ? '#ff6600' : 'var(--t-border2)'}`,
              outline: 'none',
            }}
          />
          {hostChanged && (
            <button
              onClick={connect}
              style={{
                padding: '5px 10px', borderRadius: 8, border: 'none', cursor: 'pointer',
                background: '#ff6600', color: '#fff', fontSize: 12,
              }}
            >接続</button>
          )}
        </div>

        {/* 接続ステータス */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: statusColor }} />
          <span style={{ fontSize: 12, color: 'var(--t-text-dim)' }}>{status}</span>
        </div>

        {/* rosbridge 起動/停止 */}
        <button onClick={toggleRosbridge} style={{
          padding: '5px 12px', borderRadius: 20, border: 'none', cursor: 'pointer', fontSize: 12, flexShrink: 0,
          background: rosbridgeRunning ? 'rgba(0,204,102,0.2)' : 'rgba(204,51,51,0.2)',
          color: rosbridgeRunning ? '#00cc66' : '#cc3333',
          outline: `1px solid ${rosbridgeRunning ? '#00cc66' : '#cc3333'}`,
        }}>
          rosbridge {rosbridgeRunning ? '▶' : '■'}
        </button>

        {/* テーマ */}
        <button
          onClick={() => setIsDark(d => !d)}
          style={{
            padding: '6px 12px', borderRadius: 20, border: 'none', cursor: 'pointer',
            background: 'var(--t-surface2)', color: 'var(--t-text)', fontSize: 16,
          }}
        >
          {isDark ? '☀️' : '🌙'}
        </button>

        <div style={{ flex: 1 }} />

        {TABS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            style={{
              padding: '6px 18px', borderRadius: 20, border: 'none', cursor: 'pointer',
              background: tab === id ? '#ff6600' : 'var(--t-surface2)', color: 'var(--t-text)', fontSize: 14,
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* コンテンツ */}
      <div style={{ flex: 1, padding: 12, overflow: 'hidden', minHeight: 0 }}>
        {tab === 'operation' && <OperationTab ros={ros} namespace={robot.namespace} apiUrl={apiUrl} quickPhrases={quickPhrases} setQuickPhrases={setQuickPhrases} />}
        {tab === 'talk'      && <TalkTab      ros={ros} namespace={robot.namespace} quickPhrases={quickPhrases} setQuickPhrases={setQuickPhrases} apiUrl={apiUrl} />}
        {tab === 'system'    && <SystemPanel  namespace={robot.namespace} apiUrl={apiUrl} quickPhrases={quickPhrases} setQuickPhrases={setQuickPhrases} />}
        {tab === 'map'       && <MapTab       namespace={robot.namespace} apiUrl={apiUrl} />}
        {tab === 'custom'    && <CustomTab    apiUrl={apiUrl} quickPhrases={quickPhrases} setQuickPhrases={setQuickPhrases} />}
      </div>
    </div>
  );
}
