import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from './Icon';
import { colorForRobot, nicknameForRobot } from './RobotPicker';

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
  online: boolean;
  last_seen_sec_ago: number;
}

interface FleetResponse {
  available: boolean;
  error: string | null;
  robots: Record<string, FleetRobotState>;
}

interface Props {
  apiUrl: string;
}

const POLL_MS = 1000;
const CHASE_PERIOD_MS = 3000;

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
  const panStart = useRef<{ mx: number; my: number; px: number; py: number } | null>(null);

  const [targetPoint, setTargetPoint] = useState<{ x: number; y: number } | null>(null);

  const [chaser, setChaser] = useState('');
  const [chaseTarget, setChaseTarget] = useState('');
  const [chasing, setChasing] = useState(false);

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
    setMeta(null); setMapImg(null); setTargetPoint(null);
    fetch(`${apiUrl}/map/meta?map_name=${encodeURIComponent(selectedMap)}`)
      .then(r => r.json()).then(setMeta).catch(() => {});
    const img = new window.Image(); img.crossOrigin = 'anonymous';
    img.onload = () => setMapImg(img);
    img.src = `${apiUrl}/map/image?map_name=${encodeURIComponent(selectedMap)}&type=map&t=${Date.now()}`;
  }, [apiUrl, selectedMap]);

  // ---- fit on load ----
  useEffect(() => {
    if (!mapImg || !containerRef.current) return;
    const c = containerRef.current;
    const s = Math.min(c.clientWidth / mapImg.width, c.clientHeight / mapImg.height, 1);
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

  // ---- 座標変換(回転なしの簡易版。単位: ピクセル<->world[m]) ----
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

  const screenToPx = useCallback((clientX: number, clientY: number) => {
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    const sx = clientX - rect.left, sy = clientY - rect.top;
    if (!mapImg) return { px: 0, py: 0 };
    return { px: (sx - pan.x) / scale, py: (sy - pan.y) / scale };
  }, [mapImg, pan, scale]);

  // ---- 描画 ----
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !mapImg) return;
    const ctx = canvas.getContext('2d')!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    ctx.translate(pan.x, pan.y);
    ctx.scale(scale, scale);
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
        ctx.stroke();
        ctx.font = `bold ${12 / scale}px sans-serif`;
        ctx.fillStyle = color;
        ctx.fillText(nicknameForRobot(name), px + r + 4 / scale, py - r);
        ctx.globalAlpha = 1;
      }
    }
    ctx.restore();
  }, [mapImg, scale, pan, fleet, targetPoint, selectedMap, worldToPx]);

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

  // ---- マウス操作(左クリック=目標地点セット、中クリック/ドラッグ=パン、ホイール=ズーム) ----
  const onMouseDown = (e: React.MouseEvent) => {
    if (e.button === 1 || (e.button === 0 && e.altKey)) {
      panStart.current = { mx: e.clientX, my: e.clientY, px: pan.x, py: pan.y }; return;
    }
    if (e.button !== 0 || !mapImg) return;
    const { px, py } = screenToPx(e.clientX, e.clientY);
    setTargetPoint(pxToWorld(px, py));
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (!panStart.current) return;
    setPan({ x: panStart.current.px + e.clientX - panStart.current.mx, y: panStart.current.py + e.clientY - panStart.current.my });
  };
  const onMouseUp = () => { panStart.current = null; };
  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const f = e.deltaY < 0 ? 1.1 : 0.9;
    const rect = canvasRef.current!.getBoundingClientRect();
    const cx = e.clientX - rect.left, cy = e.clientY - rect.top;
    setScale(s => {
      const ns = Math.max(0.1, Math.min(10, s * f));
      setPan(p => ({ x: cx - (cx - p.x) * (ns / s), y: cy - (cy - p.y) * (ns / s) }));
      return ns;
    });
  };

  // ---- コマンド送信 ----
  const sendMoveToPose = async (robotName: string, x: number, y: number, yaw: number) => {
    const res = await fetch(`${apiUrl}/fleet/command`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ robot_name: robotName, method: 'move_to_pose', args: { x, y, yaw, map_name: selectedMap } }),
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

  // ---- 追いかけっこモード ----
  const chaseTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const fleetRef = useRef(fleet);
  fleetRef.current = fleet;
  const chaserRef = useRef(chaser); chaserRef.current = chaser;
  const chaseTargetRef = useRef(chaseTarget); chaseTargetRef.current = chaseTarget;
  const mapRef = useRef(selectedMap); mapRef.current = selectedMap;

  const stopChase = useCallback(() => {
    if (chaseTimer.current) { clearInterval(chaseTimer.current); chaseTimer.current = null; }
    setChasing(false);
  }, []);

  const startChase = () => {
    if (!chaser || !chaseTarget || chaser === chaseTarget) return;
    setChasing(true);
    const tick = async () => {
      const f = fleetRef.current;
      const chaserRobot = f?.robots[chaserRef.current];
      const targetRobot = f?.robots[chaseTargetRef.current];
      if (!targetRobot?.pose || !targetRobot.online) return;
      const cp = chaserRobot?.pose;
      const yaw = cp ? Math.atan2(targetRobot.pose.y - cp.y, targetRobot.pose.x - cp.x) : targetRobot.pose.yaw;
      await sendMoveToPose(chaserRef.current, targetRobot.pose.x, targetRobot.pose.y, yaw);
    };
    tick();
    chaseTimer.current = setInterval(tick, CHASE_PERIOD_MS);
  };

  useEffect(() => () => { if (chaseTimer.current) clearInterval(chaseTimer.current); }, []);

  const allRobotNames = Object.keys(fleet?.robots ?? {}).sort();
  const offMapRobots = Object.entries(fleet?.robots ?? {}).filter(([, r]) => r.map_name !== selectedMap);

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
        <div ref={containerRef} style={{ position: 'absolute', inset: 0 }}>
          <canvas ref={canvasRef}
            style={{ width: '100%', height: '100%', cursor: 'crosshair' }}
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
            <select value={chaser} onChange={e => setChaser(e.target.value)} disabled={chasing} style={selectStyle}>
              <option value="">選択してください</option>
              {allRobotNames.map(n => <option key={n} value={n}>{nicknameForRobot(n)}</option>)}
            </select>
            <label style={{ fontSize: 11, color: 'var(--t-text-dim)' }}>追いかけられる側(target)</label>
            <select value={chaseTarget} onChange={e => setChaseTarget(e.target.value)} disabled={chasing} style={selectStyle}>
              <option value="">選択してください</option>
              {allRobotNames.filter(n => n !== chaser).map(n => <option key={n} value={n}>{nicknameForRobot(n)}</option>)}
            </select>
            {!chasing ? (
              <button onClick={startChase} disabled={!chaser || !chaseTarget} style={{
                marginTop: 4, padding: '8px 0', borderRadius: 10, border: 'none',
                cursor: chaser && chaseTarget ? 'pointer' : 'not-allowed',
                background: 'var(--t-accent)', color: '#fff', fontSize: 13,
                opacity: chaser && chaseTarget ? 1 : 0.5,
              }}>開始</button>
            ) : (
              <button onClick={stopChase} style={{
                marginTop: 4, padding: '8px 0', borderRadius: 10, border: 'none', cursor: 'pointer',
                background: '#cc3333', color: '#fff', fontSize: 13,
              }}>停止</button>
            )}
            {chasing && (
              <div style={{ fontSize: 11, color: 'var(--t-text-dim)' }}>
                {CHASE_PERIOD_MS / 1000}秒ごとに{nicknameForRobot(chaseTarget)}の現在地へ{nicknameForRobot(chaser)}を向かわせています
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
