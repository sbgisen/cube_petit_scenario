import { useEffect, useRef, useState } from 'react';
import * as ROSLIB from 'roslib';
import { useRosTopic } from '../hooks/useRosTopic';
import { useRosService } from '../hooks/useRosService';
import type { ConversationMessage } from '../types/ros';

interface ConversationMsg {
  data: string;
}

interface Props {
  ros: ROSLIB.Ros | null;
  namespace: string;
}

export function ConversationPanel({ ros, namespace }: Props) {
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [input, setInput] = useState('');
  const [enabled, setEnabled] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const content = useRosTopic<ConversationMsg>(
    ros,
    `/${namespace}/realtime_conversation_content`,
    'std_msgs/String',
  );

  const callEnable = useRosService(
    ros,
    `/${namespace}/enable_realtime_conversation`,
    'std_srvs/SetBool',
  );
  const callAddContext = useRosService(
    ros,
    `/${namespace}/add_realtime_context`,
    'std_srvs/Trigger',
  );

  useEffect(() => {
    if (!content) return;
    try {
      const parsed = JSON.parse(content.data);
      if (parsed.role && parsed.content) {
        setMessages((prev) => [
          ...prev,
          { role: parsed.role, content: parsed.content, timestamp: Date.now() },
        ]);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: content.data, timestamp: Date.now() },
      ]);
    }
  }, [content]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const toggleConversation = async () => {
    const next = !enabled;
    await callEnable({ data: next });
    setEnabled(next);
  };

  const sendMessage = async () => {
    if (!input.trim()) return;
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: input, timestamp: Date.now() },
    ]);
    await callAddContext({ data: input });
    setInput('');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ color: 'var(--t-text-muted)', fontSize: 14, fontWeight: 'bold' }}>会話</span>
        <button
          onClick={toggleConversation}
          style={{
            padding: '6px 14px', borderRadius: 20, border: 'none', cursor: 'pointer',
            background: enabled ? '#00cc66' : 'var(--t-border2)', color: 'var(--t-text)', fontSize: 13,
          }}
        >
          {enabled ? '会話中' : '会話OFF'}
        </button>
      </div>
      <div
        ref={scrollRef}
        style={{
          flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6,
          padding: 8, background: 'var(--t-overlay)', borderRadius: 8,
        }}
      >
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
              background: m.role === 'user' ? '#ff6600' : 'var(--t-surface2)',
              color: 'var(--t-text)', padding: '6px 12px', borderRadius: 12, maxWidth: '80%', fontSize: 13,
            }}
          >
            {m.content}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
          placeholder="メッセージを入力..."
          style={{
            flex: 1, padding: '8px 12px', borderRadius: 20, border: '1px solid var(--t-border2)',
            background: 'var(--t-surface)', color: 'var(--t-text)', fontSize: 13,
          }}
        />
        <button
          onClick={sendMessage}
          style={{
            padding: '8px 16px', borderRadius: 20, border: 'none',
            background: '#ff6600', color: 'var(--t-text)', cursor: 'pointer', fontSize: 13,
          }}
        >
          送信
        </button>
      </div>
    </div>
  );
}
