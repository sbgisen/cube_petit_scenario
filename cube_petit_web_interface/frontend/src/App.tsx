import { useEffect, useState } from 'react';
import { useRosConnection } from './hooks/useRosConnection';
import { OperationTab } from './components/OperationTab';
import { TalkTab } from './components/TalkTab';
import { SystemPanel } from './components/SystemPanel';
import type { RobotConfig } from './types/ros';

const HOST = window.location.hostname;

const ROBOTS: RobotConfig[] = [
  {
    name: 'オレンジプチ',
    namespace: 'cube_petit_orange',
    rosbridgeUrl: `ws://${HOST}:9090`,
  },
];

const API_URL = `http://${HOST}:8000`;

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

// 初期テーマを同期適用（白フラッシュ防止）
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

type Tab = 'operation' | 'talk' | 'system';

const TABS: { id: Tab; label: string }[] = [
  { id: 'operation', label: '操作' },
  { id: 'talk',      label: '会話' },
  { id: 'system',    label: 'システム' },
];

export default function App() {
  const [selectedRobot, setSelectedRobot] = useState<RobotConfig>(ROBOTS[0]);
  const [tab, setTab] = useState<Tab>('operation');
  const { ros, status } = useRosConnection(selectedRobot.rosbridgeUrl);
  const [isDark, setIsDark] = useState(() => localStorage.getItem('theme') !== 'light');

  useEffect(() => {
    applyTheme(isDark);
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
  }, [isDark]);
  const [quickPhrases, setQuickPhrasesState] = useState<string[]>(loadQuickPhrases);

  const setQuickPhrases = (phrases: string[]) => {
    setQuickPhrasesState(phrases);
    localStorage.setItem(QUICK_PHRASES_KEY, JSON.stringify(phrases));
  };

  const statusColor = {
    connected: '#00cc66',
    connecting: '#ffcc00',
    disconnected: '#888',
    error: '#cc3333',
  }[status];

  return (
    <div style={{
      height: '100dvh', background: 'var(--t-bg)', color: 'var(--t-text)',
      display: 'flex', flexDirection: 'column', fontFamily: 'sans-serif',
      padding: 0, margin: 0, boxSizing: 'border-box',
    }}>
      {/* ヘッダー */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: 'calc(env(safe-area-inset-top) + 8px) 16px 8px', background: 'var(--t-surface)', borderBottom: '1px solid var(--t-border)',
        flexShrink: 0,
      }}>
        <select
          value={selectedRobot.namespace}
          onChange={(e) => {
            const r = ROBOTS.find((r) => r.namespace === e.target.value);
            if (r) setSelectedRobot(r);
          }}
          style={{
            background: 'var(--t-surface2)', color: 'var(--t-text)', border: '1px solid var(--t-border2)',
            borderRadius: 8, padding: '6px 10px', fontSize: 14,
          }}
        >
          {ROBOTS.map((r) => (
            <option key={r.namespace} value={r.namespace}>{r.name}</option>
          ))}
        </select>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6, width: 110, flexShrink: 0 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: statusColor, flexShrink: 0 }} />
          <span style={{ fontSize: 12, color: 'var(--t-text-dim)' }}>{status}</span>
        </div>

        <button
          onClick={() => setIsDark((d) => !d)}
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
        {tab === 'operation' && <OperationTab ros={ros} namespace={selectedRobot.namespace} quickPhrases={quickPhrases} setQuickPhrases={setQuickPhrases} />}
        {tab === 'talk'      && <TalkTab      ros={ros} namespace={selectedRobot.namespace} quickPhrases={quickPhrases} setQuickPhrases={setQuickPhrases} />}
        {tab === 'system'    && <SystemPanel  ros={ros} namespace={selectedRobot.namespace} apiUrl={API_URL} quickPhrases={quickPhrases} setQuickPhrases={setQuickPhrases} />}
      </div>
    </div>
  );
}
