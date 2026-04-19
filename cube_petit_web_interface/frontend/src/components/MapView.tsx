import { useEffect, useRef, useState, useMemo } from 'react';
import * as ROSLIB from 'roslib';
import { useRosTopic } from '../hooks/useRosTopic';
import { useRosTf } from '../hooks/useRosTf';
import type { LayerVisibility } from '../types/ros';

interface LaserScan {
  angle_min: number;
  angle_max: number;
  angle_increment: number;
  ranges: number[];
  range_max: number;
}

interface Marker {
  ns: string;
  pose: { position: { x: number; y: number } };
}

interface MarkerArray {
  markers: Marker[];
}

interface PoseStamped {
  pose: { orientation: { x: number; y: number; z: number; w: number } };
}

interface Odometry {
  pose: { pose: {
    position: { x: number; y: number; z: number };
    orientation: { x: number; y: number; z: number; w: number };
  } };
}

interface Path {
  poses: Array<{ pose: { position: { x: number; y: number } } }>;
}

interface OccupancyGrid {
  info: {
    resolution: number;
    width: number;
    height: number;
    origin: { position: { x: number; y: number; z: number } };
  };
  data: number[];
}

export type MapMode = 'view' | 'goal' | 'initialpose';
export type MapFrame = 'base_link' | 'odom' | 'map';

export interface MapPlace {
  name: string;
  x: number;
  y: number;
  yaw: number;
  category: string;
}

export interface MapRoomOverlay {
  name: string;
  points: [number, number][];
}

const CAT_COLORS: Record<string, string> = {
  dock: '#ff6600', favorite: '#ffcc00', patrol: '#00aaff', initial_pose: '#00ff88',
};
const ROOM_COLORS = ['#aa44ff', '#ff44aa', '#44aaff', '#ffaa44', '#44ffaa'];

interface Props {
  ros: ROSLIB.Ros | null;
  namespace: string;
  layers: LayerVisibility;
  width: number;
  height: number;
  mode?: MapMode;
  frame?: MapFrame;
  onGoal?: (rosX: number, rosY: number, yaw: number) => void;
  onInitialPose?: (rosX: number, rosY: number, yaw: number) => void;
  places?: MapPlace[];
  rooms?: MapRoomOverlay[];
}

interface ViewState {
  scale: number;
  rotation: number;
  offsetX: number;
  offsetY: number;
}

function quatToYaw(z: number, w: number) {
  return 2 * Math.atan2(z, w);
}

// LiDARスキャン角度オフセット: ROS x+(前方)がcanvas上向きになるよう補正
const SCAN_ANGLE_OFFSET = Math.PI / 2;

