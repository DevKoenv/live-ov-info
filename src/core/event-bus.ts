import { EventEmitter } from "events";
import { type KV6Update } from "@/types/kv6";

/**
 * Event names used throughout the system
 */
export enum EventName {
  KV6_UPDATE = "kv6:update",
  CONNECTION_ERROR = "connection:error",
  CONNECTION_STATUS = "connection:status",
}

/**
 * Event types mapped to their payload types
 */
export interface EventMap {
  [EventName.KV6_UPDATE]: KV6Update;
  [EventName.CONNECTION_ERROR]: Error;
  [EventName.CONNECTION_STATUS]: {
    connected: boolean;
    topic: string;
  };
}

/**
 * Type-safe event emitter
 */
class TypedEventEmitter<T extends Record<string, any>> {
  private emitter = new EventEmitter();

  on<K extends keyof T>(event: K, listener: (data: T[K]) => void): this {
    this.emitter.on(event as string, listener);
    return this;
  }

  off<K extends keyof T>(event: K, listener: (data: T[K]) => void): this {
    this.emitter.off(event as string, listener);
    return this;
  }

  emit<K extends keyof T>(event: K, data: T[K]): boolean {
    return this.emitter.emit(event as string, data);
  }

  once<K extends keyof T>(event: K, listener: (data: T[K]) => void): this {
    this.emitter.once(event as string, listener);
    return this;
  }

  removeAllListeners<K extends keyof T>(event?: K): this {
    this.emitter.removeAllListeners(event as string);
    return this;
  }
}

// Create and export a singleton instance
export const eventBus = new TypedEventEmitter<EventMap>();
export default eventBus;
