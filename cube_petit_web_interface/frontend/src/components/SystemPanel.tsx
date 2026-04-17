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

export function SystemPanel({ ros, namespace, apiUrl, quickPhrases, setQuickPhrases }: Props) {
  const [nodeList, setNodeList] = useState<string[]>([]);
  const [draftPhrases, setDraftPhrases] = useState<string[]>(quickPhrases);
  const [, setLaunchStatus] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!ros) return;
    const interval = setInterval(() => {
      ros.getNodes((nodes: string[]) => setNodeList(nodes));
    }, 3000);
    return () => clearInterval(interval);
  }, [ros]);

  const isAlive = (shortName: string) =>
    nodeList.some((n) => n.includes(shortName));

  const launchAction = async (target: 'bringup' | 'demo', action: 'start' | 'stop') => {
    try {
      const res = await fetch(`${apiUrl}/launch/${target}/${action}`, { method: 'POST' });
      const data = await res.json();
      setLaunchStatus((prev) => ({ ...prev, [target]: action === 'start' && data.ok }));
    } catch {
      console.error('Launch API error');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: 8 }}>
      <div>
        <div style={{ color: 'var(--t-text-muted)', fontSize: 14, fontWeight: 'bold', marginBottom: 8 }}>
          ノード監視 <span style={{ fontSize: 11, color: 'var(--t-text-dim)' }}>({namespace})</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {WATCHED_NODES.map((node) => (
            <div key={node} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{
                width: 10, height: 10, borderRadius: '50%',
                background: isAlive(node) ? '#00cc66' : '#cc3333',
                flexShrink: 0,
              }} />
              <span style={{ color: 'var(--t-text-muted)', fontSize: 13 }}>{node}</span>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div style={{ color: 'var(--t-text-muted)', fontSize: 14, fontWeight: 'bold', marginBottom: 8 }}>
          起動管理
        </div>
        {(['bringup', 'demo'] as const).map((target) => (
          <div key={target} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span style={{ color: 'var(--t-text-muted)', fontSize: 13, width: 70 }}>{target}</span>
            <button
              onClick={() => launchAction(target, 'start')}
              style={{
                padding: '6px 14px', borderRadius: 16, border: 'none', cursor: 'pointer',
                background: '#00cc66', color: 'var(--t-text)', fontSize: 13,
              }}
            >
              起動
            </button>
            <button
              onClick={() => launchAction(target, 'stop')}
              style={{
                padding: '6px 14px', borderRadius: 16, border: 'none', cursor: 'pointer',
                background: '#cc3333', color: 'var(--t-text)', fontSize: 13,
              }}
            >
              停止
            </button>
          </div>
        ))}
      </div>
      <div>
        <div style={{ color: 'var(--t-text-muted)', fontSize: 14, fontWeight: 'bold', marginBottom: 8 }}>
          クイックフレーズ
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {draftPhrases.map((phrase, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ color: 'var(--t-text-dim)', fontSize: 12, width: 16, textAlign: 'right' }}>{i + 1}</span>
              <input
                value={phrase}
                onChange={(e) => {
                  const next = [...draftPhrases];
                  next[i] = e.target.value;
                  setDraftPhrases(next);
                }}
                style={{
                  flex: 1, padding: '6px 10px', borderRadius: 8, border: '1px solid var(--t-border2)',
                  background: 'var(--t-surface)', color: 'var(--t-text)', fontSize: 13,
                }}
              />
              <button
                onClick={() => setDraftPhrases(draftPhrases.filter((_, j) => j !== i))}
                style={{
                  padding: '4px 8px', borderRadius: 8, border: 'none',
                  cursor: 'pointer', background: '#442222', color: '#ff6666', fontSize: 13,
                }}
              >
                ✕
              </button>
            </div>
          ))}
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
            <button
              onClick={() => setDraftPhrases([...draftPhrases, ''])}
              style={{
                padding: '6px 14px', borderRadius: 16, border: '1px dashed var(--t-border2)',
                cursor: 'pointer', background: 'transparent', color: 'var(--t-text-dim)', fontSize: 13,
              }}
            >
              ＋ 追加
            </button>
            <button
              onClick={() => setQuickPhrases(draftPhrases.filter(p => p.trim()))}
              style={{
                padding: '6px 14px', borderRadius: 16, border: 'none',
                cursor: 'pointer', background: '#ff6600', color: 'var(--t-text)', fontSize: 13,
              }}
            >
              保存
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
