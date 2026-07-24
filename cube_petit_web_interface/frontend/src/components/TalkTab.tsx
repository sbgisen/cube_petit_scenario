import { useEffect, useState } from 'react';
import * as ROSLIB from 'roslib';
import { CameraView } from './CameraView';
import { AnimaPanel } from './AnimaPanel';
import { ConversationPanel } from './ConversationPanel';
import { QuickPhraseGrid } from './QuickPhraseGrid';
import { ExpressionGrid } from './ExpressionGrid';
import { useRosAction } from '../hooks/useRosAction';
import { useSpeechServerAlive } from '../hooks/useRosNodeAlive';

interface Props {
  ros: ROSLIB.Ros | null;
  namespace: string;
  quickPhrases: string[];
  setQuickPhrases: (phrases: string[]) => void;
  apiUrl: string;
}

const POLL_INTERVAL_MS = 3000;

export function TalkTab({ ros, namespace, quickPhrases, setQuickPhrases, apiUrl }: Props) {
  const sendSpeech = useRosAction(ros, `/${namespace}/speech_action_server`, 'cube_petit_speech_msgs/action/Speech');
  void useSpeechServerAlive(namespace);

  const [isActive, setIsActive] = useState(false);

  // Left-column grid selector: quick phrases or expression grid (persisted for e.g. photo shoots).
  const [leftTab, setLeftTab] = useState<'phrase' | 'expression'>(
    () => (localStorage.getItem('talk_left_tab') === 'expression' ? 'expression' : 'phrase'));
  const switchLeftTab = (t: 'phrase' | 'expression') => {
    setLeftTab(t);
    localStorage.setItem('talk_left_tab', t);
  };

  useEffect(() => {
    const poll = () => {
      fetch(`${apiUrl}/ros/conversation/status?namespace=${namespace}`)
        .then(r => r.json())
        .then(d => setIsActive(d.is_active))
        .catch(() => {});
    };
    poll();
    const timer = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [apiUrl, namespace]);

  const toggleConversation = () => {
    const next = !isActive;
    fetch(`${apiUrl}/ros/conversation/enable?namespace=${namespace}&enable=${next}`, { method: 'POST' })
      .then(() => setIsActive(next))
      .catch(() => {});
  };

  const speak = (phrase: string) => sendSpeech({ text: phrase, emotion: 'happy', emotion_level: 2, pitch: 100, speed: 100, volume: 100 });
  const addPhrase = (phrase: string) => setQuickPhrases([...quickPhrases, phrase]);

  return (
    <div style={{ display: 'flex', gap: 12, height: '100%', overflow: 'hidden' }}>
      {/* 左: カメラ + (フレーズ/表情 切り替え) はスクロール、下段(Anima + 会話トグル)は固定 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, width: 320, flexShrink: 0, overflow: 'hidden' }}>
        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <CameraView ros={ros} namespace={namespace} enabled toggleable height={200} />
          <div style={{ display: 'flex', gap: 4, background: 'var(--t-surface)', borderRadius: 10, padding: 3, flexShrink: 0 }}>
            {(['phrase', 'expression'] as const).map((t) => (
              <button
                key={t}
                onClick={() => switchLeftTab(t)}
                style={{
                  flex: 1, padding: '6px 0', borderRadius: 8, border: 'none', cursor: 'pointer', fontSize: 12,
                  background: leftTab === t ? 'var(--t-surface2)' : 'transparent',
                  color: leftTab === t ? 'var(--t-text)' : 'var(--t-text-dim)',
                  fontWeight: leftTab === t ? 'bold' : 'normal',
                }}
              >
                {t === 'phrase' ? 'フレーズ' : '表情'}
              </button>
            ))}
          </div>
          {leftTab === 'phrase'
            ? <QuickPhraseGrid phrases={quickPhrases} onSpeak={speak} onAdd={addPhrase} speechAvailable={true} />
            : <ExpressionGrid ros={ros} namespace={namespace} />}
        </div>
        <AnimaPanel ros={ros} namespace={namespace} />
        <button
          onClick={toggleConversation}
          style={{
            width: '100%', padding: '14px 0', borderRadius: 12, border: 'none',
            cursor: 'pointer', fontSize: 16, fontWeight: 'bold',
            background: isActive ? '#00cc66' : 'var(--t-surface2)',
            color: isActive ? '#fff' : 'var(--t-text-muted)',
            transition: 'background 0.2s',
            boxShadow: isActive ? '0 0 12px #00cc6688' : 'none',
          }}
        >
          {isActive ? '会話中' : '会話 OFF'}
        </button>
      </div>

      {/* 右: 会話 */}
      <div style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
        <ConversationPanel ros={ros} namespace={namespace} apiUrl={apiUrl} isActive={isActive} />
      </div>
    </div>
  );
}
