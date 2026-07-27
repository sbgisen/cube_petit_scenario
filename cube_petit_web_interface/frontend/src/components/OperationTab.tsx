import { useCallback, useEffect, useRef, useState } from 'react';
import * as ROSLIB from 'roslib';
import { MapView, type MapMode, type MapFrame, type MapPlace, type MapRoomOverlay } from './MapView';
import { MapView3D } from './MapView3D';
import { Joystick } from './Joystick';
import { CameraView } from './CameraView';
import { QuickPhraseGrid } from './QuickPhraseGrid';
import { Icon } from './Icon';
import { useRosPublisher, useRosTopic } from '../hooks/useRosTopic';
import { useRosAction } from '../hooks/useRosAction';
import { useRosService } from '../hooks/useRosService';
import { useSpeechServerAlive } from '../hooks/useRosNodeAlive';
import type { LayerVisibility } from '../types/ros';

type RunMode = 'stopped' | 'map_creation' | 'autonomous' | 'manual';

const RUN_MODE_INFO: Record<RunMode, { label: string; color: string; icon: string }> = {
  stopped:      { label: '未起動',         color: '#777777', icon: 'power_off' },
  map_creation: { label: 'マップ作成モード', color: '#e6c200', icon: 'edit_location_alt' },
  autonomous:   { label: '自律移動モード',   color: '#00cc66', icon: 'smart_toy' },
  manual:       { label: '手動操作モード',   color: '#0088ff', icon: 'sports_esports' },
};

function deriveRunMode(status: Record<string, boolean> | null): RunMode {
  if (!status?.bringup) return 'stopped';
  if (status.create_map) return 'map_creation';
  if (status.navigation) return 'autonomous';
  return 'manual';
}

interface Props {
  ros: ROSLIB.Ros | null;
  namespace: string;
  apiUrl: string;
  quickPhrases: string[];
  setQuickPhrases: (phrases: string[]) => void;
}

const LAYER_LABELS: { key: keyof LayerVisibility; label: string }[] = [
  { key: 'lidar',   label: 'LiDAR' },
  { key: 'camera',  label: 'カメラ' },
  { key: 'doa',     label: '音源' },
  { key: 'people',  label: '人' },
  { key: 'map',     label: 'マップ' },
  { key: 'costmap', label: 'コスト' },
  { key: 'plan',    label: 'プラン' },
];

