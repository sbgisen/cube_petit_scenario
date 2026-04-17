interface Props {
  phrases: string[];
  onSpeak: (phrase: string) => void;
  onAdd: (phrase: string) => void;
  speechAvailable: boolean;
}

const btnBase: React.CSSProperties = {
  padding: '10px 8px', borderRadius: 12, border: 'none', cursor: 'pointer',
  color: 'var(--t-text)', fontSize: 13, lineHeight: 1.3, textAlign: 'center',
};

const MAX = 8;

export function QuickPhraseGrid({ phrases, onSpeak, onAdd, speechAvailable }: Props) {
  const handleAdd = () => {
    const text = window.prompt('フレーズを入力してください');
    if (text && text.trim()) onAdd(text.trim());
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
      {phrases.map((phrase, i) => (
        <button
          key={i}
          disabled={!speechAvailable}
          onClick={() => onSpeak(phrase)}
          style={{
            ...btnBase,
            background: speechAvailable ? 'var(--t-surface2)' : 'var(--t-border)',
            color: speechAvailable ? 'var(--t-text)' : 'var(--t-text-dim)',
            cursor: speechAvailable ? 'pointer' : 'not-allowed',
            opacity: speechAvailable ? 1 : 0.5,
          }}
          onMouseDown={(e) => speechAvailable && (e.currentTarget.style.background = '#ff6600')}
          onMouseUp={(e) => speechAvailable && (e.currentTarget.style.background = 'var(--t-surface2)')}
          onMouseLeave={(e) => speechAvailable && (e.currentTarget.style.background = 'var(--t-surface2)')}
          onTouchStart={(e) => speechAvailable && (e.currentTarget.style.background = '#ff6600')}
          onTouchEnd={(e) => speechAvailable && (e.currentTarget.style.background = 'var(--t-surface2)')}
        >
          {phrase}
        </button>
      ))}
      {phrases.length < MAX && (
        <button
          onClick={handleAdd}
          style={{ ...btnBase, background: 'var(--t-surface)', border: '1px dashed var(--t-border2)', color: 'var(--t-text-dim)', fontSize: 20 }}
        >
          ＋
        </button>
      )}
    </div>
  );
}
