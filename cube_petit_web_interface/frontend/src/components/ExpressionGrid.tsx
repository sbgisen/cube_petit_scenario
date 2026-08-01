import { useState } from 'react';
import * as ROSLIB from 'roslib';
import { useRosPublisher } from '../hooks/useRosTopic';

interface Props {
  ros: ROSLIB.Ros | null;
  namespace: string;
}

interface ExpressionDef {
  name: string;
  emoji: string;
  label: string;
}

// 14 expressions supported by cube_petit_facial_animation (see frontend/emote/*.js in that package).
const EXPRESSIONS: ExpressionDef[] = [
  { name: 'normal',    emoji: '🙂',    label: 'ふつう' },
  { name: 'happy',     emoji: '😊',    label: 'うれしい' },
  { name: 'excited',   emoji: '🤩',    label: 'わくわく' },
  { name: 'love',      emoji: '😍',    label: 'だいすき' },
  { name: 'wink',      emoji: '😉',    label: 'ウインク' },
  { name: 'shy',       emoji: '😳',    label: 'てれてれ' },
  { name: 'surprised', emoji: '😲',    label: 'びっくり' },
  { name: 'curious',   emoji: '👀',    label: 'きになる' },
  { name: 'thinking',  emoji: '🤔',    label: 'かんがえちゅう' },
  { name: 'puzzled',   emoji: '😕',    label: 'こまった' },
  { name: 'dizzy',     emoji: '😵‍💫', label: 'めまい' },
  { name: 'sleepy',    emoji: '😪',    label: 'ねむい' },
  { name: 'sad',       emoji: '😢',    label: 'かなしい' },
  { name: 'angry',     emoji: '😠',    label: 'ぷんぷん' },
];

const btnBase: React.CSSProperties = {
  padding: '8px 4px', borderRadius: 12, border: '2px solid transparent', cursor: 'pointer',
  background: 'var(--t-surface2)', color: 'var(--t-text)', fontSize: 11, lineHeight: 1.3,
  textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
};

export function ExpressionGrid({ ros, namespace }: Props) {
  const publish = useRosPublisher(ros, `/${namespace}/facial_expression/expression_command`, 'cube_petit_facial_animation_msgs/FaceExpression');
  // current_expression is not published by any node yet (checked cube_petit_facial_animation),
  // so fall back to highlighting the last tapped button instead of subscribing to robot state.
  const [lastTapped, setLastTapped] = useState<string | null>(null);

  const handleTap = (name: string) => {
    publish({ expression: name });
    setLastTapped(name);
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
      {EXPRESSIONS.map(({ name, emoji, label }) => {
        const active = lastTapped === name;
        return (
          <button
            key={name}
            onClick={() => handleTap(name)}
            style={{
              ...btnBase,
              borderColor: active ? 'var(--t-accent)' : 'transparent',
            }}
            onMouseDown={(e) => (e.currentTarget.style.background = 'var(--t-accent)')}
            onMouseUp={(e) => (e.currentTarget.style.background = 'var(--t-surface2)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--t-surface2)')}
            onTouchStart={(e) => (e.currentTarget.style.background = 'var(--t-accent)')}
            onTouchEnd={(e) => (e.currentTarget.style.background = 'var(--t-surface2)')}
          >
            <span style={{ fontSize: 20 }}>{emoji}</span>
            <span>{label}</span>
          </button>
        );
      })}
    </div>
  );
}
