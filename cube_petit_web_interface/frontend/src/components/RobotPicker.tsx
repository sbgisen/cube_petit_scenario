import { useEffect, useState } from 'react';
import { Icon } from './Icon';

// Tier 2 "multi-robot picker": shows every robot currently visible on the
// zenoh fleet network (cube_petit_fleet_bridge, a separate ROS2 package in
// cube_petit_ros), aggregated by the backend's /fleet/robots endpoint (see
// cube_petit_web_interface/fleet_zenoh.py). Symmetric peer design: whichever
// robot's web interface you open, you see the same fleet-wide picture --
// there is no single "hub" instance. Purely additive to Tier 1 (host
// switching): clicking a card is just a shortcut that fills in the same
// `host` state App.tsx already manages.

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
  currentNamespace: string;
  onSelectRobot: (host: string) => void;
}

const POLL_MS = 2000;

export const ROBOT_COLOR: Record<string, string> = {
  orange: '#ff6600',
  pink: '#ff4da6',
  yellow: '#e6c200',
  purple: '#8855dd',
  green: '#2ecc71',
  blue: '#3498db',
};

export const ROBOT_NICKNAME: Record<string, string> = {
  orange: 'オレンジプチ',
  pink: 'ピンクプチ',
  yellow: 'イエロープチ',
  purple: 'パープルプチ',
  green: 'グリーンプチ',
  blue: 'ブループチ',
};

export function colorForRobot(name: string): string {
  const color = name.replace(/^cube_petit_/, '');
  return ROBOT_COLOR[color] ?? '#888888';
}

function batteryIconName(pct: number): string {
  if (pct >= 95) return 'battery_full';
  if (pct >= 80) return 'battery_6_bar';
  if (pct >= 60) return 'battery_5_bar';
  if (pct >= 40) return 'battery_4_bar';
  if (pct >= 20) return 'battery_3_bar';
  if (pct >= 10) return 'battery_2_bar';
  return 'battery_alert';
}

export function nicknameForRobot(namespace: string): string {
  const color = namespace.replace(/^cube_petit_/, '');
  return ROBOT_NICKNAME[color] ?? namespace;
}

/**
 * Derives the mDNS hostname the fleet_bridge/shared_controller zenoh launch
 * defaults assume for a robot name, e.g. 'cube_petit_pink' -> 'cube-petit-pink.local'
 * (matches cube_petit_fleet_bridge's `zenoh_router_endpoint` default naming
 * convention: 'tcp/cube-petit-orange.local:7447').
 */
function robotNameToHost(name: string): string {
  return `${name.replace(/_/g, '-')}.local`;
}

export function RobotPicker({ apiUrl, currentNamespace, onSelectRobot }: Props) {
  const [fleet, setFleet] = useState<FleetResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = () =>
      fetch(`${apiUrl}/fleet/robots`)
        .then(r => r.json())
        .then(d => { if (!cancelled) setFleet(d); })
        .catch(() => { if (!cancelled) setFleet(null); });
    poll();
    const t = setInterval(poll, POLL_MS);
    return () => { cancelled = true; clearInterval(t); };
  }, [apiUrl]);

  // Zenoh watcher not running (eclipse-zenoh not installed / router unreachable)
  // or no robot has published state yet: still render the drawer (the user opened
  // it on purpose), just show a friendly empty/unavailable state instead of a list.
  if (!fleet || !fleet.available) {
    return (
      <div style={{ padding: '16px 4px', fontSize: 13, color: 'var(--t-text-dim)' }}>
        フリート機能は利用できません(zenoh未接続)
      </div>
    );
  }
  const names = Object.keys(fleet.robots).sort();
  if (names.length === 0) {
    return (
      <div style={{ padding: '16px 4px', fontSize: 13, color: 'var(--t-text-dim)' }}>
        他の機体がまだ見つかっていません
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {names.map(name => {
        const robot = fleet.robots[name];
        const isCurrent = name === currentNamespace;
        const batteryPct = robot.battery != null ? Math.round(robot.battery * 100) : null;
        const label = name.replace(/^cube_petit_/, '');
        return (
          <button
            key={name}
            onClick={() => onSelectRobot(robotNameToHost(name))}
            title={robot.online
              ? `${name} - 最終更新 ${robot.last_seen_sec_ago}秒前`
              : `${name} - オフライン(最終更新 ${robot.last_seen_sec_ago}秒前)`}
            style={{
              display: 'flex', alignItems: 'center', gap: 10, width: '100%', textAlign: 'left',
              padding: '10px 14px', borderRadius: 12, cursor: 'pointer',
              border: isCurrent ? `2px solid ${colorForRobot(name)}` : '1px solid var(--t-border2)',
              background: isCurrent ? 'var(--t-surface2)' : 'var(--t-bg)',
              color: 'var(--t-text)', fontSize: 14,
              opacity: robot.online ? 1 : 0.45,
            }}
          >
            <div style={{
              width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
              background: robot.online ? colorForRobot(name) : '#555555',
              boxShadow: robot.online ? `0 0 4px ${colorForRobot(name)}88` : 'none',
            }} />
            <span style={{ flex: 1 }}>{nicknameForRobot(name)}</span>
            {batteryPct != null && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 2, color: 'var(--t-text-dim)', fontSize: 12 }} title="バッテリー残量">
                <Icon name={batteryIconName(batteryPct)} size={16} />
                {batteryPct}%
              </span>
            )}
            {robot.map_name && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 2, color: 'var(--t-text-dim)', fontSize: 12 }} title="使用中のマップ">
                <Icon name="map" size={16} />
                {robot.map_name}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