// BoyIcon SVG path (from @mui/icons-material/Boy)
const BOY_ICON_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="28" height="28"><path fill="#ff4444" d="M13.49 5.48c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm-3.6 13.9 1-4.4 2.1 2v6h2v-7.5l-2.1-2 .6-3c1.3 1.5 3.3 2.5 5.5 2.5v-2c-1.9 0-3.5-1-4.3-2.4l-1-1.6c-.4-.6-1-1-1.7-1-.3 0-.5.1-.8.1l-5.2 2.2v4.7h2v-3.4l1.8-.7-1.6 8.1-4.9-1-.4 2 7 1.4z"/></svg>`;

export function MapView({ ros, namespace, layers, width, height, mode = 'view', frame = 'base_link', onGoal, onInitialPose, places, rooms }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [view, setView] = useState<ViewState>({ scale: 1, rotation: 0, offsetX: 0, offsetY: 0 });
  // goal: 確定済みゴール。draft: ドラッグ中の仮ゴール
  const [goalPos, setGoalPos] = useState<{ x: number; y: number; yaw: number } | null>(null);
  const goalDraftRef = useRef<{ x: number; y: number; yaw: number } | null>(null);
  const [goalDraft, setGoalDraft] = useState<{ x: number; y: number; yaw: number } | null>(null);
  const poseDraftRef = useRef<{ x: number; y: number; yaw: number } | null>(null);
  const [poseDraft, setPoseDraft] = useState<{ x: number; y: number; yaw: number } | null>(null);

  // タッチハンドラ内でmodeを参照するためのref
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const viewRef = useRef(view);
  viewRef.current = view;

  const [iconReady, setIconReady] = useState(false);
  const boyIconImg = useMemo(() => {
    const img = new Image();
    img.onload = () => setIconReady(true);
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(BOY_ICON_SVG)}`;
    return img;
  }, []);

  const scan = useRosTopic<LaserScan>(ros, `/${namespace}/scan`, 'sensor_msgs/LaserScan', layers.lidar);
  const markers = useRosTopic<MarkerArray>(ros, '/object_detection/laser/marker', 'visualization_msgs/MarkerArray', layers.people);
  const doa = useRosTopic<PoseStamped>(ros, `/${namespace}/doa`, 'geometry_msgs/PoseStamped', layers.doa);
  const odom = useRosTopic<Odometry>(ros, `/${namespace}/odom`, 'nav_msgs/Odometry', frame === 'odom' || layers.costmap);
  const mapTf = useRosTf(ros, 'map', `${namespace}/base_link`, frame === 'map' || layers.map || layers.plan);
  const mapGrid = useRosTopic<OccupancyGrid>(ros, `/${namespace}/navigation/map`, 'nav_msgs/OccupancyGrid', layers.map);
  const costmapGrid = useRosTopic<OccupancyGrid>(ros, `/${namespace}/navigation/global_costmap/costmap`, 'nav_msgs/OccupancyGrid', layers.costmap);
  const localCostmapGrid = useRosTopic<OccupancyGrid>(ros, `/${namespace}/navigation/local_costmap/costmap`, 'nav_msgs/OccupancyGrid', layers.costmap);
  const globalPlan = useRosTopic<Path>(ros, `/${namespace}/navigation/plan`, 'nav_msgs/Path', layers.plan);
  const localPlan = useRosTopic<Path>(ros, `/${namespace}/navigation/local_plan`, 'nav_msgs/Path', layers.plan);

  const centeredForMapRef = useRef(false);

  // mapフレームに切り替えたらmap(0,0)が画面中心になるようオフセットをリセット
  useEffect(() => {
    centeredForMapRef.current = false;
  }, [frame]);

  useEffect(() => {
    const BASE_RANGE = 3;
    const baseScale = Math.min(width, height) / 2 / BASE_RANGE;
    if (frame === 'map' && mapTf && !centeredForMapRef.current) {
      const ry = mapTf.translation.y, rx = mapTf.translation.x;
      setView(v => ({ ...v, offsetX: ry * baseScale * v.scale, offsetY: rx * baseScale * v.scale, rotation: 0 }));
      centeredForMapRef.current = true;
    }
    if (frame === 'odom' && odom && !centeredForMapRef.current) {
      const ry = odom.pose.pose.position.y, rx = odom.pose.pose.position.x;
      setView(v => ({ ...v, offsetX: ry * baseScale * v.scale, offsetY: rx * baseScale * v.scale, rotation: 0 }));
      centeredForMapRef.current = true;
    }
  }, [frame, mapTf, odom, width, height]);

  const mapImageRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (!mapGrid) { mapImageRef.current = null; return; }
    const { width: mw, height: mh } = mapGrid.info;
    const offscreen = document.createElement('canvas');
    offscreen.width = mw;
    offscreen.height = mh;
    const ctx2 = offscreen.getContext('2d');
    if (!ctx2) return;
    const imageData = ctx2.createImageData(mw, mh);
    for (let i = 0; i < mapGrid.data.length; i++) {
      const val = mapGrid.data[i];
      const row = Math.floor(i / mw);
      const col = i % mw;
      const flippedRow = mh - 1 - row;
      const idx = (flippedRow * mw + col) * 4;
      if (val === -1) {
        imageData.data[idx] = 100; imageData.data[idx+1] = 105; imageData.data[idx+2] = 115; imageData.data[idx+3] = 160;
      } else if (val === 0) {
        imageData.data[idx] = 195; imageData.data[idx+1] = 205; imageData.data[idx+2] = 215; imageData.data[idx+3] = 200;
      } else {
        imageData.data[idx] = 25; imageData.data[idx+1] = 30; imageData.data[idx+2] = 45; imageData.data[idx+3] = 235;
      }
    }
    ctx2.putImageData(imageData, 0, 0);
    mapImageRef.current = offscreen;
  }, [mapGrid]);

  const costmapImageRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (!costmapGrid) { costmapImageRef.current = null; return; }
    const { width: mw, height: mh } = costmapGrid.info;
    const offscreen = document.createElement('canvas');
    offscreen.width = mw;
    offscreen.height = mh;
    const ctx2 = offscreen.getContext('2d');
    if (!ctx2) return;
    const imageData = ctx2.createImageData(mw, mh);
    for (let i = 0; i < costmapGrid.data.length; i++) {
      const val = costmapGrid.data[i];
      const row = Math.floor(i / mw);
      const col = i % mw;
      const flippedRow = mh - 1 - row;
      const idx = (flippedRow * mw + col) * 4;
      if (val <= 0) {
        imageData.data[idx+3] = 0; // 空き→透明
      } else if (val === 100) {
        imageData.data[idx] = 255; imageData.data[idx+1] = 80; imageData.data[idx+2] = 160; imageData.data[idx+3] = 120; // 障害物→ピンク
      } else if (val === -1) {
        imageData.data[idx+3] = 0; // 不明→透明
      } else {
        // コスト1-99: 薄いピンク
        const t = val / 99;
        imageData.data[idx]   = 255;
        imageData.data[idx+1] = 80;
        imageData.data[idx+2] = 160;
        imageData.data[idx+3] = Math.round(10 + t * 40);
      }
    }
    ctx2.putImageData(imageData, 0, 0);
    costmapImageRef.current = offscreen;
  }, [costmapGrid]);

  const localCostmapImageRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (!localCostmapGrid) { localCostmapImageRef.current = null; return; }
    const { width: mw, height: mh } = localCostmapGrid.info;
    const offscreen = document.createElement('canvas');
    offscreen.width = mw; offscreen.height = mh;
    const ctx2 = offscreen.getContext('2d');
    if (!ctx2) return;
    const imageData = ctx2.createImageData(mw, mh);
    for (let i = 0; i < localCostmapGrid.data.length; i++) {
      const val = localCostmapGrid.data[i];
      const row = Math.floor(i / mw);
      const col = i % mw;
      const flippedRow = mh - 1 - row;
      const idx = (flippedRow * mw + col) * 4;
      if (val <= 0 || val === -1) {
        imageData.data[idx+3] = 0;
      } else if (val === 100) {
        imageData.data[idx] = 255; imageData.data[idx+1] = 160; imageData.data[idx+2] = 0; imageData.data[idx+3] = 140; // 障害物→オレンジ
      } else {
        const t = val / 99;
        imageData.data[idx] = 255; imageData.data[idx+1] = 160; imageData.data[idx+2] = 0;
        imageData.data[idx+3] = Math.round(15 + t * 50);
      }
    }
    ctx2.putImageData(imageData, 0, 0);
    localCostmapImageRef.current = offscreen;
  }, [localCostmapGrid]);

  const lastTouchRef = useRef<{ dist: number; angle: number } | null>(null);
  const dragRef = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { scale, rotation, offsetX, offsetY } = view;
    const cx = width / 2 + offsetX;
    const cy = height / 2 + offsetY;
    const BASE_RANGE = 3; // デフォルトで6m全体（±3m）が見える
    const baseScale = Math.min(width, height) / 2 / BASE_RANGE;
    const s = baseScale * scale;

    ctx.fillStyle = '#1a1a2e';
    ctx.fillRect(0, 0, width, height);

    // map/odomフレーム: 原点固定・ロボット移動。base_link: ロボット固定
    const inMapFrame = frame === 'map';
    const inOdomFrame = frame === 'odom';
    const robot_map_x = mapTf?.translation.x ?? 0;
    const robot_map_y = mapTf?.translation.y ?? 0;
    const robot_odom_x = odom?.pose.pose.position.x ?? 0;
    const robot_odom_y = odom?.pose.pose.position.y ?? 0;
    const robotCanvasX = inMapFrame ? -robot_map_y * s : inOdomFrame ? -robot_odom_y * s : 0;
    const robotCanvasY = inMapFrame ? -robot_map_x * s : inOdomFrame ? -robot_odom_x * s : 0;

    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(rotation);

    // 1mグリッド
    const gridRange = Math.ceil(Math.max(width, height) / s) + 1;
    ctx.strokeStyle = 'rgba(255,255,255,0.08)';
    ctx.lineWidth = 1;
    for (let i = -gridRange; i <= gridRange; i++) {
      const p = i * s;
      ctx.beginPath(); ctx.moveTo(p, -gridRange * s); ctx.lineTo(p, gridRange * s); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(-gridRange * s, p); ctx.lineTo(gridRange * s, p); ctx.stroke();
    }
    ctx.strokeStyle = 'rgba(255,255,255,0.2)';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, -gridRange * s); ctx.lineTo(0, gridRange * s); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(-gridRange * s, 0); ctx.lineTo(gridRange * s, 0); ctx.stroke();

    // OccupancyGrid マップ描画
    if (mapImageRef.current && mapGrid && layers.map) {
      const mapImg = mapImageRef.current;
      const { resolution: res, width: mw, height: mh, origin } = mapGrid.info;
      const ox = origin.position.x;
      const oy = origin.position.y;
      // mapフレーム: 原点=map(0,0) → オフセット不要
      // odomフレーム: 原点=odom(0,0) → map原点のodom座標でオフセット
      // base_link: 原点=ロボット → ロボットのmap座標でオフセット
      const ref_rx = inMapFrame ? 0 : inOdomFrame ? (robot_map_x - robot_odom_x) : robot_map_x;
      const ref_ry = inMapFrame ? 0 : inOdomFrame ? (robot_map_y - robot_odom_y) : robot_map_y;
      const pxPerM = res * s;
      const mapX0 = -(oy + (mh - 1) * res - ref_ry) * s;
      const mapY0 = -(ox - ref_rx) * s;
      ctx.save();
      ctx.transform(0, -pxPerM, pxPerM, 0, mapX0, mapY0);
      ctx.drawImage(mapImg, 0, 0);
      ctx.restore();
    }

    // グローバルコストマップ描画 (mapフレーム基準)
    if (costmapImageRef.current && costmapGrid && layers.costmap) {
      const cmImg = costmapImageRef.current;
      const { resolution: res, width: mw, height: mh, origin } = costmapGrid.info;
      const ox = origin.position.x;
      const oy = origin.position.y;
      // グローバルコストマップはmap座標系: mapフレームと同じオフセット
      const ref_rx = inMapFrame ? 0 : inOdomFrame ? (robot_map_x - robot_odom_x) : robot_map_x;
      const ref_ry = inMapFrame ? 0 : inOdomFrame ? (robot_map_y - robot_odom_y) : robot_map_y;
      const pxPerM = res * s;
      const mapX0 = -(oy + (mh - 1) * res - ref_ry) * s;
      const mapY0 = -(ox - ref_rx) * s;
      ctx.save();
      ctx.transform(0, -pxPerM, pxPerM, 0, mapX0, mapY0);
      ctx.drawImage(cmImg, 0, 0);
      ctx.restore();
    }

    // ローカルコストマップ描画 (odomフレーム基準)
    if (localCostmapImageRef.current && localCostmapGrid && layers.costmap) {
      const cmImg = localCostmapImageRef.current;
      const { resolution: res, width: mw, height: mh, origin } = localCostmapGrid.info;
      const ox = origin.position.x;
      const oy = origin.position.y;
      const local_ref_rx = inMapFrame ? (robot_odom_x - robot_map_x) : inOdomFrame ? 0 : robot_odom_x;
      const local_ref_ry = inMapFrame ? (robot_odom_y - robot_map_y) : inOdomFrame ? 0 : robot_odom_y;
      const pxPerM = res * s;
      const mapX0 = -(oy + (mh - 1) * res - local_ref_ry) * s;
      const mapY0 = -(ox - local_ref_rx) * s;
      ctx.save();
      ctx.transform(0, -pxPerM, pxPerM, 0, mapX0, mapY0);
      ctx.drawImage(cmImg, 0, 0);
      ctx.restore();
    }

    const robotOrientation =
      frame === 'odom' ? odom?.pose.pose.orientation :
      frame === 'map'  ? mapTf?.rotation :
      null;
    const robotYaw = robotOrientation ? quatToYaw(robotOrientation.z, robotOrientation.w) : 0;
    const cos_yaw = Math.cos(robotYaw);
    const sin_yaw = Math.sin(robotYaw);

    // LiDAR点群
    if (scan && layers.lidar) {
      ctx.fillStyle = '#00ff88';
      scan.ranges.forEach((r, i) => {
        if (r === 0 || r > scan.range_max) return;
        const scanAngle = scan.angle_min + i * scan.angle_increment;
        let px: number, py: number;
        if (frame === 'base_link') {
          const angle = scanAngle + SCAN_ANGLE_OFFSET;
          px = r * Math.cos(angle) * s;
          py = -r * Math.sin(angle) * s;
        } else {
          const pr_x = r * Math.cos(scanAngle);
          const pr_y = r * Math.sin(scanAngle);
          const pw_x = pr_x * cos_yaw - pr_y * sin_yaw;
          const pw_y = pr_x * sin_yaw + pr_y * cos_yaw;
          const world_x = pw_x + (inMapFrame ? robot_map_x : inOdomFrame ? robot_odom_x : 0);
          const world_y = pw_y + (inMapFrame ? robot_map_y : inOdomFrame ? robot_odom_y : 0);
          px = -world_y * s;
          py = -world_x * s;
        }
        ctx.beginPath(); ctx.arc(px, py, 2, 0, Math.PI * 2); ctx.fill();
      });
    }

    // 人（PEOPLE markers）- base_link基準なのでロボット位置にオフセット
    if (markers && layers.people) {
      const iconSize = 28;
      markers.markers.filter((m) => m.ns === 'PEOPLE').forEach((m) => {
        const x = -m.pose.position.y * s + robotCanvasX;
        const y = -m.pose.position.x * s + robotCanvasY;
        ctx.beginPath(); ctx.arc(x, y, 14, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255,100,100,0.25)';
        ctx.fill();
        if (boyIconImg.complete) {
          ctx.drawImage(boyIconImg, x - iconSize / 2, y - iconSize / 2, iconSize, iconSize);
        } else {
          ctx.fillStyle = '#ff4444'; ctx.font = '12px sans-serif'; ctx.textAlign = 'center';
          ctx.fillText('人', x, y + 4);
        }
      });
    }

    // DOA方向 - ロボット位置から描画
    if (doa && layers.doa) {
      const yaw = quatToYaw(doa.pose.orientation.z, doa.pose.orientation.w) + SCAN_ANGLE_OFFSET;
      const len = s;
      const dx = Math.cos(yaw) * len;
      const dy = -Math.sin(yaw) * len;
      ctx.strokeStyle = '#ffcc00'; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(robotCanvasX, robotCanvasY); ctx.lineTo(robotCanvasX + dx, robotCanvasY + dy); ctx.stroke();
      const headAngle = Math.atan2(dy, dx);
      const hs = 10;
      ctx.beginPath();
      ctx.moveTo(robotCanvasX + dx, robotCanvasY + dy);
      ctx.lineTo(robotCanvasX + dx - Math.cos(headAngle - 0.4) * hs, robotCanvasY + dy - Math.sin(headAngle - 0.4) * hs);
      ctx.lineTo(robotCanvasX + dx - Math.cos(headAngle + 0.4) * hs, robotCanvasY + dy - Math.sin(headAngle + 0.4) * hs);
      ctx.closePath();
      ctx.fillStyle = '#ffcc00'; ctx.fill();
    }

    // ゴールドラフト（ドラッグ中）
    const drawGoalArrow = (gx: number, gy: number, yaw: number, alpha: number) => {
      const arrowLen = 30;
      const adx = -Math.sin(yaw) * arrowLen;
      const ady = -Math.cos(yaw) * arrowLen;
      ctx.globalAlpha = alpha;
      ctx.strokeStyle = '#00ccff'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(gx, gy, 14, 0, Math.PI * 2); ctx.stroke();
      ctx.fillStyle = 'rgba(0,204,255,0.2)'; ctx.fill();
      ctx.strokeStyle = '#00ccff'; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(gx, gy); ctx.lineTo(gx + adx, gy + ady); ctx.stroke();
      const headAngle = Math.atan2(ady, adx);
      const hs = 8;
      ctx.beginPath();
      ctx.moveTo(gx + adx, gy + ady);
      ctx.lineTo(gx + adx - Math.cos(headAngle - 0.5) * hs, gy + ady - Math.sin(headAngle - 0.5) * hs);
      ctx.lineTo(gx + adx - Math.cos(headAngle + 0.5) * hs, gy + ady - Math.sin(headAngle + 0.5) * hs);
      ctx.closePath();
      ctx.fillStyle = '#00ccff'; ctx.fill();
      ctx.globalAlpha = 1;
    };

    if (goalDraft) {
      const gx = -goalDraft.y * s;
      const gy = -goalDraft.x * s;
      drawGoalArrow(gx, gy, goalDraft.yaw, 0.7);
    }

    // initialposeドラフト（黄緑）
    if (poseDraft) {
      const gx = -poseDraft.y * s;
      const gy = -poseDraft.x * s;
      const arrowLen = 30;
      const adx = -Math.sin(poseDraft.yaw) * arrowLen;
      const ady = -Math.cos(poseDraft.yaw) * arrowLen;
      ctx.globalAlpha = 0.8;
      ctx.strokeStyle = '#aaff44'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(gx, gy, 14, 0, Math.PI * 2); ctx.stroke();
      ctx.fillStyle = 'rgba(170,255,68,0.2)'; ctx.fill();
      ctx.strokeStyle = '#aaff44'; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(gx, gy); ctx.lineTo(gx + adx, gy + ady); ctx.stroke();
      const ha = Math.atan2(ady, adx);
      const hs = 8;
      ctx.beginPath();
      ctx.moveTo(gx + adx, gy + ady);
      ctx.lineTo(gx + adx - Math.cos(ha - 0.5) * hs, gy + ady - Math.sin(ha - 0.5) * hs);
      ctx.lineTo(gx + adx - Math.cos(ha + 0.5) * hs, gy + ady - Math.sin(ha + 0.5) * hs);
      ctx.closePath();
      ctx.fillStyle = '#aaff44'; ctx.fill();
      ctx.globalAlpha = 1;
    }

    // ゴールマーカー（確定済み）
    if (goalPos) {
      const gx = -goalPos.y * s;
      const gy = -goalPos.x * s;
      drawGoalArrow(gx, gy, goalPos.yaw, 1.0);
      // ロボットからゴールへの点線
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = 'rgba(0,204,255,0.5)'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(robotCanvasX, robotCanvasY); ctx.lineTo(gx, gy); ctx.stroke();
      ctx.setLineDash([]);
    }

    // プラン描画ヘルパー (plan は常にmapフレーム座標)
    const drawPath = (path: Path, color: string, lineWidth: number) => {
      if (path.poses.length < 2) return;
      // plan は map 座標系
      // mapフレーム: 原点=map(0,0) → オフセット不要
      // odomフレーム: 原点=odom(0,0) → map→odom近似でオフセット
      // base_link: 原点=ロボット → ロボットmap座標でオフセット
      const ref_rx = inMapFrame ? 0 : inOdomFrame ? (robot_map_x - robot_odom_x) : robot_map_x;
      const ref_ry = inMapFrame ? 0 : inOdomFrame ? (robot_map_y - robot_odom_y) : robot_map_y;
      ctx.strokeStyle = color;
      ctx.lineWidth = lineWidth;
      ctx.lineJoin = 'round';
      ctx.beginPath();
      path.poses.forEach((p, i) => {
        const cx_ = -(p.pose.position.y - ref_ry) * s;
        const cy_ = -(p.pose.position.x - ref_rx) * s;
        if (i === 0) ctx.moveTo(cx_, cy_); else ctx.lineTo(cx_, cy_);
      });
      ctx.stroke();
    };

    if (layers.plan) {
      if (globalPlan) drawPath(globalPlan, 'rgba(80, 220, 80, 0.7)', 2);
      if (localPlan)  drawPath(localPlan,  'rgba(255, 200, 0, 0.9)', 3);
    }

    // rooms / places (map frame)
    const ref_rx = inMapFrame ? 0 : inOdomFrame ? (robot_map_x - robot_odom_x) : robot_map_x;
    const ref_ry = inMapFrame ? 0 : inOdomFrame ? (robot_map_y - robot_odom_y) : robot_map_y;

    if (rooms && rooms.length > 0) {
      rooms.forEach((room, idx) => {
        if (!room.points || room.points.length < 3) return;
        const color = ROOM_COLORS[idx % ROOM_COLORS.length];
        const pts = room.points.map(([wx, wy]: [number, number]) => ({
          px: -(wy - ref_ry) * s,
          py: -(wx - ref_rx) * s,
        }));
        ctx.save();
        ctx.beginPath();
        pts.forEach(({ px: ppx, py: ppy }, i) => i === 0 ? ctx.moveTo(ppx, ppy) : ctx.lineTo(ppx, ppy));
        ctx.closePath();
        ctx.globalAlpha = 0.18; ctx.fillStyle = color; ctx.fill();
        ctx.globalAlpha = 1; ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.stroke();
        ctx.restore();
        ctx.save();
        ctx.translate(pts[0].px, pts[0].py);
        ctx.rotate(-rotation);
        ctx.fillStyle = color; ctx.font = '11px sans-serif'; ctx.textAlign = 'left';
        ctx.fillText(room.name, 3, 12);
        ctx.restore();
      });
    }

    if (places && places.length > 0) {
      places.forEach(place => {
        const ppx = -(place.y - ref_ry) * s;
        const ppy = -(place.x - ref_rx) * s;
        const color = CAT_COLORS[place.category] || '#ffffff';
        ctx.save();
        ctx.fillStyle = color;
        ctx.beginPath(); ctx.arc(ppx, ppy, 5, 0, Math.PI * 2); ctx.fill();
        const adx = -Math.sin(place.yaw) * 12;
        const ady = -Math.cos(place.yaw) * 12;
        ctx.strokeStyle = color; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.moveTo(ppx, ppy); ctx.lineTo(ppx + adx, ppy + ady); ctx.stroke();
        ctx.restore();
        ctx.save();
        ctx.translate(ppx, ppy);
        ctx.rotate(-rotation);
        ctx.fillStyle = color; ctx.font = '11px sans-serif'; ctx.textAlign = 'left';
        ctx.fillText(place.name, 7, 4);
        ctx.restore();
      });
    }

    // ロボット（mapフレームではTF位置に、それ以外は原点に描画）
    ctx.strokeStyle = '#ff6600'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(robotCanvasX, robotCanvasY, 12, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = '#ff6600';
    ctx.beginPath(); ctx.arc(robotCanvasX, robotCanvasY, 6, 0, Math.PI * 2); ctx.fill();
    const fwdDx = frame !== 'base_link' ? -sin_yaw * 20 : 0;
    const fwdDy = frame !== 'base_link' ? -cos_yaw * 20 : -20;
    ctx.beginPath(); ctx.moveTo(robotCanvasX, robotCanvasY); ctx.lineTo(robotCanvasX + fwdDx, robotCanvasY + fwdDy); ctx.stroke();

    ctx.restore();
  }, [scan, markers, doa, odom, mapTf, mapGrid, costmapGrid, localCostmapGrid, globalPlan, localPlan, frame, layers, view, width, height, boyIconImg, iconReady, goalPos, goalDraft, poseDraft, places, rooms]);

  // canvas上のピクセル座標 → ROS座標変換
  const canvasToRos = (px: number, py: number, rect: DOMRect) => {
    const v = viewRef.current;
    const BASE_RANGE = 3;
    const baseScale = Math.min(width, height) / 2 / BASE_RANGE;
    const s = baseScale * v.scale;
    const cx = width / 2 + v.offsetX;
    const cy = height / 2 + v.offsetY;
    const dx = (px - rect.left) - cx;
    const dy = (py - rect.top) - cy;
    // 回転を逆に戻す
    const cos_r = Math.cos(-v.rotation);
    const sin_r = Math.sin(-v.rotation);
    const lx = dx * cos_r - dy * sin_r;
    const ly = dx * sin_r + dy * cos_r;
    return { rosX: -ly / s, rosY: -lx / s };
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const onTouchStart = (e: TouchEvent) => {
      if (modeRef.current === 'goal' || modeRef.current === 'initialpose') {
        e.preventDefault();
        if (e.touches.length === 1) {
          const rect = canvas.getBoundingClientRect();
          const { rosX, rosY } = canvasToRos(e.touches[0].clientX, e.touches[0].clientY, rect);
          if (modeRef.current === 'goal') {
            goalDraftRef.current = { x: rosX, y: rosY, yaw: 0 };
            setGoalDraft({ x: rosX, y: rosY, yaw: 0 });
          } else {
            poseDraftRef.current = { x: rosX, y: rosY, yaw: 0 };
            setPoseDraft({ x: rosX, y: rosY, yaw: 0 });
          }
        }
        return;
      }
      if (e.touches.length === 2) {
        lastTouchRef.current = {
          dist: Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY),
          angle: Math.atan2(e.touches[1].clientY - e.touches[0].clientY, e.touches[1].clientX - e.touches[0].clientX),
        };
      } else if (e.touches.length === 1) {
        dragRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      }
    };

    const onTouchMove = (e: TouchEvent) => {
      if (modeRef.current === 'goal' || modeRef.current === 'initialpose') {
        e.preventDefault();
        if (e.touches.length === 1) {
          const rect = canvas.getBoundingClientRect();
          const { rosX, rosY } = canvasToRos(e.touches[0].clientX, e.touches[0].clientY, rect);
          if (modeRef.current === 'goal' && goalDraftRef.current) {
            const draft = goalDraftRef.current;
            const ddx = rosX - draft.x; const ddy = rosY - draft.y;
            if (Math.hypot(ddx, ddy) > 0.05) {
              const yaw = Math.atan2(ddy, ddx);
              goalDraftRef.current = { ...draft, yaw };
              setGoalDraft({ ...draft, yaw });
            }
          } else if (modeRef.current === 'initialpose' && poseDraftRef.current) {
            const draft = poseDraftRef.current;
            const ddx = rosX - draft.x; const ddy = rosY - draft.y;
            if (Math.hypot(ddx, ddy) > 0.05) {
              const yaw = Math.atan2(ddy, ddx);
              poseDraftRef.current = { ...draft, yaw };
              setPoseDraft({ ...draft, yaw });
            }
          }
        }
        return;
      }
      e.preventDefault();
      if (e.touches.length === 2 && lastTouchRef.current) {
        const last = lastTouchRef.current;
        const newDist = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
        const newAngle = Math.atan2(e.touches[1].clientY - e.touches[0].clientY, e.touches[1].clientX - e.touches[0].clientX);
        setView((v) => ({
          ...v,
          scale: Math.max(0.2, Math.min(10, v.scale * newDist / last.dist)),
          rotation: v.rotation + newAngle - last.angle,
        }));
        lastTouchRef.current = { dist: newDist, angle: newAngle };
      } else if (e.touches.length === 1 && dragRef.current) {
        const drag = dragRef.current;
        const dx = e.touches[0].clientX - drag.x;
        const dy = e.touches[0].clientY - drag.y;
        setView((v) => ({ ...v, offsetX: v.offsetX + dx, offsetY: v.offsetY + dy }));
        dragRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      }
    };

    const onTouchEnd = () => {
      if (modeRef.current === 'goal' && goalDraftRef.current) {
        const d = goalDraftRef.current;
        setGoalPos(d);
        setGoalDraft(null);
        goalDraftRef.current = null;
        onGoal?.(d.x, d.y, d.yaw);
        return;
      }
      if (modeRef.current === 'initialpose' && poseDraftRef.current) {
        const d = poseDraftRef.current;
        setPoseDraft(null);
        poseDraftRef.current = null;
        onInitialPose?.(d.x, d.y, d.yaw);
        return;
      }
      lastTouchRef.current = null;
      dragRef.current = null;
    };

    const onWheel = (e: WheelEvent) => {
      if (modeRef.current === 'goal') return;
      e.preventDefault();
      setView((v) => ({ ...v, scale: Math.max(0.2, Math.min(10, v.scale * (e.deltaY > 0 ? 0.9 : 1.1))) }));
    };

    canvas.addEventListener('touchstart', onTouchStart, { passive: false });
    canvas.addEventListener('touchmove', onTouchMove, { passive: false });
    canvas.addEventListener('touchend', onTouchEnd);
    canvas.addEventListener('wheel', onWheel, { passive: false });

    return () => {
      canvas.removeEventListener('touchstart', onTouchStart);
      canvas.removeEventListener('touchmove', onTouchMove);
      canvas.removeEventListener('touchend', onTouchEnd);
      canvas.removeEventListener('wheel', onWheel);
    };
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const handleMouseDown = (e: React.MouseEvent) => {
    if (mode === 'goal' || mode === 'initialpose') {
      const rect = canvasRef.current!.getBoundingClientRect();
      const { rosX, rosY } = canvasToRos(e.clientX, e.clientY, rect);
      if (mode === 'goal') { goalDraftRef.current = { x: rosX, y: rosY, yaw: 0 }; setGoalDraft({ x: rosX, y: rosY, yaw: 0 }); }
      else { poseDraftRef.current = { x: rosX, y: rosY, yaw: 0 }; setPoseDraft({ x: rosX, y: rosY, yaw: 0 }); }
      return;
    }
    dragRef.current = { x: e.clientX, y: e.clientY };
  };
  const handleMouseMove = (e: React.MouseEvent) => {
    if (mode === 'goal' || mode === 'initialpose') {
      const draftRef = mode === 'goal' ? goalDraftRef : poseDraftRef;
      if (!draftRef.current) return;
      const rect = canvasRef.current!.getBoundingClientRect();
      const { rosX, rosY } = canvasToRos(e.clientX, e.clientY, rect);
      const draft = draftRef.current;
      const dx = rosX - draft.x; const dy = rosY - draft.y;
      if (Math.hypot(dx, dy) > 0.05) {
        const yaw = Math.atan2(dy, dx);
        draftRef.current = { ...draft, yaw };
        if (mode === 'goal') setGoalDraft({ ...draft, yaw });
        else setPoseDraft({ ...draft, yaw });
      }
      return;
    }
    const drag = dragRef.current;
    if (!drag) return;
    setView((v) => ({ ...v, offsetX: v.offsetX + e.clientX - drag.x, offsetY: v.offsetY + e.clientY - drag.y }));
    dragRef.current = { x: e.clientX, y: e.clientY };
  };
  const handleMouseUp = () => {
    if (mode === 'goal' && goalDraftRef.current) {
      const d = goalDraftRef.current;
      setGoalPos(d); setGoalDraft(null); goalDraftRef.current = null;
      onGoal?.(d.x, d.y, d.yaw);
      return;
    }
    if (mode === 'initialpose' && poseDraftRef.current) {
      const d = poseDraftRef.current;
      setPoseDraft(null); poseDraftRef.current = null;
      onInitialPose?.(d.x, d.y, d.yaw);
      return;
    }
    dragRef.current = null;
  };

  return (
    <div style={{ position: 'relative', width, height }}>
      <canvas
        ref={canvasRef} width={width} height={height}
        style={{ borderRadius: 8, cursor: (mode === 'goal' || mode === 'initialpose') ? 'crosshair' : 'grab', touchAction: 'none' }}
        onMouseDown={handleMouseDown} onMouseMove={handleMouseMove} onMouseUp={handleMouseUp} onMouseLeave={handleMouseUp}
      />
      <button
        onClick={() => setView({ scale: 1, rotation: 0, offsetX: 0, offsetY: 0 })}
        style={{
          position: 'absolute', bottom: 8, right: 8,
          padding: '4px 10px', borderRadius: 12, border: 'none',
          background: 'rgba(255,255,255,0.15)', color: '#fff', fontSize: 12, cursor: 'pointer',
        }}
      >
        リセット
      </button>
    </div>
  );
}
