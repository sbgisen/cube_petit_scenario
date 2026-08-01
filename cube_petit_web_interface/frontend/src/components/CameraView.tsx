import { useState } from 'react';
import * as ROSLIB from 'roslib';
import NoPhotographyIcon from '@mui/icons-material/NoPhotography';
import PhotoCameraIcon from '@mui/icons-material/PhotoCamera';
import { useRosTopic } from '../hooks/useRosTopic';

interface CompressedImage {
  format: string;
  data: string; // base64
}

interface Props {
  ros: ROSLIB.Ros | null;
  namespace: string;
  enabled: boolean;
  height?: number;
  flex?: boolean;
  fitWidth?: boolean; // 幅いっぱい・縦横比維持
  // 親にON/OFFボタンがない配置(会話タブ等)用の内蔵トグル。
  // 操作タブは既存の「カメラ」レイヤーボタン(enabled)が唯一のスイッチなので使わない
  toggleable?: boolean;
}

// rosbridge越しの常時subscribeは重いため、ボタンで明示的にONにした時だけ購読する。
// OFFにする・アンマウントする際は useRosTopic 側のクリーンアップで必ずunsubscribeされる。
// 約1fps。会場WiFiの実効帯域が細い(2026-07-14撮影時 ~0.5Mbps)ため控えめに。
// 帯域に余裕がある環境なら200(5fps)まで戻してよい
const CAMERA_THROTTLE_MS = 1000;

// カメラ画像が来ていない間のプレースホルダーの縦横比。実際の解像度が判明したら
// (実機によってRealSenseのcolorストリーム解像度が違いうるため)localStorageに
// 覚えておき、次回以降そのプレースホルダーの縦横比として使う(初期値はRealSenseの
// 一般的なデフォルト16:9を仮置き)
const ASPECT_RATIO_KEY = 'camera_aspect_ratio';

export function CameraView({ ros, namespace, enabled, height = 200, flex = false, fitWidth = false,
                             toggleable = false }: Props) {
  const [active, setActive] = useState(false);
  const subscribing = enabled && (!toggleable || active);
  const [aspectRatio, setAspectRatio] = useState<string>(() => localStorage.getItem(ASPECT_RATIO_KEY) || '16/9');

  const image = useRosTopic<CompressedImage>(
    ros,
    `/${namespace}/camera/camera/color/image_raw/compressed`,
    'sensor_msgs/CompressedImage',
    subscribing,
    { throttleRate: CAMERA_THROTTLE_MS, queueLength: 1 }, // queue_length:1で古いフレームを溜めず常に最新のみ受信
  );

  const onImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    if (!img.naturalWidth || !img.naturalHeight) return;
    const ratio = `${img.naturalWidth}/${img.naturalHeight}`;
    if (ratio !== aspectRatio) {
      setAspectRatio(ratio);
      localStorage.setItem(ASPECT_RATIO_KEY, ratio);
    }
  };

  const toggleButton = toggleable && (
    <button
      onClick={() => setActive((v) => !v)}
      style={{
        position: 'absolute', top: 6, right: 6, zIndex: 1,
        display: 'flex', alignItems: 'center', gap: 4,
        padding: '4px 10px', borderRadius: 20, border: 'none', cursor: 'pointer',
        background: active ? 'var(--t-accent)' : 'rgba(0,0,0,0.45)', color: '#fff', fontSize: 12,
      }}
    >
      <PhotoCameraIcon style={{ fontSize: 14 }} />
      カメラ表示
    </button>
  );

  const placeholder = (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, color: 'var(--t-border2)' }}>
      <NoPhotographyIcon style={{ fontSize: 40 }} />
      {!subscribing && (
        <span style={{ fontSize: 11 }}>
          {toggleable ? 'ボタンで表示開始' : '「カメラ」ボタンで表示開始'}
        </span>
      )}
    </div>
  );

  if (fitWidth) {
    return (
      <div style={{ position: 'relative', width: '100%', background: 'var(--t-surface)', borderRadius: 8, overflow: 'hidden' }}>
        {toggleButton}
        {image && subscribing ? (
          <img
            src={`data:image/${image.format};base64,${image.data}`}
            style={{ width: '100%', height: 'auto', display: 'block' }}
            onLoad={onImageLoad}
            alt="camera"
          />
        ) : (
          <div style={{ aspectRatio, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {placeholder}
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={{
      position: 'relative',
      ...(flex ? { flex: 1, minHeight: 0 } : { height, flexShrink: 0 }),
      background: 'var(--t-surface)', borderRadius: 8,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      overflow: 'hidden',
    }}>
      {toggleButton}
      {image && subscribing ? (
        <img
          src={`data:image/${image.format};base64,${image.data}`}
          style={{ width: '100%', height: '100%', objectFit: 'contain' }}
          onLoad={onImageLoad}
          alt="camera"
        />
      ) : (
        placeholder
      )}
    </div>
  );
}
