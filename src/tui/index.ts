import Table from "cli-table3";
import chalk from "chalk";
import { type KV6Update, KV6MessageType } from "@/types/kv6";
import eventBus, { EventName } from "@/core/event-bus";
import vehicleState from "./state";

export class TUI {
  private updateInterval: NodeJS.Timeout;
  private cleanupInterval: NodeJS.Timeout;

  constructor() {
    // Subscribe to vehicle updates
    eventBus.on(EventName.KV6_UPDATE, this.handleVehicleUpdate.bind(this));

    // Update the UI every 2 seconds
    this.updateInterval = setInterval(() => {
      this.renderTable();
    }, 2000);

    // Clean up stale vehicles every 5 minutes
    this.cleanupInterval = setInterval(
      () => {
        vehicleState.cleanupStaleVehicles(30); // Remove vehicles older than 30 minutes
      },
      5 * 60 * 1000
    );
  }

  /**
   * Handle a vehicle update from the event bus
   */
  private handleVehicleUpdate(update: KV6Update): void {
    vehicleState.updateVehicle(update);
  }

  /**
   * Render the vehicle table
   */
  private renderTable(): void {
    try {
      // Clear console
      console.clear();

      // Display time and user info at the top
      console.log(
        `Current Date and Time (UTC - YYYY-MM-DD HH:MM:SS formatted): ${this.getCurrentTimeFormatted()}`
      );
      console.log();

      // Get vehicle data
      const vehicles = vehicleState.getAllVehicles();
      const counts = vehicleState.getStatusCounts();

      // Print status line
      const activeCount = counts.active || 0;
      const totalCount = counts.total || 0;
      const arrivalCount = counts[KV6MessageType.ARRIVAL] || 0;
      const initCount = counts[KV6MessageType.INIT] || 0;
      const departureCount = counts[KV6MessageType.DEPARTURE] || 0;

      console.log(
        ` Active Vehicles (${activeCount} of ${totalCount}) | A:${arrivalCount} I:${initCount} D:${departureCount}`
      );

      // Create table
      const table = new Table({
        head: [
          "Vehicle",
          "Line",
          "Status",
          "Stop",
          "Occupancy",
          "Position",
          "Updated",
        ],
        style: {
          head: [], // No style for head
          border: [], // No style for border
        },
        chars: {
          top: "━",
          "top-mid": "┳",
          "top-left": "┏",
          "top-right": "┓",
          bottom: "━",
          "bottom-mid": "┻",
          "bottom-left": "┗",
          "bottom-right": "┛",
          left: "┃",
          "left-mid": "┣",
          mid: "━",
          "mid-mid": "╋",
          right: "┃",
          "right-mid": "┫",
          middle: "┃",
        },
        colWidths: [20, 80, 20, 20, 30, 40, 20],
      });

      // Add vehicle rows (limit to 10 for now to avoid flooding the terminal)
      const displayVehicles = vehicles.slice(0, 10);
      for (const vehicle of displayVehicles) {
        table.push([
          vehicle.vehicleNumber,
          vehicle.lineName
            ? `${vehicle.lineNumber} - ${vehicle.lineName}`
            : vehicle.lineNumber,
          this.colorizeStatus(vehicle.status),
          vehicle.stopCode || "",
          this.formatOccupancy(vehicle.occupancy),
          vehicle.latitude
            ? `${vehicle.latitude.toFixed(5)}, ${vehicle.longitude?.toFixed(5)}`
            : "Unknown",
          this.formatTime(vehicle.lastUpdated),
        ]);
      }

      // Print table
      console.log(table.toString());
    } catch (error) {
      console.error("Error rendering table:", error);
    }
  }

  /**
   * Colorize status text
   */
  private colorizeStatus(status: KV6MessageType): string {
    switch (status) {
      case KV6MessageType.ARRIVAL:
        return chalk.green("ARRIVAL");
      case KV6MessageType.DEPARTURE:
        return chalk.red("DEPARTURE");
      case KV6MessageType.ONROUTE:
        return chalk.blue("ONROUTE");
      case KV6MessageType.ONSTOP:
        return chalk.yellow("ONSTOP");
      case KV6MessageType.INIT:
        return chalk.magenta("INIT");
      case KV6MessageType.END:
        return chalk.grey("END");
      case KV6MessageType.DELAY:
        return chalk.red.bold("DELAY");
      case KV6MessageType.OFFROUTE:
        return chalk.yellow.bold("OFFROUTE");
      case KV6MessageType.CANCEL:
        return chalk.red.bold("CANCEL");
      default:
        return String(status);
    }
  }

  /**
   * Format occupancy level with colors
   */
  private formatOccupancy(occupancy?: number): string {
    if (occupancy === undefined) {
      return "Unknown";
    }

    switch (occupancy) {
      case 0:
        return chalk.cyan("Empty");
      case 1:
        return chalk.cyan("Many Seats");
      case 2:
        return chalk.green("Seats Available");
      case 3:
        return chalk.yellow("Standing Room");
      case 4:
        return chalk.red("Limited Standing");
      case 5:
        return chalk.red.bold("Full");
      default:
        return "Unknown";
    }
  }

  /**
   * Format time as HH:MM:SS
   */
  private formatTime(date: Date): string {
    return date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  }

  /**
   * Get current time in YYYY-MM-DD HH:MM:SS format
   */
  private getCurrentTimeFormatted(): string {
    const now = new Date();
    const year = now.getUTCFullYear();
    const month = String(now.getUTCMonth() + 1).padStart(2, "0");
    const day = String(now.getUTCDate()).padStart(2, "0");
    const hours = String(now.getUTCHours()).padStart(2, "0");
    const minutes = String(now.getUTCMinutes()).padStart(2, "0");
    const seconds = String(now.getUTCSeconds()).padStart(2, "0");

    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
  }

  /**
   * Clean up resources when shutting down
   */
  cleanup(): void {
    clearInterval(this.updateInterval);
    clearInterval(this.cleanupInterval);
    console.log(chalk.yellow("Shutting down..."));
  }
}

// Export a factory function to create the TUI
export function createTUI(): TUI {
  return new TUI();
}

export default createTUI;
