export interface RobotConfig {
  name: string;
  namespace: string;
  rosbridgeUrl: string;
}

export interface LayerVisibility {
  lidar: boolean;
  map: boolean;
  costmap: boolean;
  plan: boolean;
  people: boolean;
  doa: boolean;
  camera: boolean;
}

export interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}
