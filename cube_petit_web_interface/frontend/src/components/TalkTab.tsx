import * as ROSLIB from 'roslib';
import { CameraView } from './CameraView';
import { AnimaPanel } from './AnimaPanel';
import { ConversationPanel } from './ConversationPanel';
import { QuickPhraseGrid } from './QuickPhraseGrid';
import { useRosAction } from '../hooks/useRosAction';
import { useSpeechServerAlive } from '../hooks/useRosNodeAlive';

interface Props {
  ros: ROSLIB.Ros | null;
  namespace: string;
  quickPhrases: string[];
  setQuickPhrases: (phrases: string[]) => void;
}

export function TalkTab({ ros, namespace, quickPhrases, setQuickPhrases }: Props) {
  const sendSpeech = useRosAction(ros, `/${namespace}/speech_action_server`, 'cube_petit_speech_msgs/action/Speech');
  void useSpeechServerAlive(namespace);

  const speak = (phrase: string) => sendSpeech({ text: phrase, emotion: 'happy', emotion_level: 2, pitch: 100, speed: 100, volume: 100 });
  const addPhrase = (phrase: string) => setQuickPhrases([...quickPhrases, phrase]);

  return (
    <div style={{ display: 'flex', gap: 12, height: '100%', overflow: 'hidden' }}>
      {/* 左: カメラ + クイックフレーズ + Anima */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, width: 320, flexShrink: 0 }}>
        <CameraView ros={ros} namespace={namespace} enabled height={200} />
        <QuickPhraseGrid phrases={quickPhrases} onSpeak={speak} onAdd={addPhrase} speechAvailable={true} />
        <AnimaPanel ros={ros} namespace={namespace} />
      </div>

      {/* 右: 会話 */}
      <div style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
        <ConversationPanel ros={ros} namespace={namespace} />
      </div>
    </div>
  );
}
