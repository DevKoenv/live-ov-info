import { KV6MessageType, type KV6Update } from '@/types/kv6';
import { eventBus, EventName } from '@/core/event-bus';

/**
 * Represents a vehicle's current state
 */
export interface VehicleState {
  vehicleNumber: string;
  lineNumber: string;
  lineName?: string;
  status: KV6MessageType;
  stopCode?: string;
  stopName?: string;
  latitude?: number;
  longitude?: number;
  occupancy?: number;
  lastUpdated: Date;
  punctuality?: number;
}

/**
 * In-memory store for vehicle states
 */
export class VehicleStateManager {
  private vehicles: Map<string, VehicleState> = new Map();

  constructor() {
    eventBus.on(EventName.KV6_UPDATE, (update: KV6Update) => {
      this.updateVehicle(update);
    });
  }

  /**
   * Update vehicle state based on incoming KV6 message
   */
  updateVehicle(update: KV6Update): void {
    try {
      const { vehicleNumber } = update;
      
      // Safety check - skip updates with missing vehicle number
      if (!vehicleNumber) {
        return;
      }
      
      // Get existing state or create new
      const existingState = this.vehicles.get(vehicleNumber) || {
        vehicleNumber,
        lineNumber: update.lineNumber || 'Unknown',
        status: update.type,
        lastUpdated: update.timestamp
      };
      
      // Update state with new data
      const newState: VehicleState = {
        ...existingState,
        status: update.type,
        lastUpdated: update.timestamp,
        lineNumber: update.lineNumber || existingState.lineNumber,
        // Only update these if provided in the update
        ...(update.stopCode && { stopCode: update.stopCode }),
        ...(update.latitude && { latitude: update.latitude }),
        ...(update.longitude && { longitude: update.longitude }),
        ...(update.occupancy !== undefined && { occupancy: update.occupancy }),
        ...(update.punctuality !== undefined && { punctuality: update.punctuality }),
      };
      
      // Store updated state
      this.vehicles.set(vehicleNumber, newState);
    } catch (error) {
      console.error('Error updating vehicle state:', error);
    }
  }

  /**
   * Get all current vehicle states
   */
  getAllVehicles(): VehicleState[] {
    try {
      // Filter out any invalid entries and then sort
      return Array.from(this.vehicles.values())
        .filter(vehicle => vehicle && vehicle.vehicleNumber) // Safety check
        .sort((a, b) => {
          // Extra safety checks
          if (!a || !a.vehicleNumber) return 1;
          if (!b || !b.vehicleNumber) return -1;
          return a.vehicleNumber.localeCompare(b.vehicleNumber);
        });
    } catch (error) {
      console.error('Error getting vehicles:', error);
      return []; // Return empty array on error
    }
  }

  /**
   * Get the count of vehicles by status
   */
  getStatusCounts(): Record<string, number> {
    try {
      const counts: Record<string, number> = {
        total: this.vehicles.size,
        active: 0
      };
      
      for (const vehicle of this.vehicles.values()) {
        // Skip invalid entries
        if (!vehicle || !vehicle.status) continue;
        
        // Consider these statuses as "active"
        if ([
          KV6MessageType.ARRIVAL,
          KV6MessageType.DEPARTURE,
          KV6MessageType.ONROUTE,
          KV6MessageType.ONSTOP
        ].includes(vehicle.status)) {
          counts.active = (counts.active || 0) + 1;
        }
        
        // Count by status
        counts[vehicle.status] = (counts[vehicle.status] || 0) + 1;
      }
      
      return counts;
    } catch (error) {
      console.error('Error getting status counts:', error);
      return { total: 0, active: 0 }; // Return empty counts on error
    }
  }

  /**
   * Remove vehicles that haven't been updated in a while
   */
  cleanupStaleVehicles(maxAgeMinutes: number = 30): void {
    try {
      const now = new Date();
      
      for (const [vehicleNumber, state] of this.vehicles.entries()) {
        // Skip invalid entries
        if (!state || !state.lastUpdated) continue;
        
        const ageMinutes = (now.getTime() - state.lastUpdated.getTime()) / (1000 * 60);
        
        if (ageMinutes > maxAgeMinutes) {
          this.vehicles.delete(vehicleNumber);
        }
      }
    } catch (error) {
      console.error('Error cleaning up stale vehicles:', error);
    }
  }
}

// Export a singleton instance
export const vehicleState = new VehicleStateManager();
export default vehicleState;