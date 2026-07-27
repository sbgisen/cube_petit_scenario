import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from './Icon';

const ZOOM_MIN = 0.1;
const ZOOM_MAX = 10;
const ZOOM_BUTTON_FACTOR = 1.3;

// 「きれいな」目盛り(1,2,5 x 10^n [m])のうち、maxPx以下で最大のものを選ぶ
// (Googleマップ等の縮尺バーと同じ考え方)
function niceScaleBarMeters(targetMeters: number): number {
  if (!isFinite(targetMeters) || targetMeters <= 0) return 1;
  const exp = Math.floor(Math.log10(targetMeters));
  const base = Math.pow(10, exp);
  let best = base;
  for (const mult of [1, 2, 5, 10]) {
    const candidate = mult * base;
    if (candidate <= targetMeters) best = candidate;
  }
  return best;
}

interface Props {
  namespace: string;
  apiUrl: string;
}

interface MapPlace {
  name: string;
  category: string;
  pose: [number, number, number];
}

interface MapRoom {
  name: string;
  points: [number, number][]; // world coords polygon
}

interface MapMeta {
  resolution: number;
  origin: [number, number, number];
}

interface RobotPose { x: number; y: number; yaw: number; }

type Tool = 'pen' | 'rect' | 'eraser';
type EditorMode = 'edit' | 'place' | 'room' | 'rename';
type RoomSubMode = 'rect' | 'polygon';

const CATEGORIES = ['patrol', 'favorite', 'dock', 'initial_pose'];
const MAX_UNDO = 20;
const CAT_COLORS: Record<string, string> = { dock: '#ff6600', favorite: '#ffcc00', patrol: '#00aaff', initial_pose: '#00ff88' };
const ROOM_COLORS = ['#aa44ff', '#ff44aa', '#44ffaa', '#ffaa44', '#44aaff', '#ff4444'];

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ color: 'var(--t-text-muted)', fontSize: 13, fontWeight: 'bold', marginBottom: 8, flexShrink: 0 }}>
      {children}
    </div>
  );
}

function drawColoredText(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, size: number, color: string) {
  ctx.font = `bold ${size}px sans-serif`;
  ctx.fillStyle = color;
  ctx.fillText(text, x, y);
}

