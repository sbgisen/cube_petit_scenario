import { useCallback } from 'react';
import * as ROSLIB from 'roslib';

// rosbridge native send_action_goal (ROS2 compatible)
export function useRosAction(ros: ROSLIB.Ros | null, action: string, actionType: string) {
  return useCallback((args: object) => {
    if (!ros) return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (ros as any).callOnConnection({
      op: 'send_action_goal',
      action,
      action_type: actionType,
      args,
      feedback: false,
    });
  }, [ros, action, actionType]);
}
