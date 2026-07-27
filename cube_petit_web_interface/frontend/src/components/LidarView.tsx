import { useEffect, useRef, useState } from 'react';
import * as ROSLIB from 'roslib';
import { useRosTopic } from '../hooks/useRosTopic';
import { getAccentColor } from '../utils/theme';

interface LaserScan {
  angle_min: number;
  angle_max: number;
  angle_increment: number;
  ranges: number[];
  range_max: number;
}

interface Props {
  ros: ROSLIB.Ros | null;
  namespace: string;
  enabled: boolean;
  width: number;
  height: number;
}

interface ViewState {
  scale: number;
  rotation: number;
  offsetX: number;
  offsetY: number;
}

function getDistance(a: React.Touch, b: React.Touch) {
  return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
}

function getAngle(a: React.Touch, b: React.Touch) {
  return Math.atan2(b.clientY - a.clientY, b.clientX - a.clientX);
}

// rosbridge越しの常時subscribeは重いため、ボタンで明示的にONにした時だけ購読する。
// OFFにする・アンマウントする際は useRosTopic 側のクリーンアップで必ずunsubscribeされる。
const LIDAR_THROTTLE_MS = 300; // 約3.3Hz。表示用途としては十分

export function LidarView({ ros, namespace, enabled, width, height }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [active, setActive] = useState(false);
  const subscribing = active && enabled;
  const scan = useRosTopic<LaserScan>(
    ros, `/${namespace}/scan`, 'sensor_msgs/LaserScan', subscribing,
    { throttleRate: LIDAR_THROTTLE_MS, queueLength: 1 }, // queue_length:1で古いフレームを溜めず常に最新のみ受信
  );

  const [view, setView] = useState<ViewState>({ scale: 1, rotation: 0, offsetX: 0, offsetY: 0 });
  const viewRef = useRef(view);
  viewRef.current = view;

  // タッチ操作用
  const lastTouchRef = useRef<{ dist: number; angle: number; midX: number; midY: number } | null>(null);
  // ドラッグ操作用
  const dragRef = useRef<{ x: number; y: number } | null>(null);

  // 描画
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { scale, rotation, offsetX, offsetY } = view;
    const cx = width / 2 + offsetX;
    const cy = height / 2 + offsetY;

    ctx.fillStyle = '#1a1a2e';
    ctx.fillRect(0, 0, width, height);

    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(rotation);

    // 1mグリッド（常に表示）
    const BASE_RANGE = scan?.range_max ?? 6;
    const baseScale = Math.min(width, height) / 2 / BASE_RANGE;
    const s = baseScale * scale;
    const gridRange = Math.ceil(Math.max(width, height) / s) + 1;
    ctx.strokeStyle = 'rgba(255,255,255,0.08)';
    ctx.lineWidth = 1;
    for (let i = -gridRange; i <= gridRange; i++) {
      const p = i * s;
      ctx.beginPath();
      ctx.moveTo(p, -gridRange * s);
      ctx.lineTo(p, gridRange * s);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(-gridRange * s, p);
      ctx.lineTo(gridRange * s, p);
      ctx.stroke();
    }
    ctx.strokeStyle = 'rgba(255,255,255,0.2)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, -gridRange * s);
    ctx.lineTo(0, gridRange * s);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(-gridRange * s, 0);
    ctx.lineTo(gridRange * s, 0);
    ctx.stroke();

    // LiDAR点群
    if (scan && subscribing) {
      ctx.fillStyle = '#00ff88';
      scan.ranges.forEach((r, i) => {
        if (r === 0 || r > scan.range_max) return;
        const angle = scan.angle_min + i * scan.angle_increment;
        const x = r * Math.cos(angle) * s;
        const y = -r * Math.sin(angle) * s;
        ctx.beginPath();
        ctx.arc(x, y, 2, 0, Math.PI * 2);
        ctx.fill();
      });
    }

    // ロボット（常に表示、接続中ロボットの色）
    const robotColor = getAccentColor();
    ctx.strokeStyle = robotColor;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(0, 0, 12, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = robotColor;
    ctx.beginPath();
    ctx.arc(0, 0, 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(0, -20);
    ctx.stroke();

    ctx.restore();
  }, [scan, subscribing, width, height, view]);

  // ピンチ・回転（タッチ）
  const handleTouchStart = (e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      lastTouchRef.current = {
        dist: getDistance(e.touches[0], e.touches[1]),
        angle: getAngle(e.touches[0], e.touches[1]),
        midX: (e.touches[0].clientX + e.touches[1].clientX) / 2,
        midY: (e.touches[0].clientY + e.touches[1].clientY) / 2,
      };
    } else if (e.touches.length === 1) {
      dragRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    }
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    e.preventDefault();
    if (e.touches.length === 2 && lastTouchRef.current) {
      const newDist = getDistance(e.touches[0], e.touches[1]);
      const newAngle = getAngle(e.touches[0], e.touches[1]);
      const scaleDelta = newDist / lastTouchRef.current.dist;
      const rotDelta = newAngle - lastTouchRef.current.angle;
      setView((v) => ({
        ...v,
        scale: Math.max(0.2, Math.min(10, v.scale * scaleDelta)),
        rotation: v.rotation + rotDelta,
      }));
      lastTouchRef.current = {
        dist: newDist,
        angle: newAngle,
        midX: (e.touches[0].clientX + e.touches[1].clientX) / 2,
        midY: (e.touches[0].clientY + e.touches[1].clientY) / 2,
      };
    } else if (e.touches.length === 1 && dragRef.current) {
      const dx = e.touches[0].clientX - dragRef.current.x;
      const dy = e.touches[0].clientY - dragRef.current.y;
      setView((v) => ({ ...v, offsetX: v.offsetX + dx, offsetY: v.offsetY + dy }));
      dragRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    }
  };

  const handleTouchEnd = () => {
    lastTouchRef.current = null;
    dragRef.current = null;
  };

  // マウスホイールでズーム
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setView((v) => ({ ...v, scale: Math.max(0.2, Math.min(10, v.scale * delta)) }));
  };

  // マウスドラッグ
  const handleMouseDown = (e: React.MouseEvent) => {
    dragRef.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!dragRef.current) return;
    const dx = e.clientX - dragRef.current.x;
    const dy = e.clientY - dragRef.current.y;
    setView((v) => ({ ...v, offsetX: v.offsetX + dx, offsetY: v.offsetY + dy }));
    dragRef.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseUp = () => { dragRef.current = null; };

  // リセットボタン
  const resetView = () => setView({ scale: 1, rotation: 0, offsetX: 0, offsetY: 0 });

  return (
    <div style={{ position: 'relative', width, height }}>
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        style={{ borderRadius: 8, cursor: 'grab', touchAction: 'none' }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      />
      <button
        onClick={resetView}
        style={{
          position: 'absolute', bottom: 8, right: 8,
          padding: '4px 10px', borderRadius: 12, border: 'none',
          background: 'rgba(255,255,255,0.15)', color: '#fff',
          fontSize: 12, cursor: 'pointer',
        }}
      >
        リセット
      </button>
      <button
        onClick={() => setActive((v) => !v)}
        style={{
          position: 'absolute', top: 8, right: 8,
          padding: '4px 10px', borderRadius: 20, border: 'none', cursor: 'pointer',
          background: active ? 'var(--t-accent)' : 'rgba(255,255,255,0.15)', color: '#fff', fontSize: 12,
        }}
      >
        LiDAR表示
      </button>
      {!subscribing && (
        <div style={{
          position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
          pointerEvents: 'none', color: 'rgba(255,255,255,0.5)', fontSize: 12,
        }}>
          ボタンで表示開始
        </div>
      )}
    </div>
  );
}
