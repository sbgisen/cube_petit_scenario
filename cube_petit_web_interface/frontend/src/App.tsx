import { useEffect, useRef, useState } from 'react';
import { useRosConnection } from './hooks/useRosConnection';
import { OperationTab } from './components/OperationTab';
import { TalkTab } from './components/TalkTab';
import { SystemPanel } from './components/SystemPanel';
import { CustomTab } from './components/CustomTab';
import { MapTab } from './components/MapTab';
import { FleetDashboard } from './components/FleetDashboard';
import { RobotPicker, nicknameForRobot, colorForRobot } from './components/RobotPicker';
import { Icon } from './components/Icon';
import type { RobotConfig } from './types/ros';

const DEFAULT_HOST = window.location.hostname;

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

// アクセントカラー: 接続中ロボットの色(RobotPicker.ROBOT_COLOR)に連動させる。
// 名前空間が未確定な間はデフォルトのオレンジ。
function applyAccent(namespace: string | null) {
  document.documentElement.style.setProperty('--t-accent', namespace ? colorForRobot(namespace) : '#ff6600');
}
applyAccent(null);

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

const HOST_HISTORY_KEY = 'robot_host_history';
const HOST_HISTORY_MAX = 8;

function loadHostHistory(): string[] {
  try {
    const raw = localStorage.getItem(HOST_HISTORY_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed;
    }
  } catch { /* ignore */ }
  return [];
}

function pushHostHistory(prev: string[], host: string): string[] {
  const trimmed = host.trim();
  if (!trimmed) return prev;
  const next = [trimmed, ...prev.filter(h => h !== trimmed)].slice(0, HOST_HISTORY_MAX);
  localStorage.setItem(HOST_HISTORY_KEY, JSON.stringify(next));
  return next;
}

type Tab = 'operation' | 'talk' | 'map' | 'system' | 'custom' | 'fleet';

// UI(チュームまわり: ボタン・ラベル・メニュー)のみの言語切替。会話タブのやり取り内容や
// クイックフレーズ等の「会話内容」は対象外(常に日本語のまま)。
type UiLang = 'ja' | 'en';
const UI_LANG_KEY = 'ui_lang';
function loadUiLang(): UiLang {
  return localStorage.getItem(UI_LANG_KEY) === 'en' ? 'en' : 'ja';
}

const STRINGS = {
  ja: {
    settings: '設定',
    fleet: 'フリート',
    display: '表示',
    darkMode: 'ダークモード',
    lightMode: 'ライトモード',
    language: '言語',
    connect: '接続',
    hostPlaceholder: '192.168.1.x / cube-petit-orange.local',
    namespaceLoading: '名前空間を取得中...',
    tabOperation: '操作',
    tabTalk: '会話',
    tabSystem: 'システム',
    tabCustom: 'カスタム会話',
    tabMap: 'カスタムマップ',
    tabFleet: 'フリート運用',
  },
  en: {
    settings: 'Settings',
    fleet: 'Fleet',
    display: 'Display',
    darkMode: 'Dark Mode',
    lightMode: 'Light Mode',
    language: 'Language',
    connect: 'Connect',
    hostPlaceholder: '192.168.1.x / cube-petit-orange.local',
    namespaceLoading: 'Loading namespace...',
    tabOperation: 'Operation',
    tabTalk: 'Talk',
    tabSystem: 'System',
    tabCustom: 'Custom Talk',
    tabMap: 'Custom Map',
    tabFleet: 'Fleet Ops',
  },
} as const satisfies Record<UiLang, Record<string, string>>;

const TABS: { id: Tab; labelKey: keyof typeof STRINGS['ja'] }[] = [
  { id: 'operation', labelKey: 'tabOperation' },
  { id: 'talk',      labelKey: 'tabTalk' },
  { id: 'system',    labelKey: 'tabSystem' },
  { id: 'custom',    labelKey: 'tabCustom' },
  { id: 'map',       labelKey: 'tabMap' },
  { id: 'fleet',     labelKey: 'tabFleet' },
];

