import { useEffect, useRef, useState } from 'react';

const MAX_PHRASES = 8;

interface Props {
  apiUrl: string;
  quickPhrases: string[];
  setQuickPhrases: (phrases: string[]) => void;
}

const cardStyle: React.CSSProperties = {
  background: 'var(--t-surface)',
  border: '1px solid var(--t-border)',
  borderRadius: 12,
  padding: '14px 16px',
  overflow: 'hidden',
  display: 'flex',
  flexDirection: 'column',
};

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ color: 'var(--t-text-muted)', fontSize: 13, fontWeight: 'bold', marginBottom: 10, flexShrink: 0 }}>
      {children}
    </div>
  );
}

function ActiveBadge() {
  return <span style={{ fontSize: 11, color: '#00cc66', background: '#00cc6620', padding: '2px 8px', borderRadius: 10 }}>使用中</span>;
}

function UseButton({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} style={{ fontSize: 11, padding: '2px 8px', borderRadius: 10, border: '1px solid var(--t-border2)', cursor: 'pointer', background: 'transparent', color: 'var(--t-text-dim)' }}>
      これを使う
    </button>
  );
}

const PROTECTED_PROMPTS = new Set(['realtime_chat_setting.txt', 'gpt_chat_setting.txt']);
const PROTECTED_HISTORY = new Set(['history.jsonl']);

