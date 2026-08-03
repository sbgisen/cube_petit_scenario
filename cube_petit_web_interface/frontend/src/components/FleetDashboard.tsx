import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from './Icon';
import { ActiveStateIcon, colorForRobot, nicknameForRobot } from './RobotPicker';

// 「フリート運用」タブ: 共有マップ上に全機体の現在地を重ねて表示し、
// 1点への集合(move_to_pose一斉送信)・追いかけっこモード(chaserの目標をtargetの
// 現在地へ追従させ続けるループ)を操作する。ROSConJP 2026デモ(追いかけっこ・
// すれ違い挨拶)向け。詳細はplans/cube_petit_fleet_adapter_plan.md参照。

interface MapMeta {
  resolution: number;
  origin: [number, number, number];
}

interface FleetRobotState {
  pose: { x: number; y: number; yaw: number } | null;
  battery: number | null;
  map_name: string | null;
  bringup_active: boolean | null;
  nav_active: boolean | null;
  online: boolean;
  last_seen_sec_ago: number;
}

interface FleetResponse {
  available: boolean;
  error: string | null;
  robots: Record<string, FleetRobotState>;
}

// 会話デモ(指揮者方式・台本モード): ROSConJP 2026ブース。バックエンドは
// cube_petit_web_interface/conversation_conductor.py + routers/conversation_router.py。
// speakerはロボットのshort name(例: 'orange'、'cube_petit_'プレフィックスなし)。
interface ConversationLogEntry {
  speaker: string;
  text: string;
  face: string;
  success: boolean | null;
  error: string;
}

interface ConversationStatus {
  running: boolean;
  mode: string;
  participants: string[];
  current_turn: number;
  total_turns: number;
  log: ConversationLogEntry[];
  elapsed_sec: number;
  error: string;
}

interface Props {
  apiUrl: string;
}

const POLL_MS = 1000;
const CHASE_PERIOD_MS = 3000;
const ZOOM_MIN = 0.1;
const ZOOM_MAX = 10;
const ZOOM_BUTTON_FACTOR = 1.3;
const ROTATE_STEP = Math.PI / 4; // 左右回転ボタン1クリック分(45度)

// 会話デモの会場コンテキスト初期表示テキスト。バックエンドの
// cube_petit_web_interface/conversation_conductor_logic.py の
// DEFAULT_VENUE_CONTEXT と同内容(省略時にサーバー側で使われるデフォルトと同じ
// 文面をここでも表示し、当日ブースで話題を編集してから開始できるようにする)。
const DEFAULT_VENUE_CONTEXT =
  'ここはROSCon JP 2026(2026年8月4日・5日、茨城県つくば市の「つくばカピオ」)の会場です。' +
  'ROSコミュニティの年次イベントで、来場者はロボット開発者や研究者、学生が中心です。' +
  'ブースの前で会話を聞いている人にも届くように、ROSやロボット開発、つくば、' +
  'このイベント自体の話題を好んで話してください。\n' +
  'わたしたちキューブプチ(CubePetit)は22cm角・約6.3kgの立方体型パーソナルロボットです。' +
  'ROS 2 Jazzyで動いていて、LiDARとデプスカメラで自律ナビゲーションをし、' +
  'LLMでおしゃべりをして、ディスプレイの顔で表情を出します。研究・開発のプラットフォームとして使われていて、' +
  '今日はorange・pink・violetの3台で来ています。violetは今日は移動せずおしゃべり担当、' +
  'orangeとpinkは追いかけっこが得意です。\n' +
  '技術的な話も交えつつ、かわいらしく短い言葉で話してください。誇張したり、' +
  '実際にはできないことをできると言ったりしないでください。';

