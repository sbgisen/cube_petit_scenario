import { useEffect, useRef, useState } from 'react';
import * as ROSLIB from 'roslib';
import { useRosTopic } from '../hooks/useRosTopic';
import type { ConversationMessage } from '../types/ros';

interface ConversationMsg {
  data: string;
}

interface Props {
  ros: ROSLIB.Ros | null;
  namespace: string;
  apiUrl: string;
  isActive: boolean;
}

const POLL_INTERVAL_MS = 3000;

export function ConversationPanel({ ros, namespace, apiUrl, isActive }: Props) {
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [input, setInput] = useState('');
  const [images, setImages] = useState<string[]>([]);
  const [canSend, setCanSend] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const content = useRosTopic<ConversationMsg>(
    ros,
    `/${namespace}/realtime_conversation_content`,
    'std_msgs/String',
  );

  // ロボットの発話をメッセージ履歴に追加
  useEffect(() => {
    if (!content?.data) return;
    const raw = content.data;
    let role: 'user' | 'assistant' = 'assistant';
    let text = raw;
    if (raw.startsWith('robot: ')) {
      role = 'assistant';
      text = raw.slice('robot: '.length);
    } else if (raw.startsWith('user: ')) {
      role = 'user';
      text = raw.slice('user: '.length);
    }
    setMessages(prev => [...prev, { role, content: text, timestamp: Date.now() }]);
  }, [content]);

  // 新メッセージ時に一番下へスクロール
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // can_receive_message のポーリング
  useEffect(() => {
    const poll = () => {
      fetch(`${apiUrl}/ros/conversation/status?namespace=${namespace}`)
        .then(r => r.json())
        .then(d => setCanSend(d.can_receive_message))
        .catch(() => {});
    };
    poll();
    const timer = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [apiUrl, namespace]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    files.forEach(file => {
      const reader = new FileReader();
      reader.onload = () => setImages(prev => [...prev, reader.result as string]);
      reader.readAsDataURL(file);
    });
    e.target.value = '';
  };

  const removeImage = (index: number) => {
    setImages(prev => prev.filter((_, i) => i !== index));
  };

  const sendMessage = () => {
    if (!input.trim() && images.length === 0) return;
    const text = input;
    const imgs = images;
    setInput('');
    setImages([]);
    if (text.trim()) {
      setMessages(prev => [...prev, { role: 'user', content: text, timestamp: Date.now() }]);
    }
    fetch(`${apiUrl}/ros/conversation/context?namespace=${namespace}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ context: text, role: 2, images: imgs }),
    }).catch(() => {});
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 8 }}>
      {/* ヘッダー */}
      <div style={{ display: 'flex', justifyContent: 'flex-start', alignItems: 'center', gap: 8 }}>
        <span style={{ color: 'var(--t-text-muted)', fontSize: 14, fontWeight: 'bold' }}>会話</span>
        <span style={{
          fontSize: 11, padding: '2px 8px', borderRadius: 10,
          background: canSend ? 'rgba(0,200,100,0.2)' : 'rgba(255,255,255,0.08)',
          color: canSend ? '#00cc66' : 'var(--t-text-muted)',
        }}>
          {canSend ? '受信可' : '処理中'}
        </span>
      </div>

      {/* メッセージ一覧 */}
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
              color: 'var(--t-text)', padding: '6px 12px', borderRadius: 12,
              maxWidth: '80%', fontSize: 13,
            }}
          >
            {m.content}
          </div>
        ))}
      </div>

      {/* 画像プレビュー */}
      {images.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', padding: '4px 0' }}>
          {images.map((src, i) => (
            <div key={i} style={{ position: 'relative' }}>
              <img src={src} style={{ width: 56, height: 56, objectFit: 'cover', borderRadius: 6 }} />
              <button
                onClick={() => removeImage(i)}
                style={{
                  position: 'absolute', top: -4, right: -4,
                  width: 16, height: 16, borderRadius: '50%', border: 'none',
                  background: '#ff4444', color: '#fff', fontSize: 10, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0,
                }}
              >
                x
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 入力欄 */}
      <div style={{ display: 'flex', gap: 6 }}>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={!isActive}
          title="画像を添付"
          style={{
            padding: '8px 10px', borderRadius: 20, border: 'none',
            background: 'var(--t-border2)', color: 'var(--t-text)',
            cursor: isActive ? 'pointer' : 'not-allowed', fontSize: 16,
            opacity: isActive ? 1 : 0.5,
          }}
        >
          +
        </button>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
          placeholder={isActive ? 'コンテキストを追加...' : '会話をONにしてください'}
          disabled={!isActive}
          style={{
            flex: 1, padding: '8px 12px', borderRadius: 20,
            border: '1px solid var(--t-border2)',
            background: isActive ? 'var(--t-surface)' : 'var(--t-overlay)',
            color: 'var(--t-text)', fontSize: 13,
            opacity: isActive ? 1 : 0.5,
          }}
        />
        <button
          onClick={sendMessage}
          disabled={!isActive || (!input.trim() && images.length === 0)}
          style={{
            padding: '8px 16px', borderRadius: 20, border: 'none',
            background: isActive && (input.trim() || images.length > 0) ? '#ff6600' : 'var(--t-border2)',
            color: 'var(--t-text)', cursor: isActive ? 'pointer' : 'not-allowed', fontSize: 13,
          }}
        >
          送信
        </button>
      </div>
    </div>
  );
}
