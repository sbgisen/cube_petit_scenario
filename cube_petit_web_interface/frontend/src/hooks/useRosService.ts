import { useRef } from 'react';
import * as ROSLIB from 'roslib';

export function useRosService(
  ros: ROSLIB.Ros | null,
  name: string,
  serviceType: string,
) {
  const serviceRef = useRef<ROSLIB.Service | null>(null);

  const call = (request: object): Promise<unknown> => {
    return new Promise((resolve, reject) => {
      if (!ros) return reject('ROS not connected');
      if (!serviceRef.current) {
        serviceRef.current = new ROSLIB.Service({ ros, name, serviceType });
      }
      serviceRef.current.callService(request, resolve, reject);
    });
  };

  return call;
}
