import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import * as ROSLIB from 'roslib';
import { useRosTopic } from '../hooks/useRosTopic';
import type { LayerVisibility } from '../types/ros';
import type { MapPlace, MapRoomOverlay } from './MapView';
import { colorForRobot } from './RobotPicker';

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

interface OccupancyGrid {
  info: {
    resolution: number;
    width: number;
    height: number;
    origin: { position: { x: number; y: number; z: number } };
  };
  data: number[];
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
  places?: MapPlace[];
  rooms?: MapRoomOverlay[];
}

function quatToYaw(z: number, w: number) {
  return 2 * Math.atan2(z, w);
}

// ROS座標 → Three.js座標: ROS x(前方)→Three x, ROS y(左)→Three -z
function rosToThree(rx: number, ry: number): [number, number] {
  return [rx, -ry];
}

export function MapView3D({ ros, namespace, layers, width, height, places, rooms }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const scanPointsRef = useRef<THREE.Points | null>(null);
  const peopleGroupRef = useRef<THREE.Group | null>(null);
  const doaArrowRef = useRef<THREE.ArrowHelper | null>(null);
  const mapMeshRef = useRef<THREE.Mesh | null>(null);
  const poiGroupRef = useRef<THREE.Group | null>(null);
  const bodyMaterialsRef = useRef<THREE.MeshBasicMaterial[] | null>(null);
  const frameRef = useRef<number>(0);

  // 各購読にthrottle_rate/queue_length(ms/件)を指定してrosbridgeの負荷を抑える。
  // queue_length:1で古いフレームを溜めず常に最新のみ受信
  const scan = useRosTopic<LaserScan>(ros, `/${namespace}/scan`, 'sensor_msgs/LaserScan', layers.lidar,
    { throttleRate: 300, queueLength: 1 });
  const markers = useRosTopic<MarkerArray>(ros, '/object_detection/laser/marker', 'visualization_msgs/MarkerArray', layers.people,
    { queueLength: 1 });
  const doa = useRosTopic<PoseStamped>(ros, `/${namespace}/doa`, 'geometry_msgs/PoseStamped', layers.doa,
    { queueLength: 1 });
  const mapGrid = useRosTopic<OccupancyGrid>(ros, `/${namespace}/navigation/map`, 'nav_msgs/OccupancyGrid', layers.map,
    { queueLength: 1 }); // latched・低頻度なのでthrottle不要

  // シーン初期化
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1a2e);
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(55, width / height, 0.1, 200);
    camera.position.set(0, 6, 6);
    camera.lookAt(0, 0, 0);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.1;
    controls.maxPolarAngle = Math.PI / 2;
    controlsRef.current = controls;

    // グリッド (1m間隔, 20m範囲)
    const grid = new THREE.GridHelper(20, 20, 0x333366, 0x222244);
    scene.add(grid);
    const gridMain = new THREE.GridHelper(20, 2, 0x4444aa, 0x4444aa);
    scene.add(gridMain);

    // ロボット本体 (22cm四方のキューブ)
    const robotGroup = new THREE.Group();

    // 本体ボックス: 各面に色を付けるため面ごとにマテリアルを設定
    // BoxGeometry面の順: +x(前), -x(後), +y(上), -y(下), +z(右), -z(左)
    // 前面(白)は識別用の固定色。それ以外はロボット個体色(colorForRobot)からのバリエーション。
    // namespace変更時はこの配列を直接書き換える(下の namespace 用useEffect参照)
    const base = new THREE.Color(colorForRobot(namespace));
    const boxMaterials = [
      new THREE.MeshBasicMaterial({ color: 0xffffff }), // 前面(+x): 白
      new THREE.MeshBasicMaterial({ color: base.clone() }), // 後面
      new THREE.MeshBasicMaterial({ color: base.clone().offsetHSL(0, 0, 0.12) }), // 上面(明るめ)
      new THREE.MeshBasicMaterial({ color: base.clone().offsetHSL(0, 0, -0.15) }), // 下面(暗め)
      new THREE.MeshBasicMaterial({ color: base.clone() }), // 右面
      new THREE.MeshBasicMaterial({ color: base.clone() }), // 左面
    ];
    bodyMaterialsRef.current = boxMaterials;
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.22, 0.22), boxMaterials);
    body.position.y = 0.11;
    robotGroup.add(body);

    // 前方ノーズ: 前方(+x)に突き出た三角錐
    const noseMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const nose = new THREE.Mesh(new THREE.ConeGeometry(0.07, 0.18, 4), noseMat);
    nose.rotation.z = -Math.PI / 2; // x軸方向に向ける
    nose.rotation.y = Math.PI / 4;  // 四角錐の向きを整える
    nose.position.set(0.19, 0.11, 0);
    robotGroup.add(nose);

    // 上部の前方方向ライン (地面からでも見えるよう高めに)
    const fwdArrow = new THREE.ArrowHelper(
      new THREE.Vector3(1, 0, 0),
      new THREE.Vector3(0, 0.26, 0),
      0.55, 0xffffff, 0.18, 0.12
    );
    robotGroup.add(fwdArrow);

    scene.add(robotGroup);

    // 人グループ
    const peopleGroup = new THREE.Group();
    peopleGroupRef.current = peopleGroup;
    scene.add(peopleGroup);

    // LiDAR点群
    const scanGeo = new THREE.BufferGeometry();
    const scanMat = new THREE.PointsMaterial({ color: 0x00ff88, size: 0.06 });
    const scanPoints = new THREE.Points(scanGeo, scanMat);
    scanPointsRef.current = scanPoints;
    scene.add(scanPoints);

    // POI(places/rooms)グループ
    const poiGroup = new THREE.Group();
    poiGroupRef.current = poiGroup;
    scene.add(poiGroup);

    const animate = () => {
      frameRef.current = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(frameRef.current);
      controls.dispose();
      renderer.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, []);

  // リサイズ対応
  useEffect(() => {
    const renderer = rendererRef.current;
    const camera = cameraRef.current;
    if (!renderer || !camera) return;
    renderer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }, [width, height]);

  // LiDAR点群更新
  useEffect(() => {
    const pts = scanPointsRef.current;
    if (!pts) return;
    if (!scan || !layers.lidar) {
      pts.geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(0), 3));
      return;
    }
    const positions: number[] = [];
    scan.ranges.forEach((r, i) => {
      if (r === 0 || r > scan.range_max) return;
      const angle = scan.angle_min + i * scan.angle_increment;
      const [tx, tz] = rosToThree(r * Math.cos(angle), r * Math.sin(angle));
      positions.push(tx, 0.05, tz);
    });
    pts.geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(positions), 3));
  }, [scan, layers.lidar]);

  // 人マーカー更新
  useEffect(() => {
    const group = peopleGroupRef.current;
    if (!group) return;
    group.clear();
    if (!markers || !layers.people) return;

    const bodyMat = new THREE.MeshBasicMaterial({ color: 0xff4444, transparent: true, opacity: 0.75 });
    const headMat = new THREE.MeshBasicMaterial({ color: 0xff4444 });

    markers.markers.filter((m) => m.ns === 'PEOPLE').forEach((m) => {
      const [tx, tz] = rosToThree(m.pose.position.x, m.pose.position.y);
      const person = new THREE.Group();
      const torso = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.1, 0.9, 10), bodyMat);
      torso.position.y = 0.45;
      person.add(torso);
      const head = new THREE.Mesh(new THREE.SphereGeometry(0.14, 10, 8), headMat);
      head.position.y = 1.1;
      person.add(head);
      // 足元の輪
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(0.2, 0.03, 6, 20),
        new THREE.MeshBasicMaterial({ color: 0xff4444, transparent: true, opacity: 0.5 })
      );
      ring.rotation.x = Math.PI / 2;
      ring.position.y = 0.01;
      person.add(ring);
      person.position.set(tx, 0, tz);
      group.add(person);
    });
  }, [markers, layers.people]);

  // DOA矢印更新
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    if (doaArrowRef.current) {
      scene.remove(doaArrowRef.current);
      doaArrowRef.current = null;
    }
    if (!doa || !layers.doa) return;
    const yaw = quatToYaw(doa.pose.orientation.z, doa.pose.orientation.w);
    const [dx, dz] = rosToThree(Math.cos(yaw), Math.sin(yaw));
    const dir = new THREE.Vector3(dx, 0, dz).normalize();
    const arrow = new THREE.ArrowHelper(dir, new THREE.Vector3(0, 0.15, 0), 1, 0xffcc00, 0.2, 0.15);
    doaArrowRef.current = arrow;
    scene.add(arrow);
  }, [doa, layers.doa]);

  // マップ画像(occupancy grid)更新: セルデータからcanvasテクスチャを作り、床面に平面メッシュとして貼る
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    if (mapMeshRef.current) {
      scene.remove(mapMeshRef.current);
      mapMeshRef.current.geometry.dispose();
      const mat = mapMeshRef.current.material as THREE.MeshBasicMaterial;
      mat.map?.dispose();
      mat.dispose();
      mapMeshRef.current = null;
    }
    if (!mapGrid || !layers.map) return;

    const { resolution: res, width: mw, height: mh, origin } = mapGrid.info;
    if (mw === 0 || mh === 0) return;

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

    const texture = new THREE.CanvasTexture(offscreen);
    texture.needsUpdate = true;

    const planeWidth = mw * res;
    const planeHeight = mh * res;
    const geometry = new THREE.PlaneGeometry(planeWidth, planeHeight);
    const material = new THREE.MeshBasicMaterial({ map: texture, transparent: true, depthWrite: false });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.rotation.x = -Math.PI / 2;

    // origin.position はマップ左下(ROS座標)。平面中心はそこからセル解像度×幅/高さの半分だけ+方向にずれる
    const centerRx = origin.position.x + planeWidth / 2;
    const centerRy = origin.position.y + planeHeight / 2;
    const [tx, tz] = rosToThree(centerRx, centerRy);
    mesh.position.set(tx, -0.01, tz);

    scene.add(mesh);
    mapMeshRef.current = mesh;
  }, [mapGrid, layers.map]);

  // POI(places/rooms)更新
  useEffect(() => {
    const group = poiGroupRef.current;
    if (!group) return;
    group.clear();

    if (places) {
      places.forEach((place) => {
        const color = new THREE.Color(CAT_COLORS[place.category] || '#ffffff');
        const marker = new THREE.Mesh(
          new THREE.SphereGeometry(0.05, 12, 8),
          new THREE.MeshBasicMaterial({ color })
        );
        const [tx, tz] = rosToThree(place.x, place.y);
        marker.position.set(tx, 0.1, tz);
        group.add(marker);
      });
    }

    if (rooms) {
      rooms.forEach((room, idx) => {
        if (!room.points || room.points.length < 3) return;
        const color = new THREE.Color(ROOM_COLORS[idx % ROOM_COLORS.length]);
        const points = room.points.map(([rx, ry]) => {
          const [tx, tz] = rosToThree(rx, ry);
          return new THREE.Vector3(tx, 0.02, tz);
        });
        points.push(points[0].clone()); // 輪郭を閉じる
        const geometry = new THREE.BufferGeometry().setFromPoints(points);
        const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({ color }));
        group.add(line);
      });
    }
  }, [places, rooms]);

  // ロボット個体色更新: namespace(ロボット切り替え)に追従。シーン全体は再構築せずマテリアルのみ書き換える
  useEffect(() => {
    const mats = bodyMaterialsRef.current;
    if (!mats) return;
    const base = new THREE.Color(colorForRobot(namespace));
    // mats[0](前面)は識別用の白固定なのでそのまま
    mats[1].color.copy(base);                                  // 後面
    mats[2].color.copy(base).offsetHSL(0, 0, 0.12);             // 上面(明るめ)
    mats[3].color.copy(base).offsetHSL(0, 0, -0.15);            // 下面(暗め)
    mats[4].color.copy(base);                                  // 右面
    mats[5].color.copy(base);                                  // 左面
  }, [namespace]);

  const handleReset = () => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) return;
    camera.position.set(0, 6, 6);
    camera.lookAt(0, 0, 0);
    controls.target.set(0, 0, 0);
    controls.reset();
  };

  return (
    <div ref={containerRef} style={{ position: 'relative', width, height, borderRadius: 8, overflow: 'hidden' }}>
      <button
        onClick={handleReset}
        style={{
          position: 'absolute', bottom: 8, right: 8, zIndex: 10,
          padding: '4px 10px', borderRadius: 12, border: 'none',
          background: 'rgba(255,255,255,0.15)', color: '#fff', fontSize: 12, cursor: 'pointer',
        }}
      >
        リセット
      </button>
    </div>
  );
}