export function OperationTab({ ros, namespace, apiUrl, quickPhrases, setQuickPhrases }: Props) {
  const [layers, setLayers] = useState<LayerVisibility>({
    // lidar/camera: rosbridge越しの購読は重いため、デフォルトOFF(レイヤーボタンでONにした時だけ購読)
    lidar: false, map: true, costmap: true, plan: true, people: true, doa: true, camera: false,
  });
  const [is3D, setIs3D] = useState(false);
  const [mapMode, setMapMode] = useState<MapMode>('view');
  const [mapFrame, setMapFrame] = useState<MapFrame>('base_link');
  const [showPOI, setShowPOI] = useState(false);
  const [poiMap, setPoiMap] = useState(() => localStorage.getItem('nav_selected_map') || '');
  const [poiMaps, setPoiMaps] = useState<string[]>([]);
  const [places, setPlaces] = useState<MapPlace[]>([]);
  const [rooms, setRooms] = useState<MapRoomOverlay[]>([]);

  useEffect(() => {
    fetch(`${apiUrl}/map/list`)
      .then(r => r.json())
      .then(d => {
        const list: string[] = d.maps || [];
        setPoiMaps(list);
        setPoiMap(p => (p && list.includes(p)) ? p : (list[0] || ''));
      })
      .catch(() => {});
  }, [apiUrl]);

  useEffect(() => {
    if (!showPOI || !poiMap) { setPlaces([]); setRooms([]); return; }
    fetch(`${apiUrl}/map/places?map_name=${encodeURIComponent(poiMap)}`)
      .then(r => r.json()).then(d => setPlaces(
        (d.places || []).map((p: { name: string; category: string; pose?: [number, number, number]; x?: number; y?: number; yaw?: number }) => ({
          name: p.name,
          category: p.category,
          x: p.pose?.[0] ?? p.x ?? 0,
          y: p.pose?.[1] ?? p.y ?? 0,
          yaw: p.pose?.[2] ?? p.yaw ?? 0,
        }))
      )).catch(() => {});
    fetch(`${apiUrl}/map/rooms?map_name=${encodeURIComponent(poiMap)}`)
      .then(r => r.json()).then(d => setRooms(d.rooms || [])).catch(() => {});
  }, [showPOI, poiMap, apiUrl]);

  const handleSetMapMode = (m: MapMode) => {
    setMapMode(m);
    if (m === 'goal' || m === 'initialpose') setIs3D(false);
  };
  const [mapSize, setMapSize] = useState<{ w: number; h: number }>({ w: 400, h: 400 });

  const navStatus = useRosTopic<{ status_list: { status: number }[] }>(
    ros, `/${namespace}/navigation/navigate_to_pose/_action/status`, 'action_msgs/GoalStatusArray', true,
  );
  const navFeedback = useRosTopic<{ feedback: { distance_remaining: number } }>(
    ros, `/${namespace}/navigation/navigate_to_pose/_action/feedback`, 'nav2_msgs/action/NavigateToPose_FeedbackMessage', true,
  );

  const latestStatus = navStatus?.status_list?.slice(-1)[0]?.status ?? -1;
  const distRemaining = navFeedback?.feedback?.distance_remaining;

  const cancelNav = useRosService(ros, `/${namespace}/navigation/navigate_to_pose/_action/cancel_goal`, 'action_msgs/srv/CancelGoal');
  const publishGoal = useRosPublisher(ros, `/${namespace}/navigation/goal_pose`, 'geometry_msgs/PoseStamped');
  const publishInitialPose = useRosPublisher(ros, `/${namespace}/navigation/initialpose`, 'geometry_msgs/PoseWithCovarianceStamped');
  const sendSpeech = useRosAction(ros, `/${namespace}/speech_action_server`, 'cube_petit_speech_msgs/action/Speech');
  void useSpeechServerAlive(namespace);
  const speak = (phrase: string) => sendSpeech({ text: phrase, emotion: 'happy', emotion_level: 2, pitch: 100, speed: 100, volume: 100 });
  const addPhrase = (phrase: string) => setQuickPhrases([...quickPhrases, phrase]);

  const handleGoal = useCallback((rosX: number, rosY: number, yaw: number) => {
    publishGoal({
      header: { stamp: { sec: 0, nanosec: 0 }, frame_id: 'map' },
      pose: {
        position: { x: rosX, y: rosY, z: 0 },
        orientation: { x: 0, y: 0, z: Math.sin(yaw / 2), w: Math.cos(yaw / 2) },
      },
    });
  }, [publishGoal]);

  const handleInitialPose = useCallback((rosX: number, rosY: number, yaw: number) => {
    publishInitialPose({
      header: { stamp: { sec: 0, nanosec: 0 }, frame_id: 'map' },
      pose: {
        pose: {
          position: { x: rosX, y: rosY, z: 0 },
          orientation: { x: 0, y: 0, z: Math.sin(yaw / 2), w: Math.cos(yaw / 2) },
        },
        covariance: [0.25,0,0,0,0,0, 0,0.25,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0.07],
      },
    });
  }, [publishInitialPose]);

  const mapContainerRef = useRef<HTMLDivElement>(null);
  const controlsRef = useRef<HTMLDivElement>(null);
  const [controlsHeight, setControlsHeight] = useState(0);

  // マップコンテナのサイズを計測
  useEffect(() => {
    const el = mapContainerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) {
        setMapSize({ w: Math.floor(width), h: Math.floor(height) });
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // レイヤーボタン行の高さを計測
  useEffect(() => {
    const el = controlsRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      setControlsHeight(entry.contentRect.height);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const toggleLayer = (key: keyof LayerVisibility) =>
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }));

  // 現在のモード(マップ作成/自律移動/手動操作)表示用。/launch/status の
  // create_map・navigation・bringup の起動状況から導出する
  const [launchStatus, setLaunchStatus] = useState<Record<string, boolean> | null>(null);
  useEffect(() => {
    const poll = () => fetch(`${apiUrl}/launch/status`).then(r => r.json()).then(setLaunchStatus).catch(() => {});
    poll();
    const t = setInterval(poll, 3000);
    return () => clearInterval(t);
  }, [apiUrl]);
  const runMode = deriveRunMode(launchStatus);
  const runModeInfo = RUN_MODE_INFO[runMode];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, height: '100%', overflow: 'hidden', position: 'relative' }}>
      {/* 全幅コントロール行 */}
      <div ref={controlsRef} style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', flexShrink: 0 }}>
        {LAYER_LABELS.map(({ key, label }) => (
          <button key={key} onClick={() => toggleLayer(key)} style={{
            padding: '6px 14px', borderRadius: 20, border: 'none', cursor: 'pointer',
            background: layers[key] ? 'var(--t-accent)' : 'var(--t-border)', color: 'var(--t-text)', fontSize: 13,
          }}>
            {label}
          </button>
        ))}
        <div style={{ display: 'flex', background: 'var(--t-border)', borderRadius: 20, overflow: 'hidden', alignItems: 'center' }}>
          <button onClick={() => setShowPOI(v => !v)} style={{
            padding: '6px 14px', border: 'none', cursor: 'pointer', fontSize: 13,
            background: showPOI ? '#aa44ff' : 'transparent', color: 'var(--t-text)',
          }}>
            ポイント
          </button>
          {showPOI && poiMaps.length > 0 && (
            <select value={poiMap} onChange={e => setPoiMap(e.target.value)}
              style={{ padding: '4px 4px', fontSize: 12, background: '#333', color: '#fff', border: 'none', borderLeft: '1px solid #555', maxWidth: 110, cursor: 'pointer' }}>
              {poiMaps.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          )}
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {/* 操作/目標モード */}
          <div style={{ display: 'flex', background: '#222', borderRadius: 20, overflow: 'hidden' }}>
            {([['view', '🔄 操作'], ['goal', '📍 目標'], ['initialpose', '📌 初期']] as [MapMode, string][]).map(([m, label]) => (
              <button key={m} onClick={() => handleSetMapMode(m)} style={{
                padding: '6px 14px', border: 'none', cursor: 'pointer', fontSize: 13,
                background: mapMode === m ? '#0088ff' : 'transparent', color: '#fff',
              }}>
                {label}
              </button>
            ))}
          </div>
          {/* 2D/3D */}
          <div style={{ display: 'flex', background: '#222', borderRadius: 20, overflow: 'hidden' }}>
            {(['2D', '3D'] as const).map((m) => {
              const disabled = m === '3D' && mapMode === 'goal';
              return (
                <button key={m} onClick={() => !disabled && setIs3D(m === '3D')} style={{
                  padding: '6px 14px', border: 'none', fontSize: 13,
                  cursor: disabled ? 'not-allowed' : 'pointer',
                  background: (is3D ? '3D' : '2D') === m ? '#555' : 'transparent',
                  color: disabled ? '#777' : '#fff',
                }}>
                  {m}
                </button>
              );
            })}
          </div>
          {/* フレーム選択 (2Dのみ) */}
          {!is3D && (
            <div style={{ display: 'flex', background: '#222', borderRadius: 20, overflow: 'hidden' }}>
              {(['base_link', 'odom', 'map'] as MapFrame[]).map((f) => (
                <button key={f} onClick={() => setMapFrame(f)} style={{
                  padding: '6px 12px', border: 'none', fontSize: 12, cursor: 'pointer',
                  background: mapFrame === f ? '#336633' : 'transparent',
                  color: '#fff',
                }}>
                  {f === 'base_link' ? 'base' : f}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 現在のモード表示(マップ作成/自律移動/手動操作/未起動) */}
        <div title="rosbridge/launch/statusのcreate_map・navigation・bringupから判定" style={{
          display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 20,
          background: `${runModeInfo.color}22`, color: runModeInfo.color, fontSize: 13,
          marginLeft: 'auto', flexShrink: 0,
        }}>
          <Icon name={runModeInfo.icon} size={16} />
          {runModeInfo.label}
        </div>
      </div>

      <style>{`@keyframes navPulse { 0%,100%{opacity:1} 50%{opacity:0.45} }`}</style>

      {/* 下段: マップ + 右カラム */}
      <div style={{ display: 'flex', gap: 12, flex: 1, minHeight: 0, overflow: 'hidden', alignItems: 'stretch' }}>
        {/* 左: マップ */}
        <div ref={mapContainerRef} style={{ flex: 3, minWidth: 0, minHeight: 0, overflow: 'hidden', position: 'relative' }}>
          {is3D
            ? <MapView3D ros={ros} namespace={namespace} layers={layers} width={mapSize.w} height={mapSize.h} />
            : <MapView   ros={ros} namespace={namespace} layers={layers} width={mapSize.w} height={mapSize.h} mode={mapMode} frame={mapFrame} onGoal={handleGoal} onInitialPose={handleInitialPose} places={showPOI ? places : undefined} rooms={showPOI ? rooms : undefined} />
          }
          {/* ナビゲーションステータスオーバーレイ */}
          {(() => {
            const cfg =
              latestStatus === 2 ? { label: '移動中', sub: distRemaining != null ? `残り ${distRemaining.toFixed(1)} m` : '', bg: 'rgba(0,80,200,0.82)', pulse: true } :
              latestStatus === 4 ? { label: '到着', sub: '', bg: 'rgba(0,150,60,0.82)', pulse: false } :
              latestStatus === 6 ? { label: '移動失敗', sub: '', bg: 'rgba(180,20,20,0.82)', pulse: false } :
              latestStatus === 5 ? { label: 'キャンセル', sub: '', bg: 'rgba(80,80,80,0.82)', pulse: false } :
              latestStatus === 1 ? { label: '受付中…', sub: '', bg: 'rgba(60,60,60,0.82)', pulse: true } :
              null;
            if (!cfg) return null;
            const canCancel = latestStatus === 1 || latestStatus === 2;
            return (
              <div style={{
                position: 'absolute', top: 12, left: 12, zIndex: 10,
                background: cfg.bg, borderRadius: 12, padding: '10px 18px',
                animation: cfg.pulse ? 'navPulse 1.2s ease-in-out infinite' : 'none',
              }}>
                <div style={{ color: '#fff', fontSize: 28, fontWeight: 'bold', lineHeight: 1.1 }}>{cfg.label}</div>
                {cfg.sub && <div style={{ color: 'rgba(255,255,255,0.8)', fontSize: 15, marginTop: 3 }}>{cfg.sub}</div>}
                {canCancel && (
                  <button onClick={() => cancelNav({ goal_info: { goal_id: { uuid: Array(16).fill(0) }, stamp: { sec: 0, nanosec: 0 } } }).catch(() => {})}
                    style={{ marginTop: 8, padding: '4px 14px', borderRadius: 8, border: 'none', cursor: 'pointer', background: 'rgba(255,255,255,0.25)', color: '#fff', fontSize: 13 }}>
                    キャンセル
                  </button>
                )}
              </div>
            );
          })()}
        </div>

        {/* 右: カメラ + クイックフレーズ */}
        <div style={{ flex: 1, minWidth: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <CameraView ros={ros} namespace={namespace} enabled={layers.camera} fitWidth />
          <div style={{ marginTop: 8 }}>
            <QuickPhraseGrid phrases={quickPhrases} onSpeak={speak} onAdd={addPhrase} speechAvailable={true} />
          </div>
        </div>
      </div>

      {/* ジョイスティック（右下固定） */}
      <div style={{ position: 'absolute', bottom: 12, right: 12 }}>
        <Joystick ros={ros} namespace={namespace} />
      </div>
    </div>
  );
}