// ファイルリストコンポーネント（プロンプト・ヒストリー共用）
function FileList({
  files, selected, active, onSelect, onActivate, onDelete, onNew, newExt, protected: protectedSet,
}: {
  files: string[]; selected: string; active: string;
  onSelect: (f: string) => void; onActivate: (f: string) => void;
  onDelete: (f: string) => void; onNew: (name: string) => void;
  newExt: string; protected?: Set<string>;
}) {
  const isProtected = (f: string) => protectedSet?.has(f) ?? false;
  const [showNew, setShowNew] = useState(false);
  const [newName, setNewName] = useState('');

  const create = () => {
    if (!newName.trim()) return;
    onNew(newName.trim());
    setNewName('');
    setShowNew(false);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
      {/* 新規作成フォーム（上部固定） */}
      {showNew ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 8, flexShrink: 0 }}>
          <input
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') create(); if (e.key === 'Escape') setShowNew(false); }}
            placeholder={`名前（${newExt}）`}
            autoFocus
            style={{ padding: '5px 8px', borderRadius: 6, border: '1px solid var(--t-border2)', background: 'var(--t-input-bg)', color: 'var(--t-text)', fontSize: 12 }}
          />
          <div style={{ display: 'flex', gap: 4 }}>
            <button onClick={create} style={{ flex: 1, padding: '4px', borderRadius: 6, border: 'none', cursor: 'pointer', background: 'var(--t-accent)', color: '#fff', fontSize: 12 }}>作成</button>
            <button onClick={() => setShowNew(false)} style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid var(--t-border2)', cursor: 'pointer', background: 'transparent', color: 'var(--t-text-dim)', fontSize: 12 }}>✕</button>
          </div>
        </div>
      ) : (
        <button onClick={() => setShowNew(true)} style={{ padding: '5px 8px', borderRadius: 8, border: '1px dashed var(--t-border2)', cursor: 'pointer', background: 'transparent', color: 'var(--t-text-dim)', fontSize: 12, marginBottom: 8, flexShrink: 0 }}>
          ＋ 新規
        </button>
      )}

      {/* ファイル一覧（スクロール） */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 3 }}>
        {files.map(file => (
          <div key={file}
            onClick={() => onSelect(file)}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 8px', borderRadius: 8, cursor: 'pointer', background: file === selected ? 'var(--t-surface2)' : 'transparent', border: `1px solid ${file === selected ? 'var(--t-border2)' : 'transparent'}` }}>
            {file === active && <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#00cc66', flexShrink: 0 }} />}
            <span style={{ fontSize: 12, color: 'var(--t-text)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file}</span>
            {file === active
              ? <button onClick={e => { e.stopPropagation(); onActivate(file); }} style={{ fontSize: 10, padding: '1px 6px', borderRadius: 8, border: 'none', cursor: 'pointer', background: '#00cc6620', color: '#00cc66', flexShrink: 0 }}>使用中</button>
              : <button onClick={e => { e.stopPropagation(); onActivate(file); }} style={{ fontSize: 10, padding: '1px 6px', borderRadius: 8, border: '1px solid var(--t-border2)', cursor: 'pointer', background: 'transparent', color: 'var(--t-text-dim)', flexShrink: 0 }}>使う</button>
            }
            {!isProtected(file) && (
              <button onClick={e => { e.stopPropagation(); onDelete(file); }} style={{ padding: '1px 4px', borderRadius: 4, border: 'none', cursor: 'pointer', background: 'transparent', color: 'var(--t-text-dim)', fontSize: 11, flexShrink: 0 }}>✕</button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function CustomTab({ apiUrl, quickPhrases, setQuickPhrases }: Props) {
  // クイックフレーズ
  const [draft, setDraft] = useState<string[]>(() => {
    const p = [...quickPhrases];
    while (p.length < MAX_PHRASES) p.push('');
    return p.slice(0, MAX_PHRASES);
  });
  useEffect(() => {
    const p = [...quickPhrases];
    while (p.length < MAX_PHRASES) p.push('');
    setDraft(p.slice(0, MAX_PHRASES));
  }, [quickPhrases]);
  const savePhrases = () => setQuickPhrases(draft.map(p => p.trim()).filter(Boolean));

  // 会話プロンプト
  const [promptFiles, setPromptFiles] = useState<string[]>([]);
  const [activePrompt, setActivePrompt] = useState('');
  const [selectedPrompt, setSelectedPrompt] = useState('');
  const [content, setContent] = useState('');
  const [saved, setSaved] = useState(false);

  const loadPromptList = () =>
    fetch(`${apiUrl}/prompt/list`).then(r => r.json()).then(d => {
      setPromptFiles(d.files ?? []);
      setActivePrompt(d.active ?? '');
      setSelectedPrompt(p => p || d.active || d.files?.[0] || '');
    }).catch(() => {});

  useEffect(() => { loadPromptList(); }, [apiUrl]);

  useEffect(() => {
    if (!selectedPrompt) return;
    fetch(`${apiUrl}/prompt?file=${encodeURIComponent(selectedPrompt)}`)
      .then(r => r.json()).then(d => setContent(d.content ?? '')).catch(() => {});
  }, [selectedPrompt, apiUrl]);

  const savePrompt = () => {
    fetch(`${apiUrl}/prompt?file=${encodeURIComponent(selectedPrompt)}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    }).then(() => { setSaved(true); setTimeout(() => setSaved(false), 2000); }).catch(() => {});
  };

  const activatePrompt = (file: string) => {
    fetch(`${apiUrl}/prompt/activate?file=${encodeURIComponent(file)}`, { method: 'POST' })
      .then(() => loadPromptList()).catch(() => {});
  };

  const newPrompt = (name: string) => {
    fetch(`${apiUrl}/prompt/new?name=${encodeURIComponent(name)}`, { method: 'POST' })
      .then(r => r.json()).then(d => { if (d.ok) { loadPromptList().then(() => setSelectedPrompt(d.file)); } }).catch(() => {});
  };

  const deletePrompt = (file: string) => {
    if (!confirm(`「${file}」を削除しますか？`)) return;
    fetch(`${apiUrl}/prompt?file=${encodeURIComponent(file)}`, { method: 'DELETE' })
      .then(() => { loadPromptList(); if (selectedPrompt === file) setSelectedPrompt(activePrompt); }).catch(() => {});
  };

  // ヒストリー
  const [historyFiles, setHistoryFiles] = useState<string[]>([]);
  const [activeHistory, setActiveHistory] = useState('');
  const [selectedHistory, setSelectedHistory] = useState('');

  const loadHistoryList = () =>
    fetch(`${apiUrl}/history/list`).then(r => r.json()).then(d => {
      setHistoryFiles(d.files ?? []);
      setActiveHistory(d.active ?? '');
      setSelectedHistory(p => p || d.active || d.files?.[0] || '');
    }).catch(() => {});

  useEffect(() => { loadHistoryList(); }, [apiUrl]);

  const activateHistory = (file: string) => {
    fetch(`${apiUrl}/history/activate?file=${encodeURIComponent(file)}`, { method: 'POST' })
      .then(() => loadHistoryList()).catch(() => {});
  };

  const newHistory = (name: string) => {
    fetch(`${apiUrl}/history/new?name=${encodeURIComponent(name)}`, { method: 'POST' })
      .then(r => r.json()).then(d => { if (d.ok) { loadHistoryList().then(() => setSelectedHistory(d.file)); } }).catch(() => {});
  };

  const deleteHistory = (file: string) => {
    if (!confirm(`「${file}」を削除しますか？`)) return;
    fetch(`${apiUrl}/history?file=${encodeURIComponent(file)}`, { method: 'DELETE' })
      .then(() => { loadHistoryList(); if (selectedHistory === file) setSelectedHistory(activeHistory); }).catch(() => {});
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 16, padding: 8, height: '100%', overflow: 'hidden' }}>

      {/* 左カラム: クイックフレーズ + ヒストリー */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, minHeight: 0 }}>

        {/* クイックフレーズ */}
        <div style={{ ...cardStyle, flex: 1 }}>
          <SectionTitle>クイックフレーズ <span style={{ fontSize: 11, color: 'var(--t-text-dim)', fontWeight: 'normal' }}>（{MAX_PHRASES}個）</span></SectionTitle>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, overflowY: 'auto' }}>
            {draft.map((phrase, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <span style={{ color: 'var(--t-text-dim)', fontSize: 12, width: 18, textAlign: 'right', flexShrink: 0 }}>{i + 1}</span>
                <input value={phrase}
                  onChange={e => { const next = [...draft]; next[i] = e.target.value; setDraft(next); }}
                  style={{ flex: 1, padding: '4px 8px', borderRadius: 8, border: '1px solid var(--t-border2)', background: 'var(--t-input-bg)', color: 'var(--t-text)', fontSize: 13 }}
                />
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 6, flexShrink: 0 }}>
            <button onClick={savePhrases} style={{ padding: '6px 18px', borderRadius: 16, border: 'none', cursor: 'pointer', background: 'var(--t-accent)', color: '#fff', fontSize: 13 }}>保存</button>
          </div>
        </div>

        {/* ヒストリー */}
        <div style={{ ...cardStyle, flex: 1 }}>
          <SectionTitle>ヒストリー</SectionTitle>
          <FileList
            files={historyFiles} selected={selectedHistory} active={activeHistory}
            onSelect={setSelectedHistory} onActivate={activateHistory}
            onDelete={deleteHistory} onNew={newHistory} newExt=".jsonl"
            protected={PROTECTED_HISTORY}
          />
        </div>
      </div>

      {/* 右カラム: 会話プロンプト */}
      <div style={cardStyle}>
        <SectionTitle>会話プロンプト</SectionTitle>
        <div style={{ display: 'flex', gap: 12, flex: 1, minHeight: 0 }}>

          {/* ファイルリスト */}
          <div style={{ width: 210, flexShrink: 0, display: 'flex', flexDirection: 'column' }}>
            <FileList
              files={promptFiles} selected={selectedPrompt} active={activePrompt}
              onSelect={setSelectedPrompt} onActivate={activatePrompt}
              onDelete={deletePrompt} onNew={newPrompt} newExt=".txt"
              protected={PROTECTED_PROMPTS}
            />
          </div>

          {/* エディタ */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
            {selectedPrompt && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexShrink: 0 }}>
                <span style={{ fontSize: 12, color: 'var(--t-text-dim)' }}>{selectedPrompt}</span>
                {selectedPrompt === activePrompt ? <ActiveBadge /> : <UseButton onClick={() => activatePrompt(selectedPrompt)} />}
                {PROTECTED_PROMPTS.has(selectedPrompt) && (
                  <span style={{ fontSize: 11, color: 'var(--t-text-dim)', background: 'var(--t-overlay)', padding: '2px 8px', borderRadius: 10 }}>読み取り専用</span>
                )}
              </div>
            )}
            <textarea value={content} onChange={e => { if (!PROTECTED_PROMPTS.has(selectedPrompt)) setContent(e.target.value); }}
              readOnly={PROTECTED_PROMPTS.has(selectedPrompt)}
              style={{ flex: 1, padding: '8px 10px', borderRadius: 8, border: '1px solid var(--t-border2)', background: PROTECTED_PROMPTS.has(selectedPrompt) ? 'var(--t-overlay)' : 'var(--t-input-bg)', color: 'var(--t-text)', fontSize: 13, resize: 'none', fontFamily: 'monospace', lineHeight: 1.6, boxSizing: 'border-box' }}
            />
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', marginTop: 6, gap: 10, flexShrink: 0 }}>
              <span style={{ fontSize: 11, color: 'var(--t-text-dim)' }}>※保存後はrealtime_gpt_chatの再起動が必要です</span>
              {!PROTECTED_PROMPTS.has(selectedPrompt) && (
                <button onClick={savePrompt}
                  style={{ padding: '6px 18px', borderRadius: 16, border: 'none', cursor: 'pointer', background: saved ? '#00cc66' : 'var(--t-accent)', color: '#fff', fontSize: 13, transition: 'background 0.3s' }}>
                  {saved ? '保存済み' : '保存'}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

    </div>
  );
}