export function MapTab({ namespace, apiUrl }: Props) {
  const [maps, setMaps] = useState<string[]>([]);
  const [selectedMap, setSelectedMap] = useState('');
  const [meta, setMeta] = useState<MapMeta | null>(null);
  const [mapImg, setMapImg] = useState<HTMLImageElement | null>(null);
  const [keepoutImg, setKeeoutImg] = useState<HTMLImageElement | null>(null);
  const [editorMode, setEditorMode] = useState<EditorMode>('edit');
  const [tool, setTool] = useState<Tool>('pen');
  const [brushSize, setBrushSize] = useState(4);
  const [places, setPlaces] = useState<MapPlace[]>([]);
  const [rooms, setRooms] = useState<MapRoom[]>([]);
  const [robotPose, setRobotPose] = useState<RobotPose | null>(null);
  const [msg, setMsg] = useState('');

  // SLAM map save
  const [saveMapName, setSaveMapName] = useState('');
  const [saveDest, setSaveDest] = useState<'extra' | 'base'>('extra');
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);

  // rotation
  const [rotDeg, setRotDeg] = useState(0);
  const viewRot = rotDeg * Math.PI / 180;

  // place draft
  const [placeDraft, setPlaceDraft] = useState<{ x: number; y: number; yaw: number } | null>(null);
  const placeDraftRef = useRef<{ x: number; y: number; yaw: number } | null>(null);
  const placeDragging = useRef(false);
  const [placeName, setPlaceName] = useState('');
  const [placeCategory, setPlaceCategory] = useState('patrol');

  // rename editing
  const [editingItem, setEditingItem] = useState<{ type: 'place' | 'room'; name: string; value: string } | null>(null);

  // room draft
  const [roomSubMode, setRoomSubMode] = useState<RoomSubMode>('rect');
  const [roomDraft, setRoomDraft] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const roomDraftRef = useRef<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const roomDrawing = useRef(false);
  const [roomPolygon, setRoomPolygon] = useState<[number, number][]>([]);
  const roomPolygonRef = useRef<[number, number][]>([]);
  const [roomMouseWorld, setRoomMouseWorld] = useState<[number, number] | null>(null);
  const [roomName, setRoomName] = useState('');
  const [roomConfirming, setRoomConfirming] = useState(false);

  // canvas
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const keepoutCanvasRef = useRef<HTMLCanvasElement>(null);
  // 地図本体(occupancy grid)を直接編集するための編集用キャンバス。keepoutと同じ仕組みで
  // 小さいノイズ点(誤検出による孤立した黒点)を消しゴムで消せるようにする。
  // Editable canvas for the base occupancy grid map itself, mirroring the keepout canvas, so
  // small noise specks (isolated false-positive occupied pixels) can be erased directly.
  const mapCanvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const panStart = useRef<{ mx: number; my: number; px: number; py: number } | null>(null);
  const drawing = useRef(false);
  const rectStart = useRef<{ x: number; y: number } | null>(null);
  const keepoutDirty = useRef(false);
  const mapDirty = useRef(false);
  // 編集対象: keepoutマスク か 地図本体か
  const [editTarget, setEditTarget] = useState<'keepout' | 'map'>('keepout');
  const undoStack = useRef<ImageData[]>([]);
  const [canUndo, setCanUndo] = useState(false);
  // 編集対象を切り替えたらUndoスタックは持ち越さない(別キャンバスのスナップショットが
  // 混ざるのを防ぐ)。Reset the undo stack on target switch so snapshots from the other
  // canvas never get applied to the wrong one.
  useEffect(() => {
    undoStack.current = []; setCanUndo(false);
  }, [editTarget]);

  // map lock (iPad drawing)
  const [mapLocked, setMapLocked] = useState(false);
  const mapLockedRef = useRef(false);
  mapLockedRef.current = mapLocked;

  // touch
  const touchDist = useRef(0);
  const touchAngle = useRef(0);

  const showMsg = (m: string) => { setMsg(m); setTimeout(() => setMsg(''), 3000); };

  // ---- load map list ----
  useEffect(() => {
    fetch(`${apiUrl}/map/list`).then(r => r.json()).then(d => {
      const list: string[] = d.maps ?? [];
      setMaps(list);
      if (list.length) setSelectedMap(list[0]);
    }).catch(() => {});
  }, [apiUrl]);

  // ---- load map when selection changes ----
  useEffect(() => {
    if (!selectedMap) return;
    setMeta(null); setMapImg(null); setKeeoutImg(null); setRotDeg(0);
    setPlaces([]); setRooms([]);
    setPlaceDraft(null); setRoomDraft(null); setRoomConfirming(false); setEditingItem(null);
    fetch(`${apiUrl}/map/meta?map_name=${encodeURIComponent(selectedMap)}`)
      .then(r => r.json()).then(setMeta).catch(() => {});
    const load = (url: string, setter: (img: HTMLImageElement) => void) => {
      const img = new window.Image(); img.crossOrigin = 'anonymous';
      img.onload = () => setter(img); img.src = url;
    };
    load(`${apiUrl}/map/image?map_name=${encodeURIComponent(selectedMap)}&type=map&t=${Date.now()}`, setMapImg);
    load(`${apiUrl}/map/image?map_name=${encodeURIComponent(selectedMap)}&type=keepout&t=${Date.now()}`, setKeeoutImg);
  }, [selectedMap, apiUrl]);

  // ---- keepout canvas init ----
  useEffect(() => {
    if (!keepoutImg || !mapImg) return;
    const kc = keepoutCanvasRef.current; if (!kc) return;
    kc.width = keepoutImg.width; kc.height = keepoutImg.height;
    const ctx = kc.getContext('2d')!;
    ctx.drawImage(keepoutImg, 0, 0);
    try {
      const mt = document.createElement('canvas');
      mt.width = mapImg.width; mt.height = mapImg.height;
      const mc = mt.getContext('2d')!; mc.drawImage(mapImg, 0, 0);
      const mp = mc.getImageData(0, 0, mt.width, mt.height).data;
      const kd = ctx.getImageData(0, 0, kc.width, kc.height);
      const d = kd.data;
      for (let i = 0; i < d.length; i += 4)
        if (d[i] < 128 && mp[i] < 50) { d[i] = d[i+1] = d[i+2] = 255; d[i+3] = 255; }
      ctx.putImageData(kd, 0, 0);
    } catch { ctx.clearRect(0, 0, kc.width, kc.height); }
    undoStack.current = []; setCanUndo(false);
  }, [keepoutImg, mapImg]);

  // ---- 地図本体の編集用キャンバス初期化(mapImgをそのまま複製、mapImgの更新ごとに作り直す) ----
  useEffect(() => {
    if (!mapImg) return;
    const mc = mapCanvasRef.current; if (!mc) return;
    mc.width = mapImg.width; mc.height = mapImg.height;
    mc.getContext('2d')!.drawImage(mapImg, 0, 0);
    mapDirty.current = false;
  }, [mapImg]);

  // ---- fit canvas on load ----
  useEffect(() => {
    if (!mapImg || !containerRef.current) return;
    const c = containerRef.current;
    const s = Math.min(c.clientWidth / mapImg.width, c.clientHeight / mapImg.height, 1);
    setScale(s);
    setPan({ x: (c.clientWidth - mapImg.width * s) / 2, y: (c.clientHeight - mapImg.height * s) / 2 });
    undoStack.current = []; setCanUndo(false);
  }, [mapImg]);

  // ---- fetch map places ----
  const fetchPlaces = useCallback(() => {
    if (!selectedMap) return;
    fetch(`${apiUrl}/map/places?map_name=${encodeURIComponent(selectedMap)}`)
      .then(r => r.json()).then(d => setPlaces(d.places ?? [])).catch(() => {});
  }, [apiUrl, selectedMap]);
  useEffect(() => { fetchPlaces(); }, [fetchPlaces]);

  // ---- fetch map rooms ----
  const fetchRooms = useCallback(() => {
    if (!selectedMap) return;
    fetch(`${apiUrl}/map/rooms?map_name=${encodeURIComponent(selectedMap)}`)
      .then(r => r.json()).then(d => setRooms(d.rooms ?? [])).catch(() => {});
  }, [apiUrl, selectedMap]);
  useEffect(() => { fetchRooms(); }, [fetchRooms]);

  // ---- poll robot pose ----
  useEffect(() => {
    if (!mapImg) return;
    const poll = () =>
      fetch(`${apiUrl}/ros/robot_pose?namespace=${namespace}`)
        .then(r => r.json())
        .then(d => setRobotPose(d.ok ? d : null))
        .catch(() => setRobotPose(null));
    poll(); const t = setInterval(poll, 1000); return () => clearInterval(t);
  }, [apiUrl, namespace, mapImg]);

  // ---- canvas coordinate helpers ----
  const getPivot = useCallback((img: HTMLImageElement) => ({
    x: pan.x + img.width * scale / 2,
    y: pan.y + img.height * scale / 2,
  }), [pan, scale]);

  const imgCoords = useCallback((clientX: number, clientY: number) => {
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    const cx = clientX - rect.left, cy = clientY - rect.top;
    if (!mapImg) return { ix: 0, iy: 0, cx, cy };
    const piv = getPivot(mapImg);
    const dx = cx - piv.x, dy = cy - piv.y;
    const cos = Math.cos(-viewRot), sin = Math.sin(-viewRot);
    return {
      ix: (cos * dx - sin * dy) / scale + mapImg.width / 2,
      iy: (sin * dx + cos * dy) / scale + mapImg.height / 2,
      cx, cy,
    };
  }, [mapImg, scale, getPivot, viewRot]);

  const imgToWorld = useCallback((ix: number, iy: number) => {
    if (!meta || !mapImg) return { x: 0, y: 0 };
    return {
      x: Math.round((ix * meta.resolution + meta.origin[0]) * 1000) / 1000,
      y: Math.round(((mapImg.height - iy) * meta.resolution + meta.origin[1]) * 1000) / 1000,
    };
  }, [meta, mapImg]);

  // world coords → image pixel coords (for render)
  const worldToImg = useCallback((wx: number, wy: number) => {
    if (!meta || !mapImg) return { ix: 0, iy: 0 };
    return {
      ix: (wx - meta.origin[0]) / meta.resolution - mapImg.width / 2,
      iy: mapImg.height - (wy - meta.origin[1]) / meta.resolution - mapImg.height / 2,
    };
  }, [meta, mapImg]);

  // ---- Google Maps風のズーム(+/-)・現在地ボタン・縮尺バー ----
  const zoomBy = useCallback((factor: number) => {
    const cont = containerRef.current;
    if (!cont) return;
    const cx = cont.clientWidth / 2, cy = cont.clientHeight / 2;
    setScale(s => {
      const ns = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, s * factor));
      setPan(p => ({ x: cx - (cx - p.x) * (ns / s), y: cy - (cy - p.y) * (ns / s) }));
      return ns;
    });
  }, []);

  const recenterOnRobot = useCallback(() => {
    const cont = containerRef.current;
    if (!cont || !mapImg || !robotPose) return;
    const { ix, iy } = worldToImg(robotPose.x, robotPose.y);
    const cos = Math.cos(viewRot), sin = Math.sin(viewRot);
    const cw = cont.clientWidth / 2, ch = cont.clientHeight / 2;
    setPan({
      x: cw - mapImg.width * scale / 2 - scale * (cos * ix - sin * iy),
      y: ch - mapImg.height * scale / 2 - scale * (sin * ix + cos * iy),
    });
  }, [mapImg, robotPose, scale, viewRot, worldToImg]);

  // 1マス(map画像1px) = meta.resolution [m] なので、画面上の1mあたりpx数 = scale / resolution
  const scaleBar = useMemo(() => {
    if (!meta || !mapImg) return null;
    const pxPerMeter = scale / meta.resolution;
    const meters = niceScaleBarMeters(120 / pxPerMeter);
    return { meters, px: meters * pxPerMeter };
  }, [meta, mapImg, scale]);

  // ---- render ----
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    const kc = keepoutCanvasRef.current;
    const mc = mapCanvasRef.current;
    if (!canvas || !mapImg) return;
    const ctx = canvas.getContext('2d')!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const piv = getPivot(mapImg);
    ctx.save();
    ctx.translate(piv.x, piv.y);
    ctx.rotate(viewRot);
    ctx.scale(scale, scale);
    // 地図編集(消しゴム等)を反映するため、mapImgではなく編集用キャンバス(mc)から描く。
    // mcが未初期化の間だけmapImgへフォールバック。
    if (mc && mc.width > 0) ctx.drawImage(mc, -mapImg.width / 2, -mapImg.height / 2);
    else ctx.drawImage(mapImg, -mapImg.width / 2, -mapImg.height / 2);

    // keepout overlay
    if (kc && kc.width > 0) {
      const tmp = document.createElement('canvas');
      tmp.width = kc.width; tmp.height = kc.height;
      const tc = tmp.getContext('2d')!; tc.drawImage(kc, 0, 0);
      try {
        const id = tc.getImageData(0, 0, tmp.width, tmp.height); const d = id.data;
        for (let i = 0; i < d.length; i += 4)
          if (d[i] < 128) { d[i] = 200; d[i+1] = 0; d[i+2] = 0; d[i+3] = 180; } else d[i+3] = 0;
        tc.putImageData(id, 0, 0);
      } catch { /**/ }
      ctx.drawImage(tmp, -mapImg.width / 2, -mapImg.height / 2);
    }

    if (meta) {
      const textSize = 10 / scale;

      // rooms (saved)
      rooms.forEach((room, idx) => {
        const color = ROOM_COLORS[idx % ROOM_COLORS.length];
        if (!room.points || room.points.length < 3) return;
        const pts = room.points.map(([wx, wy]: [number, number]) => worldToImg(wx, wy));
        ctx.save();
        ctx.beginPath();
        pts.forEach(({ ix, iy }, i) => i === 0 ? ctx.moveTo(ix, iy) : ctx.lineTo(ix, iy));
        ctx.closePath();
        ctx.globalAlpha = 0.18; ctx.fillStyle = color; ctx.fill();
        ctx.globalAlpha = 1; ctx.strokeStyle = color; ctx.lineWidth = 2 / scale; ctx.stroke();
        ctx.restore();
        drawColoredText(ctx, room.name, pts[0].ix + 3 / scale, pts[0].iy + textSize + 2 / scale, textSize, color);
      });

      // room rect draft
      if (roomDraft) {
        const p1 = worldToImg(roomDraft.x1, roomDraft.y1);
        const p2 = worldToImg(roomDraft.x2, roomDraft.y2);
        const rx = Math.min(p1.ix, p2.ix), ry = Math.min(p1.iy, p2.iy);
        const rw = Math.abs(p2.ix - p1.ix), rh = Math.abs(p2.iy - p1.iy);
        ctx.save();
        ctx.globalAlpha = 0.2; ctx.fillStyle = '#ffaa00'; ctx.fillRect(rx, ry, rw, rh);
        ctx.globalAlpha = 1; ctx.strokeStyle = '#ffaa00'; ctx.lineWidth = 2 / scale;
        ctx.setLineDash([6 / scale, 3 / scale]); ctx.strokeRect(rx, ry, rw, rh);
        ctx.restore();
      }

      // room polygon draft
      if (roomPolygon.length > 0) {
        const pts = roomPolygon.map(([wx, wy]) => worldToImg(wx, wy));
        ctx.save();
        ctx.beginPath();
        pts.forEach(({ ix, iy }, i) => i === 0 ? ctx.moveTo(ix, iy) : ctx.lineTo(ix, iy));
        if (roomMouseWorld) {
          const mp = worldToImg(roomMouseWorld[0], roomMouseWorld[1]);
          ctx.lineTo(mp.ix, mp.iy);
        }
        ctx.globalAlpha = 0.15; ctx.fillStyle = '#ffaa00'; ctx.fill();
        ctx.globalAlpha = 1; ctx.strokeStyle = '#ffaa00'; ctx.lineWidth = 2 / scale;
        ctx.setLineDash([6 / scale, 3 / scale]); ctx.stroke();
        ctx.restore();
        // vertices
        pts.forEach(({ ix, iy }, i) => {
          ctx.beginPath(); ctx.arc(ix, iy, 4 / scale, 0, Math.PI * 2);
          ctx.fillStyle = i === 0 ? '#ff6600' : '#ffaa00'; ctx.globalAlpha = 1; ctx.fill();
        });
      }

      // places
      for (const p of places) {
        const { ix, iy } = worldToImg(p.pose[0], p.pose[1]);
        const color = CAT_COLORS[p.category] ?? '#aaa';
        const arrowLen = 14 / scale;
        const pyaw = -p.pose[2];
        ctx.beginPath(); ctx.moveTo(ix, iy);
        ctx.lineTo(ix + Math.cos(pyaw) * arrowLen, iy + Math.sin(pyaw) * arrowLen);
        ctx.strokeStyle = color; ctx.lineWidth = 2 / scale; ctx.stroke();
        ctx.beginPath(); ctx.arc(ix, iy, 5 / scale, 0, Math.PI * 2);
        ctx.fillStyle = color; ctx.fill();
        drawColoredText(ctx, p.name, ix + 7 / scale, iy + 4 / scale, textSize, color);
      }

      // place draft arrow
      if (placeDraft) {
        const { ix, iy } = worldToImg(placeDraft.x, placeDraft.y);
        const arrowLen = 20 / scale, pyaw = -placeDraft.yaw;
        ctx.beginPath(); ctx.moveTo(ix, iy);
        ctx.lineTo(ix + Math.cos(pyaw) * arrowLen, iy + Math.sin(pyaw) * arrowLen);
        ctx.strokeStyle = '#ff6600'; ctx.lineWidth = 3 / scale; ctx.stroke();
        const ax = ix + Math.cos(pyaw) * arrowLen, ay = iy + Math.sin(pyaw) * arrowLen;
        ctx.beginPath(); ctx.moveTo(ax, ay);
        ctx.lineTo(ax + Math.cos(pyaw + 2.6) * 8 / scale, ay + Math.sin(pyaw + 2.6) * 8 / scale);
        ctx.lineTo(ax + Math.cos(pyaw - 2.6) * 8 / scale, ay + Math.sin(pyaw - 2.6) * 8 / scale);
        ctx.closePath(); ctx.fillStyle = '#ff6600'; ctx.fill();
        ctx.beginPath(); ctx.arc(ix, iy, 7 / scale, 0, Math.PI * 2);
        ctx.strokeStyle = '#ff6600'; ctx.lineWidth = 2 / scale; ctx.stroke();
      }

    }

    // robot pose
    if (robotPose && meta) {
      const { ix, iy } = worldToImg(robotPose.x, robotPose.y);
      const arrowLen = 18 / scale, r = 7 / scale;
      const imgYaw = -robotPose.yaw;
      ctx.beginPath(); ctx.arc(ix, iy, r, 0, Math.PI * 2);
      ctx.fillStyle = '#00ff88'; ctx.fill();
      ctx.strokeStyle = '#006633'; ctx.lineWidth = 2 / scale; ctx.stroke();
      ctx.beginPath(); ctx.moveTo(ix, iy);
      ctx.lineTo(ix + Math.cos(imgYaw) * arrowLen, iy + Math.sin(imgYaw) * arrowLen);
      ctx.strokeStyle = '#00ff88'; ctx.lineWidth = 3 / scale; ctx.stroke();
    }

    ctx.restore();
  }, [mapImg, scale, pan, viewRot, places, placeDraft, roomDraft, roomPolygon, roomMouseWorld, rooms, meta, robotPose, getPivot, worldToImg]);

  useEffect(() => { render(); }, [render]);

  useEffect(() => {
    const obs = new ResizeObserver(() => {
      const canvas = canvasRef.current, cont = containerRef.current;
      if (!canvas || !cont) return;
      canvas.width = cont.clientWidth; canvas.height = cont.clientHeight; render();
    });
    if (containerRef.current) obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, [render]);

  // ---- keepout drawing helpers ----
  // 編集対象(keepoutマスク/地図本体)に応じたキャンバスを返す
  const editCanvasRef = () => editTarget === 'map' ? mapCanvasRef : keepoutCanvasRef;

  const getKcCtx = () => {
    const kc = editCanvasRef().current;
    if (!kc || !mapImg) return null;
    if (kc.width === 0) { kc.width = mapImg.width; kc.height = mapImg.height; }
    return kc.getContext('2d')!;
  };

  const saveUndo = () => {
    const kc = editCanvasRef().current; if (!kc || kc.width === 0) return;
    try {
      const snap = kc.getContext('2d')!.getImageData(0, 0, kc.width, kc.height);
      undoStack.current.push(snap);
      if (undoStack.current.length > MAX_UNDO) undoStack.current.shift();
      setCanUndo(true);
    } catch { /**/ }
  };

  const undo = () => {
    const kc = editCanvasRef().current; if (!kc || !undoStack.current.length) return;
    kc.getContext('2d')!.putImageData(undoStack.current.pop()!, 0, 0);
    setCanUndo(undoStack.current.length > 0); render();
  };

  const drawAt = (ix: number, iy: number) => {
    const ctx = getKcCtx(); if (!ctx) return;
    if (editTarget === 'map') mapDirty.current = true; else keepoutDirty.current = true;
    ctx.fillStyle = tool === 'eraser' ? '#ffffff' : '#000000';
    ctx.beginPath(); ctx.arc(ix, iy, tool === 'eraser' ? brushSize * 2 : brushSize, 0, Math.PI * 2);
    ctx.fill(); render();
  };

  // ---- pointer event helpers ----
  const handlePointerDown = (clientX: number, clientY: number) => {
    if (!mapImg || !meta) return;
    const { ix, iy } = imgCoords(clientX, clientY);
    const w = imgToWorld(ix, iy);

    if (editorMode === 'place') {
      placeDraftRef.current = { x: w.x, y: w.y, yaw: 0 };
      placeDragging.current = true;
      setPlaceDraft({ x: w.x, y: w.y, yaw: 0 });
      return;
    }
    if (editorMode === 'room') {
      if (roomSubMode === 'rect') {
        roomDraftRef.current = { x1: w.x, y1: w.y, x2: w.x, y2: w.y };
        roomDrawing.current = true;
        setRoomDraft({ x1: w.x, y1: w.y, x2: w.x, y2: w.y });
      } else {
        // polygon: check if clicking near first point to close
        const prev = roomPolygonRef.current;
        if (prev.length >= 3) {
          const fp = worldToImg(prev[0][0], prev[0][1]);
          const cp = worldToImg(w.x, w.y);
          const dist = Math.hypot(fp.ix - cp.ix, fp.iy - cp.iy);
          if (dist < 12 / scale) {
            setRoomConfirming(true); return;
          }
        }
        const next: [number, number][] = [...prev, [w.x, w.y]];
        roomPolygonRef.current = next;
        setRoomPolygon(next);
      }
      return;
    }
    saveUndo(); drawing.current = true;
    if (tool === 'rect') rectStart.current = { x: ix, y: iy };
    else drawAt(ix, iy);
  };

  const handlePointerMove = (clientX: number, clientY: number) => {
    if (!mapImg || !meta) return;
    const { ix, iy } = imgCoords(clientX, clientY);
    const w = imgToWorld(ix, iy);

    if (editorMode === 'place' && placeDragging.current && placeDraftRef.current) {
      const draft = placeDraftRef.current;
      const yaw = Math.atan2(w.y - draft.y, w.x - draft.x);
      placeDraftRef.current = { ...draft, yaw };
      setPlaceDraft({ ...draft, yaw }); return;
    }
    if (editorMode === 'room') {
      if (roomSubMode === 'rect' && roomDrawing.current && roomDraftRef.current) {
        const d = { ...roomDraftRef.current, x2: w.x, y2: w.y };
        roomDraftRef.current = d; setRoomDraft(d);
      } else if (roomSubMode === 'polygon') {
        setRoomMouseWorld([w.x, w.y]);
      }
      return;
    }
    if (!drawing.current) return;
    if (tool !== 'rect') drawAt(ix, iy);
  };

  const handlePointerUp = (clientX: number, clientY: number) => {
    if (editorMode === 'place') { placeDragging.current = false; return; }
    if (editorMode === 'room' && roomSubMode === 'rect' && roomDrawing.current) {
      roomDrawing.current = false;
      if (roomDraftRef.current) {
        const d = roomDraftRef.current;
        const area = Math.abs(d.x2 - d.x1) * Math.abs(d.y2 - d.y1);
        if (area > 0.01) setRoomConfirming(true);
        else { setRoomDraft(null); roomDraftRef.current = null; }
      }
      return;
    }
    if (!drawing.current) return;
    drawing.current = false;
    if (tool === 'rect' && rectStart.current) {
      const { ix, iy } = imgCoords(clientX, clientY);
      const ctx = getKcCtx();
      if (ctx) {
        if (editTarget === 'map') mapDirty.current = true; else keepoutDirty.current = true;
        ctx.fillStyle = '#000000';
        ctx.fillRect(Math.min(rectStart.current.x, ix), Math.min(rectStart.current.y, iy),
          Math.abs(ix - rectStart.current.x), Math.abs(iy - rectStart.current.y));
        render();
      }
      rectStart.current = null;
    }
  };

  // ---- mouse events ----
  const onMouseDown = (e: React.MouseEvent) => {
    if (e.button === 1 || (e.button === 0 && e.altKey)) {
      panStart.current = { mx: e.clientX, my: e.clientY, px: pan.x, py: pan.y }; return;
    }
    if (e.button !== 0) return;
    handlePointerDown(e.clientX, e.clientY);
  };

  const onMouseMove = (e: React.MouseEvent) => {
    if (panStart.current) {
      setPan({ x: panStart.current.px + e.clientX - panStart.current.mx, y: panStart.current.py + e.clientY - panStart.current.my }); return;
    }
    handlePointerMove(e.clientX, e.clientY);
  };

  const onMouseUp = (e: React.MouseEvent) => {
    if (panStart.current) { panStart.current = null; return; }
    handlePointerUp(e.clientX, e.clientY);
  };

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    if (mapLockedRef.current) return;
    const f = e.deltaY < 0 ? 1.1 : 0.9;
    const rect = canvasRef.current!.getBoundingClientRect();
    const cx = e.clientX - rect.left, cy = e.clientY - rect.top;
    setScale(s => { const ns = Math.max(0.1, Math.min(10, s * f)); setPan(p => ({ x: cx - (cx - p.x) * (ns / s), y: cy - (cy - p.y) * (ns / s) })); return ns; });
  };

  // ---- touch ----
  const onTouchStart = (e: React.TouchEvent) => {
    e.preventDefault();
    const ts = Array.from(e.touches);
    if (ts.length === 1) {
      if (mapLockedRef.current || editorMode === 'place' || editorMode === 'room') {
        handlePointerDown(ts[0].clientX, ts[0].clientY);
      } else {
        panStart.current = { mx: ts[0].clientX, my: ts[0].clientY, px: pan.x, py: pan.y };
      }
    } else if (ts.length === 2 && !mapLockedRef.current) {
      touchDist.current = Math.hypot(ts[0].clientX - ts[1].clientX, ts[0].clientY - ts[1].clientY);
      touchAngle.current = Math.atan2(ts[1].clientY - ts[0].clientY, ts[1].clientX - ts[0].clientX);
      panStart.current = null;
    }
  };

  const onTouchMove = (e: React.TouchEvent) => {
    e.preventDefault();
    const ts = Array.from(e.touches);
    if (ts.length === 1) {
      if (mapLockedRef.current || editorMode === 'place' || editorMode === 'room') {
        handlePointerMove(ts[0].clientX, ts[0].clientY);
      } else if (panStart.current) {
        setPan({ x: panStart.current.px + ts[0].clientX - panStart.current.mx, y: panStart.current.py + ts[0].clientY - panStart.current.my });
      }
    } else if (ts.length === 2 && !mapLockedRef.current) {
      const currDist = Math.hypot(ts[0].clientX - ts[1].clientX, ts[0].clientY - ts[1].clientY);
      const currAngle = Math.atan2(ts[1].clientY - ts[0].clientY, ts[1].clientX - ts[0].clientX);
      const f = currDist / touchDist.current;
      const dDeg = (currAngle - touchAngle.current) * 180 / Math.PI;
      const rect = canvasRef.current!.getBoundingClientRect();
      const mx = (ts[0].clientX + ts[1].clientX) / 2 - rect.left;
      const my = (ts[0].clientY + ts[1].clientY) / 2 - rect.top;
      setScale(s => { const ns = Math.max(0.1, Math.min(10, s * f)); setPan(p => ({ x: mx - (mx - p.x) * (ns / s), y: my - (my - p.y) * (ns / s) })); return ns; });
      setRotDeg(r => r + dDeg);
      touchDist.current = currDist; touchAngle.current = currAngle;
    }
  };

  const onTouchEnd = (e: React.TouchEvent) => {
    e.preventDefault();
    if (e.touches.length < 2) {
      panStart.current = null;
      if (mapLockedRef.current && e.touches.length === 0) {
        const t = e.changedTouches[0];
        handlePointerUp(t.clientX, t.clientY);
      }
      if (editorMode === 'place') placeDragging.current = false;
      if (editorMode === 'room' && roomSubMode === 'rect' && roomDrawing.current) {
        roomDrawing.current = false;
        if (roomDraftRef.current) {
          const d = roomDraftRef.current;
          if (Math.abs(d.x2 - d.x1) * Math.abs(d.y2 - d.y1) > 0.01) setRoomConfirming(true);
          else { setRoomDraft(null); roomDraftRef.current = null; }
        }
      }
    }
  };

  // ---- actions ----
  const saveKeeout = () => {
    const kc = keepoutCanvasRef.current;
    if (!kc || !selectedMap) { showMsg('既存マップを選択してください'); return; }
    kc.toBlob(async blob => {
      if (!blob) return;
      const ab = await blob.arrayBuffer();
      const b64 = btoa(String.fromCharCode(...new Uint8Array(ab)));
      const r = await fetch(`${apiUrl}/map/keepout/save`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ map_name: selectedMap, png_base64: b64 }),
      });
      const d = await r.json();
      showMsg(d.ok ? 'keepout保存完了' : '保存失敗'); keepoutDirty.current = false;
    }, 'image/png');
  };

  // 地図本体(occupancy grid)への上書き保存。実際のナビゲーションに使われるファイルを
  // 直接書き換えるため、keepout保存より影響が大きい。誤操作防止にconfirmを挟む
  // (バックエンド側でも上書き前に.bakを残す)。
  const saveMapImage = () => {
    const mc = mapCanvasRef.current;
    if (!mc || !selectedMap) { showMsg('既存マップを選択してください'); return; }
    if (!confirm('地図本体を上書き保存します。ナビゲーションで実際に使われる地図が変わります。よろしいですか？')) return;
    mc.toBlob(async blob => {
      if (!blob) return;
      const ab = await blob.arrayBuffer();
      const b64 = btoa(String.fromCharCode(...new Uint8Array(ab)));
      const r = await fetch(`${apiUrl}/map/base/save`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ map_name: selectedMap, png_base64: b64 }),
      });
      const d = await r.json();
      showMsg(d.ok ? '地図保存完了' : '保存失敗'); mapDirty.current = false;
    }, 'image/png');
  };

  const previewLiveMap = async () => {
    setPreviewing(true);
    try {
      const r = await fetch(`${apiUrl}/map/preview`);
      if (!r.ok) { showMsg('SLAMマップ取得失敗'); return; }
      const d = await r.json();
      if (d.meta) setMeta(d.meta);
      const img = new window.Image(); img.crossOrigin = 'anonymous';
      img.onload = () => {
        setKeeoutImg(null); setMapImg(img);
        const kc = keepoutCanvasRef.current;
        if (kc) { kc.width = img.width; kc.height = img.height; kc.getContext('2d')!.clearRect(0, 0, kc.width, kc.height); }
        setRotDeg(0); setPlaceDraft(null); undoStack.current = []; setCanUndo(false);
        showMsg('SLAMマップを取得しました');
      };
      img.src = `data:image/png;base64,${d.png_base64}`;
      setSelectedMap('');
    } finally { setPreviewing(false); }
  };

  const saveCurrentMap = async () => {
    if (!saveMapName.trim()) { showMsg('名前を入力してください'); return; }
    setSaving(true);
    const r = await fetch(`${apiUrl}/map/save`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ map_name: saveMapName.trim(), dest: saveDest }),
    });
    const d = await r.json(); setSaving(false);
    if (d.ok) {
      showMsg('保存完了');
      fetch(`${apiUrl}/map/list`).then(r => r.json()).then(data => {
        const list: string[] = data.maps ?? []; setMaps(list); setSelectedMap(saveMapName.trim());
      });
    } else showMsg(`失敗: ${d.error}`);
  };

  const applyRotation = async () => {
    if (!selectedMap) { showMsg('既存マップを選択してから適用してください'); return; }
    const r = await fetch(`${apiUrl}/map/rotate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ map_name: selectedMap, degrees: rotDeg }),
    });
    const d = await r.json();
    if (!d.ok) { showMsg(`失敗: ${d.detail ?? ''}`); return; }
    showMsg(`${rotDeg.toFixed(1)}°回転保存完了`);
    setMeta(null); setMapImg(null); setKeeoutImg(null); setRotDeg(0);
    const load = (url: string, setter: (img: HTMLImageElement) => void) => {
      const img = new window.Image(); img.crossOrigin = 'anonymous'; img.onload = () => setter(img); img.src = url;
    };
    fetch(`${apiUrl}/map/meta?map_name=${encodeURIComponent(selectedMap)}`).then(r => r.json()).then(setMeta).catch(() => {});
    load(`${apiUrl}/map/image?map_name=${encodeURIComponent(selectedMap)}&type=map&t=${Date.now()}`, setMapImg);
    load(`${apiUrl}/map/image?map_name=${encodeURIComponent(selectedMap)}&type=keepout&t=${Date.now()}`, setKeeoutImg);
  };

  const confirmPlace = async () => {
    if (!placeName.trim() || !placeDraft || !selectedMap) return;
    const r = await fetch(`${apiUrl}/map/places/add`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ map_name: selectedMap, name: placeName.trim(), category: placeCategory, x: placeDraft.x, y: placeDraft.y, yaw: placeDraft.yaw }),
    });
    const d = await r.json();
    if (d.ok) { showMsg('ポイント追加完了'); setPlaceDraft(null); placeDraftRef.current = null; setPlaceName(''); fetchPlaces(); }
    else showMsg(`失敗: ${d.error}`);
  };

  const setDraftFromRobotPose = async () => {
    const r = await fetch(`${apiUrl}/ros/robot_pose?namespace=${namespace}`);
    const d = await r.json();
    if (!d.ok) { showMsg('ロボット位置を取得できませんでした'); return; }
    placeDraftRef.current = { x: d.x, y: d.y, yaw: d.yaw };
    placeDragging.current = false;
    setPlaceDraft({ x: d.x, y: d.y, yaw: d.yaw });
  };


  const confirmRoom = async () => {
    if (!roomName.trim() || !selectedMap) return;
    let points: [number, number][];
    if (roomSubMode === 'rect' && roomDraft) {
      points = [
        [roomDraft.x1, roomDraft.y1], [roomDraft.x2, roomDraft.y1],
        [roomDraft.x2, roomDraft.y2], [roomDraft.x1, roomDraft.y2],
      ];
    } else if (roomSubMode === 'polygon' && roomPolygon.length >= 3) {
      points = roomPolygon;
    } else return;
    const r = await fetch(`${apiUrl}/map/rooms/add`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ map_name: selectedMap, name: roomName.trim(), points }),
    });
    const d = await r.json();
    if (d.ok) {
      showMsg('部屋範囲を追加しました');
      setRoomDraft(null); roomDraftRef.current = null;
      setRoomPolygon([]); roomPolygonRef.current = [];
      setRoomMouseWorld(null); setRoomName(''); setRoomConfirming(false);
      fetchRooms();
    } else showMsg(`失敗: ${d.error}`);
  };

  const removePlace = (name: string) => {
    if (!selectedMap) return;
    fetch(`${apiUrl}/map/places/remove?map_name=${encodeURIComponent(selectedMap)}&name=${encodeURIComponent(name)}`, { method: 'DELETE' })
      .then(() => fetchPlaces()).catch(() => {});
  };

  const removeRoom = (name: string) => {
    if (!selectedMap) return;
    fetch(`${apiUrl}/map/rooms/remove?map_name=${encodeURIComponent(selectedMap)}&name=${encodeURIComponent(name)}`, { method: 'DELETE' })
      .then(() => fetchRooms()).catch(() => {});
  };

  const movePlaceUp = (cat: string, idx: number) => {
    if (idx === 0) return;
    const catPlaces = places.filter(p => p.category === cat);
    [catPlaces[idx - 1], catPlaces[idx]] = [catPlaces[idx], catPlaces[idx - 1]];
    const otherPlaces = places.filter(p => p.category !== cat);
    const newPlaces = [...otherPlaces, ...catPlaces];
    setPlaces(newPlaces);
    if (selectedMap)
      fetch(`${apiUrl}/map/places/reorder`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ map_name: selectedMap, places: newPlaces }),
      }).catch(() => {});
  };

  const renamePlace = async (oldName: string, newName: string) => {
    if (!selectedMap || !newName.trim() || newName.trim() === oldName) { setEditingItem(null); return; }
    await fetch(`${apiUrl}/map/places/rename?map_name=${encodeURIComponent(selectedMap)}&old_name=${encodeURIComponent(oldName)}&new_name=${encodeURIComponent(newName.trim())}`, { method: 'POST' });
    setEditingItem(null); fetchPlaces();
  };

  const renameRoom = async (oldName: string, newName: string) => {
    if (!selectedMap || !newName.trim() || newName.trim() === oldName) { setEditingItem(null); return; }
    await fetch(`${apiUrl}/map/rooms/rename?map_name=${encodeURIComponent(selectedMap)}&old_name=${encodeURIComponent(oldName)}&new_name=${encodeURIComponent(newName.trim())}`, { method: 'POST' });
    setEditingItem(null); fetchRooms();
  };

  const switchMode = (m: EditorMode) => {
    setEditorMode(m);
    setPlaceDraft(null); placeDraftRef.current = null; placeDragging.current = false;
    setRoomDraft(null); roomDraftRef.current = null; roomDrawing.current = false;
    setRoomPolygon([]); roomPolygonRef.current = []; setRoomMouseWorld(null); setRoomConfirming(false);
  };

  const cardStyle: React.CSSProperties = {
    background: 'var(--t-surface)', border: '1px solid var(--t-border)',
    borderRadius: 12, padding: '12px 14px', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden',
  };
  const btnStyle = (active?: boolean): React.CSSProperties => ({
    padding: '5px 10px', borderRadius: 8, border: 'none', cursor: 'pointer', fontSize: 12,
    background: active ? 'var(--t-accent)' : 'var(--t-surface2)', color: active ? '#fff' : 'var(--t-text)',
  });

  const MODE_DEFS: [EditorMode, string, string][] = [
    ['edit',   '🖊', 'マップ編集'],
    ['place',  '📍', 'ポイント追加'],
    ['room',   '🏠', '部屋範囲'],
    ['rename', '✏️', '名前変更'],
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr 220px', gap: 12, height: '100%', overflow: 'hidden' }}>

      {/* 左パネル */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minHeight: 0, overflow: 'hidden' }}>

        {/* マップ選択 */}
        <div style={cardStyle}>
          <SectionTitle>既存マップを編集</SectionTitle>
          <select value={selectedMap} onChange={e => setSelectedMap(e.target.value)}
            style={{ padding: '5px 8px', borderRadius: 8, border: '1px solid var(--t-border2)', background: 'var(--t-input-bg)', color: 'var(--t-text)', fontSize: 12 }}>
            <option value="">-- 選択 --</option>
            {maps.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>

        {/* SLAM保存 */}
        <div style={cardStyle}>
          <SectionTitle>作成中マップを編集</SectionTitle>
          <button onClick={previewLiveMap} disabled={previewing}
            style={{ ...btnStyle(), background: previewing ? 'var(--t-border)' : '#6644cc', color: '#fff', marginBottom: 8, width: '100%' }}>
            {previewing ? '取得中...' : '📡 SLAMプレビュー'}
          </button>
          <input value={saveMapName} onChange={e => setSaveMapName(e.target.value)} placeholder="フォルダ名"
            style={{ padding: '5px 8px', borderRadius: 8, border: '1px solid var(--t-border2)', background: 'var(--t-input-bg)', color: 'var(--t-text)', fontSize: 12, marginBottom: 6 }} />
          <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
            {(['extra', 'base'] as const).map(d => (
              <label key={d} style={{ fontSize: 11, color: 'var(--t-text-muted)', display: 'flex', alignItems: 'center', gap: 3 }}>
                <input type="radio" value={d} checked={saveDest === d} onChange={() => setSaveDest(d)} />
                {d === 'extra' ? '~/map' : 'navpkg'}
              </label>
            ))}
          </div>
          <button onClick={saveCurrentMap} disabled={saving}
            style={{ ...btnStyle(), background: saving ? 'var(--t-border)' : 'var(--t-accent)', color: '#fff', width: '100%' }}>
            {saving ? '保存中...' : 'SLAMマップ保存'}
          </button>
        </div>

        {/* モード切替 + ツール */}
        <div style={{ ...cardStyle, flex: 1, overflow: 'auto' }}>
          {/* モード切替 2×2 */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, marginBottom: 12, flexShrink: 0 }}>
            {MODE_DEFS.map(([m, icon, label]) => (
              <button key={m} onClick={() => switchMode(m)}
                style={{ padding: '6px 4px', border: 'none', cursor: 'pointer', fontSize: 11, borderRadius: 8, whiteSpace: 'nowrap',
                  background: editorMode === m ? '#0088ff' : 'var(--t-surface2)', color: editorMode === m ? '#fff' : 'var(--t-text)',
                  fontWeight: editorMode === m ? 'bold' : 'normal' }}>
                {icon} {label}
              </button>
            ))}
          </div>

          {/* マップ編集モード */}
          {editorMode === 'edit' && (
            <>
              <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
                {(['keepout', 'map'] as const).map(target => (
                  <button key={target} onClick={() => setEditTarget(target)}
                    style={{ ...btnStyle(editTarget === target), flex: 1 }}>
                    {target === 'keepout' ? 'keepout編集' : '地図本体編集'}
                  </button>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
                {(['pen', 'rect', 'eraser'] as Tool[]).map(t => (
                  <button key={t} onClick={() => setTool(t)} style={btnStyle(tool === t)}>
                    {t === 'pen' ? 'ペン' : t === 'rect' ? '矩形' : '消しゴム'}
                  </button>
                ))}
              </div>
              <div style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--t-text-muted)', marginBottom: 3 }}>
                  <span>サイズ</span><span>{brushSize}px</span>
                </div>
                <input type="range" min={1} max={40} value={brushSize} onChange={e => setBrushSize(Number(e.target.value))}
                  style={{ width: '100%', accentColor: 'var(--t-accent)' }} />
              </div>
              <div style={{ display: 'flex', gap: 5, marginBottom: 10 }}>
                <button onClick={undo} disabled={!canUndo} style={{ ...btnStyle(), flex: 1, opacity: canUndo ? 1 : 0.4 }}>↩ 戻す</button>
                {editTarget === 'keepout' ? (
                  <button onClick={saveKeeout} style={{ ...btnStyle(), flex: 1, background: 'var(--t-accent)', color: '#fff' }}>keepout保存</button>
                ) : (
                  <button onClick={saveMapImage} style={{ ...btnStyle(), flex: 1, background: '#cc6600', color: '#fff' }}>地図保存</button>
                )}
              </div>
              <div style={{ fontSize: 11, color: 'var(--t-text-muted)', marginBottom: 4 }}>
                回転 <span style={{ color: 'var(--t-text-dim)' }}>{rotDeg.toFixed(1)}°</span>
              </div>
              <input type="range" min={-180} max={180} step={0.5} value={rotDeg} onChange={e => setRotDeg(Number(e.target.value))}
                style={{ width: '100%', accentColor: 'var(--t-accent)', marginBottom: 5 }} />
              <div style={{ display: 'flex', gap: 5, marginBottom: 5, flexWrap: 'nowrap', alignItems: 'center' }}>
                <input type="number" step={0.5} value={rotDeg.toFixed(1)} onChange={e => setRotDeg(Number(e.target.value))}
                  style={{ flex: 1, minWidth: 0, padding: '4px 6px', borderRadius: 6, border: '1px solid var(--t-border2)', background: 'var(--t-input-bg)', color: 'var(--t-text)', fontSize: 12 }} />
                <button onClick={() => setRotDeg(0)} style={{ ...btnStyle(), whiteSpace: 'nowrap', flexShrink: 0 }}>リセット</button>
              </div>
              <button onClick={applyRotation} style={{ ...btnStyle(), background: selectedMap ? 'var(--t-accent)' : 'var(--t-border)', color: '#fff', width: '100%' }}>
                ファイルに適用
              </button>
            </>
          )}

          {/* ポイント追加モード */}
          {editorMode === 'place' && (
            <>
              <div style={{ fontSize: 11, color: 'var(--t-text-dim)', marginBottom: 8, lineHeight: 1.6 }}>
                マップをタップして場所を指定し、ドラッグして向きを決めてください
              </div>
              <button onClick={setDraftFromRobotPose}
                style={{ ...btnStyle(), background: '#00aa55', color: '#fff', width: '100%', marginBottom: 8 }}>
                📍 現在地を設定
              </button>
              {placeDraft && (
                <div style={{ background: 'var(--t-overlay)', borderRadius: 8, padding: '8px 10px', marginBottom: 8 }}>
                  <div style={{ fontSize: 11, color: 'var(--t-text-muted)', marginBottom: 3 }}>指定地点</div>
                  <div style={{ fontSize: 12, color: 'var(--t-text)' }}>({placeDraft.x.toFixed(2)}, {placeDraft.y.toFixed(2)})</div>
                  <div style={{ fontSize: 12, color: 'var(--t-text)' }}>向き: {(placeDraft.yaw * 180 / Math.PI).toFixed(1)}°</div>
                </div>
              )}
              <input value={placeName} onChange={e => setPlaceName(e.target.value)} placeholder="名前"
                style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid var(--t-border2)', background: 'var(--t-input-bg)', color: 'var(--t-text)', fontSize: 13, marginBottom: 6 }} />
              <select value={placeCategory} onChange={e => setPlaceCategory(e.target.value)}
                style={{ padding: '6px 8px', borderRadius: 8, border: '1px solid var(--t-border2)', background: 'var(--t-input-bg)', color: 'var(--t-text)', fontSize: 13, marginBottom: 8 }}>
                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
              {placeDraft && (
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={() => { setPlaceDraft(null); placeDraftRef.current = null; }} style={{ ...btnStyle(), flex: 1 }}>キャンセル</button>
                  <button onClick={confirmPlace} disabled={!placeName.trim() || !selectedMap}
                    style={{ ...btnStyle(), flex: 1, background: placeName.trim() && selectedMap ? 'var(--t-accent)' : 'var(--t-border)', color: '#fff' }}>
                    追加
                  </button>
                </div>
              )}
            </>
          )}

          {/* 名前変更モード */}
          {editorMode === 'rename' && (
            <div style={{ fontSize: 11, color: 'var(--t-text-dim)', lineHeight: 1.6 }}>
              右パネルのポイント・部屋名をクリックして編集できます
            </div>
          )}

          {/* 部屋範囲モード */}
          {editorMode === 'room' && (
            <>
              {/* サブモード切替 */}
              {!roomConfirming && (
                <div style={{ display: 'flex', background: 'var(--t-surface2)', borderRadius: 8, overflow: 'hidden', marginBottom: 10, flexShrink: 0 }}>
                  {(['rect', 'polygon'] as RoomSubMode[]).map(m => (
                    <button key={m} onClick={() => { setRoomSubMode(m); setRoomDraft(null); roomDraftRef.current = null; setRoomPolygon([]); roomPolygonRef.current = []; setRoomMouseWorld(null); }}
                      style={{ flex: 1, padding: '6px 4px', border: 'none', cursor: 'pointer', fontSize: 11, whiteSpace: 'nowrap',
                        background: roomSubMode === m ? '#ffaa00' : 'transparent', color: roomSubMode === m ? '#000' : 'var(--t-text)' }}>
                      {m === 'rect' ? '⬜ 矩形' : '⬡ ポリゴン'}
                    </button>
                  ))}
                </div>
              )}

              {roomConfirming ? (
                <>
                  <div style={{ background: 'var(--t-overlay)', borderRadius: 8, padding: '8px 10px', marginBottom: 8 }}>
                    <div style={{ fontSize: 11, color: 'var(--t-text-muted)', marginBottom: 3 }}>
                      {roomSubMode === 'rect' ? '矩形範囲' : `ポリゴン (${roomPolygon.length}点)`}
                    </div>
                  </div>
                  <input value={roomName} onChange={e => setRoomName(e.target.value)} placeholder="部屋名"
                    autoFocus
                    style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid var(--t-border2)', background: 'var(--t-input-bg)', color: 'var(--t-text)', fontSize: 13, marginBottom: 8 }} />
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button onClick={() => {
                      setRoomDraft(null); roomDraftRef.current = null;
                      setRoomPolygon([]); roomPolygonRef.current = []; setRoomConfirming(false);
                    }} style={{ ...btnStyle(), flex: 1 }}>キャンセル</button>
                    <button onClick={confirmRoom} disabled={!roomName.trim() || !selectedMap}
                      style={{ ...btnStyle(), flex: 1, background: roomName.trim() && selectedMap ? '#ffaa00' : 'var(--t-border)', color: roomName.trim() && selectedMap ? '#000' : 'var(--t-text)' }}>
                      追加
                    </button>
                  </div>
                </>
              ) : roomSubMode === 'rect' ? (
                <div style={{ fontSize: 11, color: 'var(--t-text-dim)' }}>マップをドラッグして範囲を選択</div>
              ) : (
                <>
                  <div style={{ fontSize: 11, color: 'var(--t-text-dim)', marginBottom: 8, lineHeight: 1.6 }}>
                    クリックでポイントを追加。<br />
                    最初のポイントに戻ると確定。
                  </div>
                  {roomPolygon.length > 0 && (
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button onClick={() => { setRoomPolygon([]); roomPolygonRef.current = []; setRoomMouseWorld(null); }} style={{ ...btnStyle(), flex: 1 }}>クリア</button>
                      {roomPolygon.length >= 3 && (
                        <button onClick={() => setRoomConfirming(true)}
                          style={{ ...btnStyle(), flex: 1, background: '#ffaa00', color: '#000' }}>
                          完了 ({roomPolygon.length}点)
                        </button>
                      )}
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* 中央: キャンバス */}
      <div style={{ ...cardStyle, padding: 0, position: 'relative', minWidth: 0 }}>
        {msg && (
          <div style={{ position: 'absolute', top: 10, left: '50%', transform: 'translateX(-50%)', background: '#333', color: '#fff', padding: '6px 16px', borderRadius: 12, fontSize: 12, zIndex: 10, whiteSpace: 'nowrap' }}>
            {msg}
          </div>
        )}
        {mapImg && (
          <div style={{ position: 'absolute', top: 8, left: 8, background: editorMode !== 'edit' ? 'rgba(0,100,200,0.8)' : 'rgba(0,0,0,0.5)', color: '#fff', padding: '3px 10px', borderRadius: 8, fontSize: 11, zIndex: 5 }}>
            {MODE_DEFS.find(([m]) => m === editorMode)?.[1]} {MODE_DEFS.find(([m]) => m === editorMode)?.[2]}モード
          </div>
        )}
        {mapImg && (
          <button
            onClick={() => setMapLocked(v => !v)}
            style={{ position: 'absolute', top: 8, right: 8, zIndex: 5, padding: '4px 12px', borderRadius: 8, border: 'none', cursor: 'pointer', fontSize: 13,
              background: mapLocked ? 'var(--t-accent)' : 'rgba(0,0,0,0.45)', color: '#fff' }}>
            {mapLocked ? '🔒 ロック中' : '🔓 ロック'}
          </button>
        )}
        {robotPose && mapImg && (
          <div style={{ position: 'absolute', bottom: 8, left: 8, background: 'rgba(0,0,0,0.6)', color: '#00ff88', padding: '3px 8px', borderRadius: 8, fontSize: 11, zIndex: 5 }}>
            🤖 ({robotPose.x.toFixed(2)}, {robotPose.y.toFixed(2)}) {(robotPose.yaw * 180 / Math.PI).toFixed(1)}°
          </div>
        )}

        {/* Google Maps風: 右下にズーム+/-と現在地ボタン、縮尺バー */}
        {mapImg && (
          <div style={{ position: 'absolute', bottom: 8, right: 8, zIndex: 6, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
            {scaleBar && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                <span style={{ fontSize: 10, color: '#fff', background: 'rgba(0,0,0,0.55)', padding: '1px 6px', borderRadius: 6 }}>
                  {scaleBar.meters >= 1 ? `${scaleBar.meters} m` : `${scaleBar.meters * 100} cm`}
                </span>
                <div style={{ width: Math.max(4, scaleBar.px), height: 3, background: '#fff', borderRadius: 2, boxShadow: '0 0 0 1px rgba(0,0,0,0.5)' }} />
              </div>
            )}
            <button
              onClick={recenterOnRobot}
              disabled={!robotPose}
              title="現在地に戻る"
              style={{
                width: 46, height: 46, borderRadius: '50%', border: '1px solid #fff',
                cursor: robotPose ? 'pointer' : 'not-allowed',
                background: 'rgba(0,0,0,0.6)', color: robotPose ? '#00ff88' : '#666',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: '0 1px 4px rgba(0,0,0,0.4)',
              }}
            >
              <Icon name="my_location" size={24} />
            </button>
            <div style={{ display: 'flex', flexDirection: 'column', borderRadius: 12, overflow: 'hidden', background: 'rgba(0,0,0,0.6)', border: '1px solid #fff', boxShadow: '0 1px 4px rgba(0,0,0,0.4)' }}>
              <button
                onClick={() => zoomBy(ZOOM_BUTTON_FACTOR)}
                title="ズームイン"
                style={{ width: 46, height: 40, border: 'none', cursor: 'pointer', background: 'transparent', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              ><Icon name="add" size={22} /></button>
              <div style={{ height: 1, background: 'rgba(255,255,255,0.35)' }} />
              <button
                onClick={() => zoomBy(1 / ZOOM_BUTTON_FACTOR)}
                title="ズームアウト"
                style={{ width: 46, height: 40, border: 'none', cursor: 'pointer', background: 'transparent', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              ><Icon name="remove" size={22} /></button>
            </div>
          </div>
        )}
        {!mapImg && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--t-text-dim)', fontSize: 13 }}>
            {selectedMap ? 'マップ読み込み中...' : 'マップを選択してください'}
          </div>
        )}
        <div ref={containerRef} style={{ position: 'absolute', inset: 0 }}>
          <canvas ref={canvasRef}
            style={{ width: '100%', height: '100%', touchAction: 'none' }}
            onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={onMouseUp} onMouseLeave={onMouseUp}
            onWheel={onWheel} onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd}
          />
        </div>
        <canvas ref={keepoutCanvasRef} style={{ display: 'none' }} />
        <canvas ref={mapCanvasRef} style={{ display: 'none' }} />
      </div>

      {/* 右パネル */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minHeight: 0, overflow: 'hidden' }}>

        {/* ポイント一覧 */}
        <div style={{ ...cardStyle, flex: 2 }}>
          <SectionTitle>ポイント一覧 <span style={{ fontSize: 10, color: 'var(--t-text-dim)', fontWeight: 'normal' }}>{selectedMap || '未選択'}</span></SectionTitle>
        <div style={{ fontSize: 10, color: 'var(--t-text-dim)', marginBottom: 6, flexShrink: 0 }}>名前をクリックで一つ上に移動</div>
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
            {CATEGORIES.map(cat => {
              const list = places.filter(p => p.category === cat);
              if (!list.length) return null;
              return (
                <div key={cat} style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 10, color: CAT_COLORS[cat] ?? 'var(--t-text-dim)', marginBottom: 3, textTransform: 'uppercase', letterSpacing: 1 }}>{cat}</div>
                  {list.map((p, idx) => (
                    <div key={p.name} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '5px 6px', borderRadius: 6, background: 'var(--t-overlay)', marginBottom: 2 }}>
                      <span style={{ fontSize: 11, color: 'var(--t-text-dim)', flexShrink: 0, width: 14, textAlign: 'right' }}>{idx + 1}</span>
                      {editorMode === 'rename' && editingItem?.type === 'place' && editingItem.name === p.name ? (
                        <input autoFocus value={editingItem.value}
                          onChange={e => setEditingItem({ ...editingItem, value: e.target.value })}
                          onKeyDown={e => { if (e.key === 'Enter') renamePlace(p.name, editingItem.value); if (e.key === 'Escape') setEditingItem(null); }}
                          onBlur={() => renamePlace(p.name, editingItem.value)}
                          style={{ flex: 1, padding: '2px 6px', borderRadius: 6, border: '1px solid #0088ff', background: 'var(--t-input-bg)', color: 'var(--t-text)', fontSize: 12 }} />
                      ) : (
                        <button onClick={() => editorMode === 'rename' ? setEditingItem({ type: 'place', name: p.name, value: p.name }) : movePlaceUp(cat, idx)}
                          style={{ fontSize: 12, color: (editorMode !== 'rename' && idx === 0) ? 'var(--t-text-dim)' : 'var(--t-text)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', background: 'transparent', border: 'none', cursor: 'pointer', textAlign: 'left', padding: 0 }}
                          title={editorMode === 'rename' ? '名前を編集' : idx === 0 ? '' : '一つ上に移動'}>
                          {p.name}
                        </button>
                      )}
                      <span style={{ fontSize: 10, color: 'var(--t-text-dim)', flexShrink: 0 }}>{(p.pose[2] * 180 / Math.PI).toFixed(0)}°</span>
                      <button onClick={() => removePlace(p.name)} style={{ padding: '1px 4px', borderRadius: 4, border: 'none', cursor: 'pointer', background: 'transparent', color: 'var(--t-text-dim)', fontSize: 11, flexShrink: 0 }}>✕</button>
                    </div>
                  ))}
                </div>
              );
            })}
            {places.length === 0 && <div style={{ fontSize: 12, color: 'var(--t-text-dim)' }}>なし</div>}
          </div>
        </div>

        {/* 部屋一覧 */}
        <div style={{ ...cardStyle, flex: 1 }}>
          <SectionTitle>部屋一覧</SectionTitle>
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
            {rooms.map((room, idx) => (
              <div key={room.name} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '4px 6px', borderRadius: 6, background: 'var(--t-overlay)', marginBottom: 2 }}>
                <div style={{ width: 8, height: 8, borderRadius: 2, background: ROOM_COLORS[idx % ROOM_COLORS.length], flexShrink: 0 }} />
                {editorMode === 'rename' && editingItem?.type === 'room' && editingItem.name === room.name ? (
                  <input autoFocus value={editingItem.value}
                    onChange={e => setEditingItem({ ...editingItem, value: e.target.value })}
                    onKeyDown={e => { if (e.key === 'Enter') renameRoom(room.name, editingItem.value); if (e.key === 'Escape') setEditingItem(null); }}
                    onBlur={() => renameRoom(room.name, editingItem.value)}
                    style={{ flex: 1, padding: '2px 6px', borderRadius: 6, border: '1px solid #0088ff', background: 'var(--t-input-bg)', color: 'var(--t-text)', fontSize: 12 }} />
                ) : (
                  <button onClick={() => editorMode === 'rename' && setEditingItem({ type: 'room', name: room.name, value: room.name })}
                    style={{ fontSize: 11, color: 'var(--t-text)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', background: 'transparent', border: 'none', cursor: editorMode === 'rename' ? 'pointer' : 'default', textAlign: 'left', padding: 0 }}
                    title={editorMode === 'rename' ? '名前を編集' : ''}>
                    {room.name}
                  </button>
                )}
                <button onClick={() => removeRoom(room.name)} style={{ padding: '1px 3px', borderRadius: 4, border: 'none', cursor: 'pointer', background: 'transparent', color: 'var(--t-text-dim)', fontSize: 10, flexShrink: 0 }}>✕</button>
              </div>
            ))}
            {rooms.length === 0 && <div style={{ fontSize: 11, color: 'var(--t-text-dim)' }}>なし</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
