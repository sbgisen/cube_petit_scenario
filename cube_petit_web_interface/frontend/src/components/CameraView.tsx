import * as ROSLIB from 'roslib';
import NoPhotographyIcon from '@mui/icons-material/NoPhotography';
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
}

export function CameraView({ ros, namespace, enabled, height = 200, flex = false, fitWidth = false }: Props) {
  const image = useRosTopic<CompressedImage>(
    ros,
    `/${namespace}/camera/camera/color/image_raw/compressed`,
    'sensor_msgs/CompressedImage',
  );

  if (fitWidth) {
    return (
      <div style={{ width: '100%', background: 'var(--t-surface)', borderRadius: 8, overflow: 'hidden' }}>
        {image && enabled ? (
          <img
            src={`data:image/${image.format};base64,${image.data}`}
            style={{ width: '100%', height: 'auto', display: 'block' }}
            alt="camera"
          />
        ) : (
          <div style={{ aspectRatio: '4/3', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <NoPhotographyIcon style={{ color: 'var(--t-border2)', fontSize: 40 }} />
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={{
      ...(flex ? { flex: 1, minHeight: 0 } : { height, flexShrink: 0 }),
      background: 'var(--t-surface)', borderRadius: 8,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      overflow: 'hidden',
    }}>
      {image && enabled ? (
        <img
          src={`data:image/${image.format};base64,${image.data}`}
          style={{ width: '100%', height: '100%', objectFit: 'contain' }}
          alt="camera"
        />
      ) : (
        <NoPhotographyIcon style={{ color: 'var(--t-border2)', fontSize: 40 }} />
      )}
    </div>
  );
}
