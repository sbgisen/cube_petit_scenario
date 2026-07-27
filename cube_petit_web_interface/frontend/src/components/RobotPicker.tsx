import { useEffect, useState } from 'react';

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

const ROBOT_COLOR: Record<string, string> = {
  orange: '#ff6600',
  pink: '#ff4da6',
  yellow: '#e6c200',
  purple: '#8855dd',
  green: '#2ecc71',
  blue: '#3498db',
};

function colorForRobot(name: string): string {
  const color = name.replace(/^cube_petit_/, '');
  return ROBOT_COLOR[color] ?? '#888888';
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
  // or no robot has published state yet: hide the picker entirely so Tier 1
  // (single-robot operation via host switching) is unaffected.
  if (!fleet || !fleet.available) return null;
  const names = Object.keys(fleet.robots).sort();
  if (names.length === 0) return null;

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8, padding: '6px 16px', overflowX: 'auto',
      background: 'var(--t-surface)', borderBottom: '1px solid var(--t-border)', flexShrink: 0,
    }}>
      <span style={{ fontSize: 11, color: 'var(--t-text-dim)', flexShrink: 0 }}>フリート</span>
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
              display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0,
              padding: '5px 12px', borderRadius: 20, cursor: 'pointer',
              border: isCurrent ? `2px solid ${colorForRobot(name)}` : '1px solid var(--t-border2)',
              background: isCurrent ? 'var(--t-surface2)' : 'var(--t-bg)',
              color: 'var(--t-text)', fontSize: 12,
              opacity: robot.online ? 1 : 0.45,
            }}
          >
            <div style={{
              width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
              background: robot.online ? colorForRobot(name) : '#555555',
              boxShadow: robot.online ? `0 0 4px ${colorForRobot(name)}88` : 'none',
            }} />
            <span>{label}</span>
            {batteryPct != null && <span style={{ color: 'var(--t-text-dim)' }}>{batteryPct}%</span>}
            {robot.map_name && <span style={{ color: 'var(--t-text-dim)' }}>{robot.map_name}</span>}
          </button>
        );
      })}
    </div>
  );
}
