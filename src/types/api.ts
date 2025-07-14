import { type VehicleState } from '@/tui/state';
import { type KV6Update } from './kv6';

export interface APIResponse<T = any> {
  data?: T;
  error?: string;
  timestamp: string;
}

export interface VehiclesResponse extends APIResponse {
  vehicles: VehicleState[];
  total: number;
}

export interface VehicleResponse extends APIResponse {
  vehicle: VehicleState;
}

export interface LineVehiclesResponse extends APIResponse {
  lineNumber: string;
  vehicles: VehicleState[];
  total: number;
}

export interface StatusResponse extends APIResponse {
  counts: Record<string, number>;
}

export interface HealthResponse extends APIResponse {
  status: 'ok' | 'error';
  uptime: number;
}

// SSE Message types
export interface SSEMessage {
  type: 'connected' | 'vehicle_update' | 'status_update' | 'initial_data';
  data: any;
}

export interface ConnectedMessage extends SSEMessage {
  type: 'connected';
  data: {
    message: string;
    timestamp: string;
  };
}

export interface VehicleUpdateMessage extends SSEMessage {
  type: 'vehicle_update';
  data: {
    update: KV6Update;
    timestamp: string;
  };
}

export interface StatusUpdateMessage extends SSEMessage {
  type: 'status_update';
  data: {
    counts: Record<string, number>;
    timestamp: string;
  };
}

export interface InitialDataMessage extends SSEMessage {
  type: 'initial_data';
  data: {
    vehicles: VehicleState[];
    counts: Record<string, number>;
    timestamp: string;
  };
}