export default function App() {
  const [host, setHost] = useState<string>(() => localStorage.getItem('robot_host') || DEFAULT_HOST);
  const [inputHost, setInputHost] = useState<string>(host);
  const inputRef = useRef<HTMLInputElement>(null);
  const [hostHistory, setHostHistory] = useState<string[]>(() => pushHostHistory(loadHostHistory(), host));

  const apiUrl = `http://${host}:8000`;

  // 名前空間は接続先ロボット (host) の hostname 由来で変わるため、host が確定/切替される
  // たびに再取得する。取得できるまでは null（下の描画でローディング扱い）。
  const [namespace, setNamespace] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    setNamespace(null);
    fetch(`${apiUrl}/system/namespace`)
      .then(r => r.json())
      .then(d => { if (!cancelled && d.namespace) setNamespace(d.namespace); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [apiUrl]);

  const robot: RobotConfig = {
    name: namespace ? nicknameForRobot(namespace) : '',
    namespace: namespace ?? '',
    rosbridgeUrl: `ws://${host}:9090`,
  };

  const [tab, setTab] = useState<Tab>('operation');
  const { ros, status } = useRosConnection(robot.rosbridgeUrl);
  const [isDark, setIsDark] = useState(() => localStorage.getItem('theme') !== 'light');
  const [uiLang, setUiLang] = useState<UiLang>(loadUiLang);
  const t = STRINGS[uiLang];

  useEffect(() => {
    applyTheme(isDark);
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  useEffect(() => {
    localStorage.setItem(UI_LANG_KEY, uiLang);
  }, [uiLang]);

  useEffect(() => {
    applyAccent(namespace);
  }, [namespace]);

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
    setHostHistory(prev => pushHostHistory(prev, trimmed));
    inputRef.current?.blur();
  };

  // Tier 2 ロボットピッカー: カードクリックで即座にそのロボットへ切り替える
  // (connect() と違い、入力確定ボタンを経由しない一発切り替え)。左上の設定アイコンで
  // 開閉するドロワー(設定パネル)の中のフリートセクションとして表示する
  // (常時表示だと場所を取るため。テーマ/言語もここに集約している)。
  const [settingsOpen, setSettingsOpen] = useState(false);
  const selectRobotFromFleet = (newHost: string) => {
    setSettingsOpen(false);
    if (newHost === host) return;
    setInputHost(newHost);
    setHost(newHost);
    localStorage.setItem('robot_host', newHost);
    setHostHistory(prev => pushHostHistory(prev, newHost));
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
        {/* 設定ドロワー(フリート切替/テーマ/言語)の開閉トグル */}
        <button
          onClick={() => setSettingsOpen(o => !o)}
          title={t.settings}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 32, height: 32, borderRadius: 10, border: 'none', cursor: 'pointer',
            background: 'var(--t-surface2)', color: 'var(--t-text)', fontSize: 16, flexShrink: 0,
          }}
        >
          <Icon name="settings" />
        </button>

        {/* ロボット名(接続中の名前空間から動的に。複数機を行き来するので固定表記にしない) */}
        {robot.name && (
          <span style={{ fontSize: 14, color: 'var(--t-text)', whiteSpace: 'nowrap' }}>
            {robot.name}
          </span>
        )}

        {/* IP入力(過去に繋いだホストをdatalistで選べる) */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <input
            ref={inputRef}
            value={inputHost}
            onChange={e => setInputHost(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && connect()}
            placeholder={t.hostPlaceholder}
            list="host-history"
            style={{
              width: 220, padding: '5px 8px', borderRadius: 8, fontSize: 13,
              background: 'var(--t-input-bg)', color: 'var(--t-text)',
              border: `1px solid ${hostChanged ? 'var(--t-accent)' : 'var(--t-border2)'}`,
              outline: 'none',
            }}
          />
          <datalist id="host-history">
            {hostHistory.map(h => <option key={h} value={h} />)}
          </datalist>
          {hostChanged && (
            <button
              onClick={connect}
              style={{
                padding: '5px 10px', borderRadius: 8, border: 'none', cursor: 'pointer',
                background: 'var(--t-accent)', color: '#fff', fontSize: 12,
              }}
            >{t.connect}</button>
          )}
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

        {/* 接続ステータス(テーマボタンの右。ここより前の要素の位置がテキスト長で
            ずれないよう、可変長のstatusテキストは一番最後に置く) */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: statusColor }} />
          <span style={{ fontSize: 12, color: 'var(--t-text-dim)' }}>{status}</span>
        </div>

        <div style={{ flex: 1 }} />

        {TABS.map(({ id, labelKey }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            style={{
              padding: '6px 18px', borderRadius: 20, border: 'none', cursor: 'pointer',
              background: tab === id ? 'var(--t-accent)' : 'var(--t-surface2)', color: 'var(--t-text)', fontSize: 14,
            }}
          >
            {t[labelKey]}
          </button>
        ))}
      </div>

      {/* 設定ドロワー: テーマ/言語(表示設定)+ Tier 2複数ロボット切替(フリート、zenoh経由)。
          左上のアイコンで開閉する左からのスライドドロワー。背景クリックで閉じる */}
      {settingsOpen && (
        <div
          onClick={() => setSettingsOpen(false)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', zIndex: 100,
          }}
        />
      )}
      <div style={{
        position: 'fixed', top: 0, left: 0, bottom: 0, width: 280, zIndex: 101,
        background: 'var(--t-surface)', borderRight: '1px solid var(--t-border)',
        padding: 'calc(env(safe-area-inset-top) + 16px) 16px 16px',
        overflowY: 'auto', boxSizing: 'border-box',
        transform: settingsOpen ? 'translateX(0)' : 'translateX(-100%)',
        transition: 'transform 0.25s ease',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <span style={{ fontSize: 15, fontWeight: 'bold', color: 'var(--t-text)' }}>{t.settings}</span>
          <button
            onClick={() => setSettingsOpen(false)}
            style={{
              width: 28, height: 28, borderRadius: 8, border: 'none', cursor: 'pointer',
              background: 'var(--t-surface2)', color: 'var(--t-text)', fontSize: 14,
            }}
          ><Icon name="close" size={16} /></button>
        </div>

        {/* 表示設定: テーマ + 言語 */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 12, color: 'var(--t-text-dim)', marginBottom: 8 }}>{t.display}</div>
          <button
            onClick={() => setIsDark(d => !d)}
            style={{
              display: 'flex', alignItems: 'center', gap: 8, width: '100%',
              padding: '10px 14px', borderRadius: 12, border: '1px solid var(--t-border2)', cursor: 'pointer',
              background: 'var(--t-bg)', color: 'var(--t-text)', fontSize: 14, marginBottom: 8,
            }}
          >
            <Icon name={isDark ? 'light_mode' : 'dark_mode'} size={18} />
            {isDark ? t.lightMode : t.darkMode}
          </button>
          <div style={{ fontSize: 12, color: 'var(--t-text-dim)', margin: '10px 0 6px' }}>{t.language}</div>
          <div style={{ display: 'flex', gap: 8 }}>
            {(['ja', 'en'] as const).map(lang => (
              <button
                key={lang}
                onClick={() => setUiLang(lang)}
                style={{
                  flex: 1, padding: '8px 0', borderRadius: 10, cursor: 'pointer', fontSize: 13,
                  border: uiLang === lang ? '2px solid var(--t-accent)' : '1px solid var(--t-border2)',
                  background: uiLang === lang ? 'var(--t-surface2)' : 'var(--t-bg)', color: 'var(--t-text)',
                }}
              >
                {lang === 'ja' ? '日本語' : 'English'}
              </button>
            ))}
          </div>
        </div>

        {/* フリート */}
        <div style={{ fontSize: 12, color: 'var(--t-text-dim)', marginBottom: 8 }}>{t.fleet}</div>
        <RobotPicker apiUrl={apiUrl} currentNamespace={namespace ?? ''} onSelectRobot={selectRobotFromFleet} />
      </div>

      {/* コンテンツ */}
      <div style={{ flex: 1, padding: 12, overflow: 'hidden', minHeight: 0 }}>
        {namespace === null ? (
          <div style={{ padding: 24, textAlign: 'center', color: 'var(--t-text-dim)' }}>
            {t.namespaceLoading}
          </div>
        ) : (
          <>
            {tab === 'operation' && <OperationTab ros={ros} namespace={robot.namespace} apiUrl={apiUrl} quickPhrases={quickPhrases} setQuickPhrases={setQuickPhrases} />}
            {tab === 'talk'      && <TalkTab      ros={ros} namespace={robot.namespace} quickPhrases={quickPhrases} setQuickPhrases={setQuickPhrases} apiUrl={apiUrl} />}
            {tab === 'system'    && <SystemPanel  namespace={robot.namespace} apiUrl={apiUrl} quickPhrases={quickPhrases} setQuickPhrases={setQuickPhrases} />}
            {tab === 'map'       && <MapTab       namespace={robot.namespace} apiUrl={apiUrl} />}
            {tab === 'custom'    && <CustomTab    apiUrl={apiUrl} quickPhrases={quickPhrases} setQuickPhrases={setQuickPhrases} />}
            {tab === 'fleet'     && <FleetDashboard apiUrl={apiUrl} />}
          </>
        )}
      </div>
    </div>
  );
}
