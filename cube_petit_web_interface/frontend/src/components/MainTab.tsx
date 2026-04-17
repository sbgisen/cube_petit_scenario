import { useEffect, useRef, useState } from 'react';
import * as ROSLIB from 'roslib';
import { MapView } from './MapView';
import { MapView3D } from './MapView3D';
import { Joystick } from './Joystick';
import { CameraView } from './CameraView';
import { AnimaPanel } from './AnimaPanel';
import { ConversationPanel } from './ConversationPanel';
import type { LayerVisibility } from '../types/ros';

interface Props {
  ros: ROSLIB.Ros | null;
  namespace: string;
}

const LAYER_LABELS: { key: keyof LayerVisibility; label: string }[] = [
  { key: 'lidar', label: 'LiDAR' },
  { key: 'people', label: '人' },
  { key: 'doa', label: 'DOA' },
  { key: 'camera', label: 'カメラ' },
];

export function MainTab({ ros, namespace }: Props) {
  const [layers, setLayers] = useState<LayerVisibility>({
    lidar: true, map: true, people: true, doa: true, camera: true,
  });
  const [is3D, setIs3D] = useState(false);
  const leftColRef = useRef<HTMLDivElement>(null);
  const [mapSize, setMapSize] = useState(380);

  useEffect(() => {
    const update = () => {
      // ヘッダー(~50px) + padding(24px) + レイヤーボタン(~40px) + gap(10px) + ジョイスティック(~140px) を引いた残り
      const available = window.innerHeight - 50 - 24 - 40 - 10 - 140;
      setMapSize(Math.max(280, Math.min(available, window.innerHeight * 0.6)));
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  const toggleLayer = (key: keyof LayerVisibility) =>
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }));

  return (
    <div style={{ display: 'flex', gap: 12, height: '100%', overflow: 'hidden' }}>
      {/* 左カラム: 2Dビュー + コントロール */}
      <div ref={leftColRef} style={{ display: 'flex', flexDirection: 'column', gap: 10, flexShrink: 0 }}>
        {/* レイヤー切替 + 2D/3Dトグル */}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          {LAYER_LABELS.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => toggleLayer(key)}
              style={{
                padding: '6px 14px', borderRadius: 20, border: 'none', cursor: 'pointer',
                background: layers[key] ? '#ff6600' : '#333',
                color: '#fff', fontSize: 13,
              }}
            >
              {label}
            </button>
          ))}
          <div style={{ marginLeft: 'auto', display: 'flex', background: '#222', borderRadius: 20, overflow: 'hidden' }}>
            {(['2D', '3D'] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => setIs3D(mode === '3D')}
                style={{
                  padding: '6px 14px', border: 'none', cursor: 'pointer', fontSize: 13,
                  background: (is3D ? '3D' : '2D') === mode ? '#0088ff' : 'transparent',
                  color: '#fff',
                }}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>

        {/* マップビュー */}
        {is3D
          ? <MapView3D ros={ros} namespace={namespace} layers={layers} width={mapSize} height={mapSize} />
          : <MapView ros={ros} namespace={namespace} layers={layers} width={mapSize} height={mapSize} />
        }

        {/* ジョイスティック */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ color: '#888', fontSize: 12 }}>移動</span>
          <Joystick ros={ros} namespace={namespace} />
        </div>
      </div>

      {/* 右カラム: カメラ + 会話 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1, minWidth: 0, overflow: 'hidden' }}>
        {/* カメラ */}
        <CameraView ros={ros} namespace={namespace} enabled={layers.camera} height={200} />

        {/* Anima状態 */}
        <AnimaPanel ros={ros} namespace={namespace} />

        {/* 会話 */}
        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
          <ConversationPanel ros={ros} namespace={namespace} />
        </div>
      </div>
    </div>
  );
}