export function FleetDashboard({ apiUrl }: Props) {
  const [maps, setMaps] = useState<string[]>([]);
  const [selectedMap, setSelectedMap] = useState('');
  const [meta, setMeta] = useState<MapMeta | null>(null);
  const [mapImg, setMapImg] = useState<HTMLImageElement | null>(null);
  const [fleet, setFleet] = useState<FleetResponse | null>(null);
  const [msg, setMsg] = useState('');

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  // マップ画像の中心を軸とした回転(ラジアン)。0=北上(回転なし)
  const [rotation, setRotation] = useState(0);
  const panStart = useRef<{ mx: number; my: number; px: number; py: number } | null>(null);

  // ロック中はパン/ズーム/クリックでの目標地点指定を無効化(デモ中に画面が触られて
  // 誤操作するのを防ぐ)。ズーム+/-・全体表示ボタン自体は明示操作なのでロック中も有効
  const [mapLocked, setMapLocked] = useState(false);
  const mapLockedRef = useRef(false);
  mapLockedRef.current = mapLocked;

  const [targetPoint, setTargetPoint] = useState<{ x: number; y: number } | null>(null);
  // 'view'(既定): ドラッグでマップをパンできる。'gather': クリックで集合地点を指定する。
  // 'goal': 対象ロボット1台にゴールを送る。'localize': 対象ロボット1台の現在地(自己位置)を調整する
  type InteractionMode = 'view' | 'gather' | 'goal' | 'localize';
  const [interactionMode, setInteractionMode] = useState<InteractionMode>('view');
  // goal/localizeの対象ロボット
  const [actionRobot, setActionRobot] = useState('');
  // goal/localize用ドラフト: クリックで位置決め、ドラッグで向き(yaw)を決める(MapTabのplace
  // ドラフトと同じ操作感)
  const [draft, setDraft] = useState<{ x: number; y: number; yaw: number } | null>(null);
  const draftDraggingRef = useRef(false);

  // 追いかけっこは複数ペアを自由に組める(同じtargetを複数のchaserが追いかける、
  // 別々のペアを並行させる、等)。各ペアは独立にadd/remove可能
  const [chasePairs, setChasePairs] = useState<{ id: string; chaser: string; target: string }[]>([]);
  const [newChaser, setNewChaser] = useState('');
  const [newTarget, setNewTarget] = useState('');

  // ---- 会話デモ(台本モード/掛け合いモード) ----
  const [convoStatus, setConvoStatus] = useState<ConversationStatus | null>(null);
  const [convoParticipants, setConvoParticipants] = useState<string[]>([]);
  // 'script'(台本): 開始時にLLM1回で丸ごと台本生成。'interactive'(掛け合い):
  // 1ターン1回LLM呼び出し + orangeマイクのASRテキストを織り込む(バックエンドは
  // conversation_conductor.py の _run_interactive)。
  const [convoMode, setConvoMode] = useState<'script' | 'interactive'>('script');
  // 会場コンテキスト: 既定文(DEFAULT_VENUE_CONTEXT)を初期表示し、当日ブースで
  // 話題を差し替えたい時だけ折りたたみを開いて編集する(普段は畳んでおく)。
  const [convoContext, setConvoContext] = useState(DEFAULT_VENUE_CONTEXT);
  const [convoContextOpen, setConvoContextOpen] = useState(false);

  const showMsg = (m: string) => { setMsg(m); setTimeout(() => setMsg(''), 3000); };

  // ---- マップ一覧・選択 ----
  useEffect(() => {
    fetch(`${apiUrl}/map/list`).then(r => r.json()).then(d => {
      const list: string[] = d.maps ?? [];
      setMaps(list);
      if (list.length && !selectedMap) setSelectedMap(list[0]);
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl]);

  useEffect(() => {
    if (!selectedMap) return;
    setMeta(null); setMapImg(null); setTargetPoint(null); setDraft(null);
    fetch(`${apiUrl}/map/meta?map_name=${encodeURIComponent(selectedMap)}`)
      .then(r => r.json()).then(setMeta).catch(() => {});
    const img = new window.Image(); img.crossOrigin = 'anonymous';
    img.onload = () => setMapImg(img);
    img.src = `${apiUrl}/map/image?map_name=${encodeURIComponent(selectedMap)}&type=map&t=${Date.now()}`;
  }, [apiUrl, selectedMap]);

  // ---- fit on load(等倍上限を設けず、常にコンテナいっぱいに収まる最大サイズで表示する) ----
  useEffect(() => {
    if (!mapImg || !containerRef.current) return;
    const c = containerRef.current;
    const s = Math.min(c.clientWidth / mapImg.width, c.clientHeight / mapImg.height);
    setScale(s);
    setPan({ x: (c.clientWidth - mapImg.width * s) / 2, y: (c.clientHeight - mapImg.height * s) / 2 });
  }, [mapImg]);

  // ---- フリート状態ポーリング ----
  useEffect(() => {
    let cancelled = false;
    const poll = () =>
      fetch(`${apiUrl}/fleet/robots`).then(r => r.json())
        .then(d => { if (!cancelled) setFleet(d); }).catch(() => { if (!cancelled) setFleet(null); });
    poll();
    const t = setInterval(poll, POLL_MS);
    return () => { cancelled = true; clearInterval(t); };
  }, [apiUrl]);

  // ---- 座標変換(単位: ピクセル<->world[m]) ----
  // world<->px(マップ画像ピクセル座標)の変換自体は回転の影響を受けない。回転は
  // 「マップ画像の中心を軸にした表示上の回転」として、px<->screen(canvas実ピクセル)の
  // 変換(render()のctx.rotateとscreenToPx)側にのみ効かせる設計。
  const worldToPx = useCallback((wx: number, wy: number) => {
    if (!meta || !mapImg) return { px: 0, py: 0 };
    return {
      px: (wx - meta.origin[0]) / meta.resolution,
      py: mapImg.height - (wy - meta.origin[1]) / meta.resolution,
    };
  }, [meta, mapImg]);

  const pxToWorld = useCallback((px: number, py: number) => {
    if (!meta || !mapImg) return { x: 0, y: 0 };
    return {
      x: px * meta.resolution + meta.origin[0],
      y: (mapImg.height - py) * meta.resolution + meta.origin[1],
    };
  }, [meta, mapImg]);

  // screen(canvas実ピクセル) -> px(マップ画像ピクセル、回転前の座標系)。
  // render()での変換は translate(pan) -> scale(scale) -> [中心へtranslate -> rotate(rotation) ->
  // 中心から戻すtranslate] -> drawImage(0,0) の順なので、逆変換は scale/pan を戻した後、
  // 中心を軸に -rotation だけ回して戻す。
  const screenToPx = useCallback((clientX: number, clientY: number) => {
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    const sx = clientX - rect.left, sy = clientY - rect.top;
    if (!mapImg) return { px: 0, py: 0 };
    const cx = mapImg.width / 2, cy = mapImg.height / 2;
    const qx = (sx - pan.x) / scale - cx;
    const qy = (sy - pan.y) / scale - cy;
    const cos = Math.cos(-rotation), sin = Math.sin(-rotation);
    return { px: qx * cos - qy * sin + cx, py: qx * sin + qy * cos + cy };
  }, [mapImg, pan, scale, rotation]);

  // ---- 描画 ----
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !mapImg) return;
    const ctx = canvas.getContext('2d')!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    ctx.translate(pan.x, pan.y);
    ctx.scale(scale, scale);
    // マップ画像の中心を軸に回転(screenToPxの逆変換と対になる)
    const rcx = mapImg.width / 2, rcy = mapImg.height / 2;
    ctx.translate(rcx, rcy);
    ctx.rotate(rotation);
    ctx.translate(-rcx, -rcy);
    ctx.drawImage(mapImg, 0, 0);

    // 目標地点(集合先ドラフト)
    if (targetPoint) {
      const { px, py } = worldToPx(targetPoint.x, targetPoint.y);
      ctx.beginPath(); ctx.arc(px, py, 9 / scale, 0, Math.PI * 2);
      ctx.strokeStyle = '#ffaa00'; ctx.lineWidth = 3 / scale; ctx.setLineDash([4 / scale, 3 / scale]); ctx.stroke();
      ctx.setLineDash([]);
      ctx.beginPath(); ctx.moveTo(px - 12 / scale, py); ctx.lineTo(px + 12 / scale, py);
      ctx.moveTo(px, py - 12 / scale); ctx.lineTo(px, py + 12 / scale);
      ctx.strokeStyle = '#ffaa00'; ctx.lineWidth = 2 / scale; ctx.stroke();
    }

    // goal/localizeドラフト(クリック位置+ドラッグ方向の矢印)
    if (draft) {
      const { px, py } = worldToPx(draft.x, draft.y);
      const arrowLen = 20 / scale;
      const ax = px + Math.cos(-draft.yaw) * arrowLen, ay = py + Math.sin(-draft.yaw) * arrowLen;
      ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(ax, ay);
      ctx.strokeStyle = '#ff6600'; ctx.lineWidth = 3 / scale; ctx.stroke();
      ctx.beginPath(); ctx.arc(px, py, 7 / scale, 0, Math.PI * 2);
      ctx.strokeStyle = '#ff6600'; ctx.lineWidth = 2 / scale; ctx.stroke();
    }

    // 追いかけっこペア: chaserからtargetへの矢印(誰が誰を追っているか一目で分かるように、
    // chaserの色で点線+矢先を描く)
    if (fleet?.robots) {
      for (const pair of chasePairs) {
        const chaserRobot = fleet.robots[pair.chaser];
        const targetRobot = fleet.robots[pair.target];
        if (!chaserRobot?.pose || !targetRobot?.pose) continue;
        if (chaserRobot.map_name !== selectedMap || targetRobot.map_name !== selectedMap) continue;
        const from = worldToPx(chaserRobot.pose.x, chaserRobot.pose.y);
        const to = worldToPx(targetRobot.pose.x, targetRobot.pose.y);
        const color = colorForRobot(pair.chaser);
        const angle = Math.atan2(to.py - from.py, to.px - from.px);
        const headLen = 12 / scale;
        ctx.beginPath();
        ctx.moveTo(from.px, from.py);
        ctx.lineTo(to.px, to.py);
        ctx.strokeStyle = color;
        ctx.lineWidth = 2.5 / scale;
        ctx.setLineDash([6 / scale, 5 / scale]);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(to.px, to.py);
        ctx.lineTo(to.px - headLen * Math.cos(angle - Math.PI / 6), to.py - headLen * Math.sin(angle - Math.PI / 6));
        ctx.lineTo(to.px - headLen * Math.cos(angle + Math.PI / 6), to.py - headLen * Math.sin(angle + Math.PI / 6));
        ctx.closePath();
        ctx.fillStyle = color;
        ctx.fill();
      }
    }

    // 各ロボット(このマップにいるもののみ)
    if (fleet?.robots) {
      for (const [name, robot] of Object.entries(fleet.robots)) {
        if (!robot.pose || robot.map_name !== selectedMap) continue;
        const { px, py } = worldToPx(robot.pose.x, robot.pose.y);
        const color = colorForRobot(name);
        const imgYaw = -robot.pose.yaw;
        const len = 16 / scale, r = 8 / scale;
        ctx.globalAlpha = robot.online ? 1 : 0.4;
        ctx.beginPath(); ctx.arc(px, py, r, 0, Math.PI * 2);
        ctx.fillStyle = color; ctx.fill();
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 2 / scale; ctx.stroke();
        ctx.beginPath(); ctx.moveTo(px, py);
        ctx.lineTo(px + Math.cos(imgYaw) * len, py + Math.sin(imgYaw) * len);
        ctx.strokeStyle = color; ctx.lineWidth = 3 / scale; ctx.stroke();
        ctx.font = `bold ${12 / scale}px sans-serif`;
        ctx.fillStyle = color;
        ctx.fillText(nicknameForRobot(name), px + r + 4 / scale, py - r);
        ctx.globalAlpha = 1;
      }
    }
    ctx.restore();
  }, [mapImg, scale, pan, rotation, fleet, targetPoint, draft, selectedMap, worldToPx, chasePairs]);

  useEffect(() => {
    const canvas = canvasRef.current, cont = containerRef.current;
    if (!canvas || !cont) return;
    const resize = () => { canvas.width = cont.clientWidth; canvas.height = cont.clientHeight; render(); };
    resize();
    const obs = new ResizeObserver(resize);
    obs.observe(cont);
    return () => obs.disconnect();
  }, [render]);
  useEffect(() => { render(); }, [render]);

  // ---- マウス操作 ----
  // 既定(view)は左ドラッグ=パン。gatherは左クリックで集合地点を指定する。
  // goal/localizeは対象ロボットが選ばれていれば、クリック=位置決め+ドラッグ=向き指定
  // (MapTabのplaceドラフトと同じ操作感)。
  // 中クリック/alt+クリックはモードによらず常にパン(エスケープハッチ)。
  // ロック中はクリック/ドラッグ/ホイールを無視する(誤操作防止)
  const onMouseDown = (e: React.MouseEvent) => {
    if (mapLockedRef.current) return;
    if (e.button === 1 || (e.button === 0 && e.altKey)) {
      panStart.current = { mx: e.clientX, my: e.clientY, px: pan.x, py: pan.y }; return;
    }
    if (e.button !== 0 || !mapImg) return;
    if (interactionMode === 'gather') {
      const { px, py } = screenToPx(e.clientX, e.clientY);
      setTargetPoint(pxToWorld(px, py));
    } else if ((interactionMode === 'goal' || interactionMode === 'localize') && actionRobot) {
      const { px, py } = screenToPx(e.clientX, e.clientY);
      const w = pxToWorld(px, py);
      setDraft({ x: w.x, y: w.y, yaw: 0 });
      draftDraggingRef.current = true;
    } else {
      panStart.current = { mx: e.clientX, my: e.clientY, px: pan.x, py: pan.y };
    }
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (panStart.current) {
      setPan({ x: panStart.current.px + e.clientX - panStart.current.mx, y: panStart.current.py + e.clientY - panStart.current.my });
      return;
    }
    if (draftDraggingRef.current) {
      const { px, py } = screenToPx(e.clientX, e.clientY);
      const w = pxToWorld(px, py);
      setDraft(d => d ? { ...d, yaw: Math.atan2(w.y - d.y, w.x - d.x) } : d);
    }
  };
  const onMouseUp = () => { panStart.current = null; draftDraggingRef.current = false; };

  // ---- タッチ操作(スマホ/タブレット): 1本指=マウスドラッグと同じ挙動、2本指=ピンチズーム ----
  const touchPinchRef = useRef<number | null>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const onTouchStart = (e: TouchEvent) => {
      if (mapLockedRef.current) return;
      if (e.touches.length === 2) {
        e.preventDefault();
        touchPinchRef.current = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
        return;
      }
      if (e.touches.length !== 1 || !mapImg) return;
      e.preventDefault();
      const t = e.touches[0];
      if (interactionMode === 'gather') {
        const { px, py } = screenToPx(t.clientX, t.clientY);
        setTargetPoint(pxToWorld(px, py));
      } else if ((interactionMode === 'goal' || interactionMode === 'localize') && actionRobot) {
        const { px, py } = screenToPx(t.clientX, t.clientY);
        const w = pxToWorld(px, py);
        setDraft({ x: w.x, y: w.y, yaw: 0 });
        draftDraggingRef.current = true;
      } else {
        panStart.current = { mx: t.clientX, my: t.clientY, px: pan.x, py: pan.y };
      }
    };

    const onTouchMove = (e: TouchEvent) => {
      if (mapLockedRef.current) return;
      if (e.touches.length === 2 && touchPinchRef.current !== null) {
        e.preventDefault();
        const dist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
        const factor = dist / touchPinchRef.current;
        touchPinchRef.current = dist;
        setScale(s => Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, s * factor)));
        return;
      }
      if (e.touches.length !== 1) return;
      e.preventDefault();
      const t = e.touches[0];
      if (panStart.current) {
        setPan({ x: panStart.current.px + t.clientX - panStart.current.mx, y: panStart.current.py + t.clientY - panStart.current.my });
        return;
      }
      if (draftDraggingRef.current) {
        const { px, py } = screenToPx(t.clientX, t.clientY);
        const w = pxToWorld(px, py);
        setDraft(d => d ? { ...d, yaw: Math.atan2(w.y - d.y, w.x - d.x) } : d);
      }
    };

    const onTouchEnd = () => {
      touchPinchRef.current = null;
      panStart.current = null;
      draftDraggingRef.current = false;
    };

    canvas.addEventListener('touchstart', onTouchStart, { passive: false });
    canvas.addEventListener('touchmove', onTouchMove, { passive: false });
    canvas.addEventListener('touchend', onTouchEnd);
    canvas.addEventListener('touchcancel', onTouchEnd);
    return () => {
      canvas.removeEventListener('touchstart', onTouchStart);
      canvas.removeEventListener('touchmove', onTouchMove);
      canvas.removeEventListener('touchend', onTouchEnd);
      canvas.removeEventListener('touchcancel', onTouchEnd);
    };
  }, [mapImg, pan, scale, interactionMode, actionRobot, screenToPx, pxToWorld]);
  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    if (mapLockedRef.current) return;
    const f = e.deltaY < 0 ? 1.1 : 0.9;
    const rect = canvasRef.current!.getBoundingClientRect();
    const cx = e.clientX - rect.left, cy = e.clientY - rect.top;
    setScale(s => {
      const ns = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, s * f));
      setPan(p => ({ x: cx - (cx - p.x) * (ns / s), y: cy - (cy - p.y) * (ns / s) }));
      return ns;
    });
  };

  // Google Maps風ズーム+/-(明示ボタン操作なのでロック中も有効)。今画面(canvas)に
  // 見えている表示領域の中心を固定点にしてズームする(onWheelのマウス位置基準ズームと
  // 同じ考え方で、基準点をcontainerの中心に固定したもの)。この計算はスクリーン座標系
  // だけで完結する(screenToPxを経由しない)ので、回転(rotation)があっても影響を受けない。
  // ※マップ画像自体の中心ではない: マップを隅にパンして見ている状態では画像の中心は
  // 画面外にあり、そちらを基準にすると「今見えている場所」からズレて見えてしまう
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

  // マップの中心に画面を戻す(+ズーム・回転もリセットして全体表示。等倍上限は設けず、
  // 常にコンテナいっぱいに収まる最大サイズで表示する)
  const fitToView = useCallback(() => {
    if (!mapImg || !containerRef.current) return;
    const c = containerRef.current;
    const s = Math.min(c.clientWidth / mapImg.width, c.clientHeight / mapImg.height);
    setScale(s);
    setRotation(0);
    setPan({ x: (c.clientWidth - mapImg.width * s) / 2, y: (c.clientHeight - mapImg.height * s) / 2 });
  }, [mapImg]);

  const rotateBy = useCallback((delta: number) => {
    setRotation(r => {
      let nr = (r + delta) % (Math.PI * 2);
      if (nr < 0) nr += Math.PI * 2;
      return nr;
    });
  }, []);

  // ---- コマンド送信 ----
  const sendMoveToPose = async (robotName: string, x: number, y: number, yaw: number) => {
    const res = await fetch(`${apiUrl}/fleet/command`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ robot_name: robotName, method: 'move_to_pose', args: { x, y, yaw, map_name: selectedMap } }),
    }).then(r => r.json()).catch(() => ({ ok: false, error: '通信エラー' }));
    return res;
  };

  const sendLocalize = async (robotName: string, x: number, y: number, theta: number) => {
    const res = await fetch(`${apiUrl}/fleet/command`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ robot_name: robotName, method: 'localize', args: { pose: { x, y, theta }, map_name: selectedMap } }),
    }).then(r => r.json()).catch(() => ({ ok: false, error: '通信エラー' }));
    return res;
  };

  const onlineRobotsOnMap = Object.entries(fleet?.robots ?? {})
    .filter(([, r]) => r.online && r.map_name === selectedMap);

  const gatherHere = async () => {
    if (!targetPoint) return;
    let ok = 0, fail = 0;
    for (const [name] of onlineRobotsOnMap) {
      const res = await sendMoveToPose(name, targetPoint.x, targetPoint.y, 0);
      if (res.ok) ok++; else fail++;
    }
    showMsg(`集合指令を送信: 成功${ok}件${fail ? ` / 失敗${fail}件` : ''}`);
  };

  const confirmDraftAction = async () => {
    if (!draft || !actionRobot) return;
    const res = interactionMode === 'localize'
      ? await sendLocalize(actionRobot, draft.x, draft.y, draft.yaw)
      : await sendMoveToPose(actionRobot, draft.x, draft.y, draft.yaw);
    const actionLabel = interactionMode === 'localize' ? '現在地を設定' : 'ゴールを送信';
    showMsg(res.ok ? `${nicknameForRobot(actionRobot)}へ${actionLabel}しました` : `送信失敗: ${res.error ?? ''}`);
    setDraft(null);
  };

  // ---- 追いかけっこモード(複数ペアを自由に組める。ループ自体は常駐APIサーバー側で
  // 3秒ごとに回っており、ここではサーバーの状態(GET /fleet/chase/list)をポーリングして
  // 表示するだけ。ブラウザがタブを離れても停止しない) ----
  useEffect(() => {
    let cancelled = false;
    const poll = () =>
      fetch(`${apiUrl}/fleet/chase/list`).then(r => r.json())
        .then(d => { if (!cancelled) setChasePairs(d.pairs ?? []); }).catch(() => {});
    poll();
    const t = setInterval(poll, POLL_MS);
    return () => { cancelled = true; clearInterval(t); };
  }, [apiUrl]);

  const addChasePair = async () => {
    if (!newChaser || !newTarget || newChaser === newTarget) return;
    const res = await fetch(`${apiUrl}/fleet/chase/start`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chaser: newChaser, target: newTarget }),
    }).then(r => r.json()).catch(() => ({ ok: false, error: '通信エラー' }));
    if (res.ok) {
      setNewChaser(''); setNewTarget('');
    } else {
      showMsg(`ペアの追加に失敗: ${res.error ?? ''}`);
    }
  };

  const removeChasePair = async (id: string) => {
    const res = await fetch(`${apiUrl}/fleet/chase/stop?pair_id=${encodeURIComponent(id)}`, { method: 'POST' })
      .then(r => r.json()).catch(() => ({ ok: false }));
    if (!res.ok) showMsg('ペアの停止に失敗しました');
  };

  // ---- 会話デモ(指揮者・台本モード): サーバー側の常駐スレッドで実行され、
  // ブラウザ側はGET /fleet/conversation/statusをポーリングして表示するだけ
  // (追いかけっこモードと同じ、タブ切替/クローズに影響されない設計) ----
  useEffect(() => {
    let cancelled = false;
    const poll = () =>
      fetch(`${apiUrl}/fleet/conversation/status`).then(r => r.json())
        .then(d => { if (!cancelled) setConvoStatus(d); }).catch(() => { if (!cancelled) setConvoStatus(null); });
    poll();
    const t = setInterval(poll, POLL_MS);
    return () => { cancelled = true; clearInterval(t); };
  }, [apiUrl]);

  const toggleConvoParticipant = (name: string) => {
    setConvoParticipants(prev => prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name]);
  };

  const startConversation = async () => {
    const res = await fetch(`${apiUrl}/fleet/conversation/start`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ participants: convoParticipants, mode: convoMode, context: convoContext }),
    }).then(r => r.json()).catch(() => ({ ok: false, error: '通信エラー' }));
    if (!res.ok) showMsg(`会話デモの開始に失敗: ${res.error ?? ''}`);
  };

  const stopConversation = async () => {
    const res = await fetch(`${apiUrl}/fleet/conversation/stop`, { method: 'POST' })
      .then(r => r.json()).catch(() => ({ ok: false }));
    if (!res.ok) showMsg('会話デモの停止に失敗しました');
  };

  const allRobotNames = Object.keys(fleet?.robots ?? {}).sort();
  const offMapRobots = Object.entries(fleet?.robots ?? {}).filter(([, r]) => r.map_name !== selectedMap);
  // 追いかけっこは選択中マップにいるロボット同士でしか成立しない(別マップの機体を
  // 目標にmove_to_poseしても座標系が合わず届かないため)
  const robotNamesOnSelectedMap = onlineRobotsOnMap.map(([name]) => name).sort();

  return (
    <div style={{ display: 'flex', gap: 12, height: '100%', overflow: 'hidden' }}>
      {/* 左: マップ + ロボット重畳表示 */}
      <div style={{ flex: 3, minWidth: 0, position: 'relative', background: 'var(--t-surface)', borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ position: 'absolute', top: 8, left: 8, zIndex: 5, display: 'flex', gap: 8, alignItems: 'center' }}>
          <select value={selectedMap} onChange={e => setSelectedMap(e.target.value)} style={{
            padding: '6px 10px', borderRadius: 8, border: '1px solid var(--t-border2)',
            background: 'var(--t-input-bg)', color: 'var(--t-text)', fontSize: 13,
          }}>
            {maps.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          {onlineRobotsOnMap.length > 0 && (
            <span style={{ fontSize: 11, color: 'var(--t-text-dim)', background: 'var(--t-surface2)', padding: '3px 8px', borderRadius: 8 }}>
              このマップ上: {onlineRobotsOnMap.length}台
            </span>
          )}
          <div style={{ display: 'flex', background: 'var(--t-surface2)', borderRadius: 8, overflow: 'hidden' }}>
            {([
              ['view', '表示', 'pan_tool', 'ドラッグで地図を移動'],
              ['gather', '集合', 'push_pin', 'クリックで集合地点を指定'],
              ['goal', 'ゴール', 'flag', '対象ロボットを選んでクリック(ドラッグで向き指定)'],
              ['localize', '現在地調整', 'my_location', '対象ロボットを選んでクリック(ドラッグで向き指定)'],
            ] as [InteractionMode, string, string, string][]).map(([m, label, icon, title]) => (
              <button key={m} onClick={() => { setInteractionMode(m); setDraft(null); setTargetPoint(null); }} title={title} style={{
                display: 'flex', alignItems: 'center', gap: 4, padding: '5px 10px', border: 'none', cursor: 'pointer', fontSize: 12, whiteSpace: 'nowrap',
                background: interactionMode === m ? 'var(--t-accent)' : 'transparent', color: interactionMode === m ? '#fff' : 'var(--t-text)',
              }}>
                <Icon name={icon} size={14} />{label}
              </button>
            ))}
          </div>
          {(interactionMode === 'goal' || interactionMode === 'localize') && (
            <select value={actionRobot} onChange={e => { setActionRobot(e.target.value); setDraft(null); }} style={{
              padding: '5px 8px', borderRadius: 8, border: '1px solid var(--t-border2)',
              background: 'var(--t-input-bg)', color: 'var(--t-text)', fontSize: 12,
            }}>
              <option value="">対象ロボット</option>
              {allRobotNames.map(n => <option key={n} value={n}>{nicknameForRobot(n)}</option>)}
            </select>
          )}
          <button
            onClick={() => setMapLocked(v => !v)}
            title={mapLocked ? 'ロック中(クリック/ドラッグ/ズーム無効)' : 'ロック解除'}
            style={{
              display: 'flex', alignItems: 'center', gap: 4, padding: '5px 10px', borderRadius: 8, border: 'none', cursor: 'pointer',
              background: mapLocked ? 'var(--t-accent)' : 'var(--t-surface2)', color: mapLocked ? '#fff' : 'var(--t-text)', fontSize: 12,
            }}
          >
            <Icon name={mapLocked ? 'lock' : 'lock_open'} size={15} />
          </button>
        </div>
        {msg && (
          <div style={{ position: 'absolute', top: 8, left: '50%', transform: 'translateX(-50%)', background: '#333', color: '#fff', padding: '6px 16px', borderRadius: 12, fontSize: 12, zIndex: 10, whiteSpace: 'nowrap' }}>
            {msg}
          </div>
        )}
        {!mapImg && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--t-text-dim)', fontSize: 13 }}>
            {selectedMap ? 'マップ読み込み中...' : 'マップがありません'}
          </div>
        )}
        {targetPoint && (
          <div style={{ position: 'absolute', bottom: 8, left: 8, zIndex: 5, display: 'flex', gap: 8, alignItems: 'center' }}>
            <button onClick={gatherHere} disabled={onlineRobotsOnMap.length === 0} style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', borderRadius: 20, border: 'none',
              cursor: onlineRobotsOnMap.length ? 'pointer' : 'not-allowed',
              background: 'var(--t-accent)', color: '#fff', fontSize: 13, opacity: onlineRobotsOnMap.length ? 1 : 0.5,
            }}>
              <Icon name="groups" size={16} /> ここに集合({onlineRobotsOnMap.length}台)
            </button>
            <button onClick={() => setTargetPoint(null)} style={{
              width: 30, height: 30, borderRadius: '50%', border: 'none', cursor: 'pointer',
              background: 'rgba(0,0,0,0.5)', color: '#fff',
            }}><Icon name="close" size={16} /></button>
          </div>
        )}
        {draft && actionRobot && (
          <div style={{ position: 'absolute', bottom: 8, left: 8, zIndex: 5, display: 'flex', gap: 8, alignItems: 'center' }}>
            <button onClick={confirmDraftAction} style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', borderRadius: 20, border: 'none', cursor: 'pointer',
              background: 'var(--t-accent)', color: '#fff', fontSize: 13,
            }}>
              <Icon name={interactionMode === 'localize' ? 'my_location' : 'flag'} size={16} />
              {nicknameForRobot(actionRobot)}{interactionMode === 'localize' ? 'の現在地に設定' : 'へゴール送信'}
            </button>
            <button onClick={() => setDraft(null)} style={{
              width: 30, height: 30, borderRadius: '50%', border: 'none', cursor: 'pointer',
              background: 'rgba(0,0,0,0.5)', color: '#fff',
            }}><Icon name="close" size={16} /></button>
          </div>
        )}
        {/* Google Maps風: 右下に全体表示・ズーム+/- */}
        {mapImg && (
          <div style={{ position: 'absolute', bottom: 8, right: 8, zIndex: 6, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
            <button
              onClick={fitToView}
              title="全体表示"
              style={{
                width: 46, height: 46, borderRadius: '50%', border: '1px solid #fff', cursor: 'pointer',
                background: 'rgba(0,0,0,0.6)', color: '#fff',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: '0 1px 4px rgba(0,0,0,0.4)',
              }}
            ><Icon name="fit_screen" size={22} /></button>
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
            <div style={{ display: 'flex', borderRadius: 12, overflow: 'hidden', background: 'rgba(0,0,0,0.6)', border: '1px solid #fff', boxShadow: '0 1px 4px rgba(0,0,0,0.4)' }}>
              <button
                onClick={() => rotateBy(-ROTATE_STEP)}
                title="左に45度回転"
                style={{ width: 40, height: 40, border: 'none', cursor: 'pointer', background: 'transparent', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              ><Icon name="rotate_left" size={20} /></button>
              <div style={{ width: 1, background: 'rgba(255,255,255,0.35)' }} />
              <button
                onClick={() => rotateBy(ROTATE_STEP)}
                title="右に45度回転"
                style={{ width: 40, height: 40, border: 'none', cursor: 'pointer', background: 'transparent', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              ><Icon name="rotate_right" size={20} /></button>
            </div>
          </div>
        )}
        <div ref={containerRef} style={{ position: 'absolute', inset: 0, cursor: mapLocked ? 'not-allowed' : undefined }}>
          <canvas ref={canvasRef}
            style={{ width: '100%', height: '100%', cursor: mapLocked ? 'not-allowed' : interactionMode === 'view' ? 'grab' : 'crosshair' }}
            onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={onMouseUp} onMouseLeave={onMouseUp}
            onWheel={onWheel}
          />
        </div>
      </div>

      {/* 右: 操作パネル */}
      <div style={{ flex: 1, minWidth: 220, maxWidth: 280, display: 'flex', flexDirection: 'column', gap: 16, overflowY: 'auto' }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 'bold', color: 'var(--t-text-muted)', marginBottom: 8 }}>機体一覧</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {allRobotNames.map(name => {
              const r = fleet!.robots[name];
              return (
                <div key={name} style={{
                  display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', borderRadius: 10,
                  background: 'var(--t-surface2)', fontSize: 12, opacity: r.online ? 1 : 0.5,
                }}>
                  <div style={{ width: 9, height: 9, borderRadius: '50%', background: colorForRobot(name), flexShrink: 0 }} />
                  <span style={{ flex: 1, color: 'var(--t-text)' }}>{nicknameForRobot(name)}</span>
                  <ActiveStateIcon
                    name="power_settings_new" active={r.bringup_active}
                    activeLabel="bringup: 起動中" inactiveLabel="bringup: 停止中"
                  />
                  <ActiveStateIcon
                    name="near_me" active={r.nav_active}
                    activeLabel="navigation: 起動中" inactiveLabel="navigation: 停止中"
                  />
                  <span style={{ color: 'var(--t-text-dim)' }}>{r.map_name ?? '?'}</span>
                </div>
              );
            })}
            {allRobotNames.length === 0 && <div style={{ fontSize: 12, color: 'var(--t-text-dim)' }}>フリートが見えていません</div>}
          </div>
          {offMapRobots.length > 0 && (
            <div style={{ fontSize: 11, color: 'var(--t-text-dim)', marginTop: 6 }}>
              ※別マップ: {offMapRobots.map(([n, r]) => `${nicknameForRobot(n)}(${r.map_name ?? '?'})`).join(', ')}
            </div>
          )}
        </div>

        <div>
          <div style={{ fontSize: 13, fontWeight: 'bold', color: 'var(--t-text-muted)', marginBottom: 8 }}>追いかけっこモード</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label style={{ fontSize: 11, color: 'var(--t-text-dim)' }}>追いかける側(chaser)</label>
            <select value={newChaser} onChange={e => setNewChaser(e.target.value)} style={selectStyle}>
              <option value="">選択してください</option>
              {robotNamesOnSelectedMap.map(n => <option key={n} value={n}>{nicknameForRobot(n)}</option>)}
            </select>
            <label style={{ fontSize: 11, color: 'var(--t-text-dim)' }}>追いかけられる側(target)</label>
            <select value={newTarget} onChange={e => setNewTarget(e.target.value)} style={selectStyle}>
              <option value="">選択してください</option>
              {robotNamesOnSelectedMap.filter(n => n !== newChaser).map(n => <option key={n} value={n}>{nicknameForRobot(n)}</option>)}
            </select>
            {robotNamesOnSelectedMap.length === 0 && (
              <div style={{ fontSize: 11, color: 'var(--t-text-dim)' }}>このマップ上にオンラインの機体がいません</div>
            )}
            <button onClick={addChasePair} disabled={!newChaser || !newTarget || newChaser === newTarget} style={{
              marginTop: 4, padding: '8px 0', borderRadius: 10, border: 'none',
              cursor: newChaser && newTarget && newChaser !== newTarget ? 'pointer' : 'not-allowed',
              background: 'var(--t-accent)', color: '#fff', fontSize: 13,
              opacity: newChaser && newTarget && newChaser !== newTarget ? 1 : 0.5,
            }}>ペアを追加</button>

            {chasePairs.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }}>
                {chasePairs.map(p => (
                  <div key={p.id} style={{
                    display: 'flex', alignItems: 'center', gap: 6, fontSize: 12,
                    background: 'var(--t-surface2)', padding: '6px 10px', borderRadius: 8,
                  }}>
                    <span style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span style={{
                        padding: '2px 8px', borderRadius: 10, color: '#fff', fontWeight: 'bold',
                        background: colorForRobot(p.chaser), whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                      }} title="追いかける側(chaser)">{nicknameForRobot(p.chaser)}</span>
                      <Icon name="arrow_forward" size={14} />
                      <span style={{
                        padding: '2px 8px', borderRadius: 10, color: '#fff', fontWeight: 'bold',
                        background: colorForRobot(p.target), whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                      }} title="追いかけられる側(target)">{nicknameForRobot(p.target)}</span>
                    </span>
                    <button onClick={() => removeChasePair(p.id)} title="このペアを停止" style={{
                      width: 22, height: 22, borderRadius: '50%', border: 'none', cursor: 'pointer',
                      background: '#cc3333', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                    }}><Icon name="close" size={12} /></button>
                  </div>
                ))}
                <div style={{ fontSize: 11, color: 'var(--t-text-dim)' }}>
                  {CHASE_PERIOD_MS / 1000}秒ごとに現在地へ追従送信中({chasePairs.length}組)
                </div>
              </div>
            )}
          </div>
        </div>

        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <div style={{ fontSize: 13, fontWeight: 'bold', color: 'var(--t-text-muted)' }}>会話デモ</div>
            <div style={{ display: 'flex', background: 'var(--t-surface2)', borderRadius: 8, overflow: 'hidden' }}>
              {([
                ['script', '台本', '台本モード: 開始時にLLM1回で丸ごと台本を生成して再生します'],
                ['interactive', '掛け合い', '掛け合いモード: 1ターンずつLLMを呼び、orangeのマイクで拾った来場者の発話も織り込みます'],
              ] as ['script' | 'interactive', string, string][]).map(([m, label, title]) => (
                <button
                  key={m}
                  onClick={() => setConvoMode(m)}
                  disabled={!!convoStatus?.running}
                  title={title}
                  style={{
                    padding: '4px 10px', border: 'none', fontSize: 12, whiteSpace: 'nowrap',
                    cursor: convoStatus?.running ? 'not-allowed' : 'pointer',
                    background: convoMode === m ? 'var(--t-accent)' : 'transparent',
                    color: convoMode === m ? '#fff' : 'var(--t-text)',
                    opacity: convoStatus?.running && convoMode !== m ? 0.5 : 1,
                  }}
                >{label}</button>
              ))}
            </div>
          </div>
          <div style={{ marginBottom: 8 }}>
            <button
              onClick={() => setConvoContextOpen(v => !v)}
              style={{
                display: 'flex', alignItems: 'center', gap: 4, padding: '2px 0', border: 'none', background: 'none',
                color: 'var(--t-text-dim)', fontSize: 11, cursor: 'pointer',
              }}
            >
              <Icon name={convoContextOpen ? 'expand_more' : 'chevron_right'} size={14} />
              会場コンテキスト{convoStatus?.running ? '(実行中は編集できません)' : ''}
            </button>
            {convoContextOpen && (
              <textarea
                value={convoContext}
                disabled={!!convoStatus?.running}
                onChange={e => setConvoContext(e.target.value)}
                rows={6}
                style={{
                  width: '100%', boxSizing: 'border-box', marginTop: 4, padding: 8, borderRadius: 8,
                  border: '1px solid var(--t-border2)', background: 'var(--t-input-bg)', color: 'var(--t-text)',
                  fontSize: 12, resize: 'vertical',
                }}
              />
            )}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {allRobotNames.map(name => (
                <label key={name} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={convoParticipants.includes(name)}
                    disabled={!!convoStatus?.running}
                    onChange={() => toggleConvoParticipant(name)}
                  />
                  <span style={{ color: colorForRobot(name) }}>{nicknameForRobot(name)}</span>
                </label>
              ))}
              {allRobotNames.length === 0 && <div style={{ fontSize: 11, color: 'var(--t-text-dim)' }}>フリートが見えていません</div>}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={startConversation}
                disabled={!!convoStatus?.running || convoParticipants.length < 2}
                style={{
                  flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, padding: '8px 0',
                  borderRadius: 10, border: 'none',
                  cursor: !convoStatus?.running && convoParticipants.length >= 2 ? 'pointer' : 'not-allowed',
                  background: 'var(--t-accent)', color: '#fff', fontSize: 13,
                  opacity: !convoStatus?.running && convoParticipants.length >= 2 ? 1 : 0.5,
                }}
              ><Icon name="play_arrow" size={16} /> 開始</button>
              <button
                onClick={stopConversation}
                disabled={!convoStatus?.running}
                style={{
                  flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, padding: '8px 0',
                  borderRadius: 10, border: 'none', cursor: convoStatus?.running ? 'pointer' : 'not-allowed',
                  background: '#cc3333', color: '#fff', fontSize: 13, opacity: convoStatus?.running ? 1 : 0.5,
                }}
              ><Icon name="stop" size={16} /> 停止</button>
            </div>
            {convoStatus && (
              <div style={{ fontSize: 11, color: 'var(--t-text-dim)' }}>
                {convoStatus.running
                  ? (convoStatus.mode === 'interactive'
                    ? `掛け合い中: 第${convoStatus.current_turn}ターン・経過${Math.round(convoStatus.elapsed_sec)}秒`
                    : `再生中: ${convoStatus.current_turn}/${convoStatus.total_turns}ターン・経過${Math.round(convoStatus.elapsed_sec)}秒`)
                  : convoStatus.error
                    ? `エラー: ${convoStatus.error}`
                    : convoStatus.log.length > 0 ? `終了(経過${Math.round(convoStatus.elapsed_sec)}秒)` : '停止中'}
              </div>
            )}
            {convoStatus && convoStatus.log.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 220, overflowY: 'auto' }}>
                {convoStatus.log.map((entry, i) => {
                  const isHuman = entry.speaker === 'human';
                  return (
                    <div key={i} style={{
                      fontSize: 12, background: 'var(--t-surface2)', borderRadius: 8, padding: '6px 8px',
                      borderLeft: `3px solid ${colorForRobot(entry.speaker)}`,
                      fontStyle: isHuman ? 'italic' : 'normal',
                    }}>
                      <span style={{ fontWeight: 'bold', color: colorForRobot(entry.speaker) }}>
                        {isHuman && <Icon name="person" size={12} />} {nicknameForRobot(entry.speaker)}
                      </span>
                      <span style={{ marginLeft: 6, color: 'var(--t-text)' }}>{entry.text}</span>
                      {entry.success === false && (
                        <span style={{ marginLeft: 6, color: '#cc3333' }} title={entry.error || '発話に失敗しました'}>
                          <Icon name="warning" size={12} />
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

const selectStyle: React.CSSProperties = {
  padding: '6px 8px', borderRadius: 8, border: '1px solid var(--t-border2)',
  background: 'var(--t-input-bg)', color: 'var(--t-text)', fontSize: 12,
};
