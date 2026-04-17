import { useEffect, useState } from 'react';

interface Props {
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

export function CustomTab({ apiUrl, quickPhrases, setQuickPhrases }: Props) {
  const [draft, setDraft] = useState<string[]>(quickPhrases);
  const [prompt, setPrompt] = useState('');
  const [promptSaved, setPromptSaved] = useState(false);

  useEffect(() => { setDraft(quickPhrases); }, [quickPhrases]);

  useEffect(() => {
    fetch(`${apiUrl}/prompt`)
      .then(r => r.json())
      .then(d => setPrompt(d.content ?? ''))
      .catch(() => {});
  }, [apiUrl]);

  const savePhrases = () => setQuickPhrases(draft.filter(p => p.trim()));

  const savePrompt = () => {
    fetch(`${apiUrl}/prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: prompt }),
    }).then(() => {
      setPromptSaved(true);
      setTimeout(() => setPromptSaved(false), 2000);
    }).catch(() => {});
  };

  return (
    <div style={{ display: 'flex', gap: 24, padding: 8, flexWrap: 'wrap', alignContent: 'flex-start', overflowY: 'auto', height: '100%' }}>

      {/* クイックフレーズ */}
      <div style={{ minWidth: 280, maxWidth: 400 }}>
        <SectionTitle>クイックフレーズ</SectionTitle>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {draft.map((phrase, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ color: 'var(--t-text-dim)', fontSize: 12, width: 18, textAlign: 'right', flexShrink: 0 }}>{i + 1}</span>
              <input
                value={phrase}
                onChange={e => {
                  const next = [...draft];
                  next[i] = e.target.value;
                  setDraft(next);
                }}
                style={{
                  flex: 1, padding: '6px 10px', borderRadius: 8,
                  border: '1px solid var(--t-border2)',
                  background: 'var(--t-surface)', color: 'var(--t-text)', fontSize: 13,
                }}
              />
              <button
                onClick={() => setDraft(draft.filter((_, j) => j !== i))}
                style={{ padding: '4px 8px', borderRadius: 8, border: 'none', cursor: 'pointer', background: '#442222', color: '#ff6666', fontSize: 13 }}
              >✕</button>
            </div>
          ))}
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
            <button
              onClick={() => setDraft([...draft, ''])}
              style={{ padding: '6px 14px', borderRadius: 16, border: '1px dashed var(--t-border2)', cursor: 'pointer', background: 'transparent', color: 'var(--t-text-dim)', fontSize: 13 }}
            >＋ 追加</button>
            <button
              onClick={savePhrases}
              style={{ padding: '6px 14px', borderRadius: 16, border: 'none', cursor: 'pointer', background: '#ff6600', color: '#fff', fontSize: 13 }}
            >保存</button>
          </div>
        </div>
      </div>

      {/* 会話プロンプト */}
      <div style={{ minWidth: 320, flex: 1 }}>
        <SectionTitle>会話プロンプト</SectionTitle>
        <div style={{ fontSize: 11, color: 'var(--t-text-muted)', marginBottom: 6 }}>
          ※保存後はrealtime_gpt_chatの再起動が必要です
        </div>
        <textarea
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          style={{
            width: '100%', minHeight: 260, padding: '8px 10px', borderRadius: 8,
            border: '1px solid var(--t-border2)',
            background: 'var(--t-surface)', color: 'var(--t-text)', fontSize: 13,
            resize: 'vertical', fontFamily: 'monospace', lineHeight: 1.6,
            boxSizing: 'border-box',
          }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 6 }}>
          <button
            onClick={savePrompt}
            style={{
              padding: '6px 18px', borderRadius: 16, border: 'none', cursor: 'pointer',
              background: promptSaved ? '#00cc66' : '#ff6600', color: '#fff', fontSize: 13,
              transition: 'background 0.3s',
            }}
          >{promptSaved ? '保存済み' : '保存'}</button>
        </div>
      </div>

    </div>
  );
}
