import express from "express";
import cors from "cors";
import { vehicleState } from "@/tui/state";
import { type KV6Update } from "@/types/kv6";
import eventBus, { EventName } from "@/core/event-bus";
import path from "path";

export class APIServer {
  private app: express.Application;
  private server: any;
  private sseClients: Set<express.Response> = new Set();
  private statusInterval?: NodeJS.Timeout;

  constructor(private port: number = 3000) {
    this.app = express();
    this.setupMiddleware();
    this.setupRoutes();
    this.setupSSE();
  }

  private setupMiddleware(): void {
    this.app.use(cors());
    this.app.use(express.json());

    // Add request logging
    this.app.use((req, res, next) => {
      if (process.env.NODE_ENV !== "production") {
        console.log(`${req.method} ${req.path}`);
      }
      next();
    });
  }

  private setupRoutes(): void {
    // Root endpoint
    this.app.get("/", (req, res) => {
      // show a simple HTML page with links to API and SSE via an external html file
      res.sendFile(path.join(import.meta.dirname, "index.html"));
    });

    // Health check endpoint
    this.app.get("/health", (req, res) => {
      res.json({
        status: "ok",
        timestamp: new Date().toISOString(),
        uptime: process.uptime(),
      });
    });

    // Get all vehicles
    this.app.get("/api/vehicles", (req, res) => {
      try {
        const vehicles = vehicleState.getAllVehicles();
        res.json({
          vehicles,
          total: vehicles.length,
          timestamp: new Date().toISOString(),
        });
      } catch (error) {
        console.error("Error fetching vehicles:", error);
        res.status(500).json({ error: "Internal server error" });
      }
    });

    // Get vehicle by number
    this.app.get("/api/vehicles/:vehicleNumber", (req, res) => {
      try {
        const { vehicleNumber } = req.params;
        const vehicles = vehicleState.getAllVehicles();
        const vehicle = vehicles.find((v) => v.vehicleNumber === vehicleNumber);

        if (!vehicle) {
          return res.status(404).json({ error: "Vehicle not found" });
        }

        res.json({
          vehicle,
          timestamp: new Date().toISOString(),
        });
      } catch (error) {
        console.error("Error fetching vehicle:", error);
        res.status(500).json({ error: "Internal server error" });
      }
    });

    // Get vehicles by line
    this.app.get("/api/lines/:lineNumber/vehicles", (req, res) => {
      try {
        const { lineNumber } = req.params;
        const vehicles = vehicleState.getAllVehicles();
        const lineVehicles = vehicles.filter(
          (v) => v.lineNumber === lineNumber
        );

        res.json({
          lineNumber,
          vehicles: lineVehicles,
          total: lineVehicles.length,
          timestamp: new Date().toISOString(),
        });
      } catch (error) {
        console.error("Error fetching line vehicles:", error);
        res.status(500).json({ error: "Internal server error" });
      }
    });

    // Get status counts
    this.app.get("/api/status", (req, res) => {
      try {
        const counts = vehicleState.getStatusCounts();
        res.json({
          counts,
          timestamp: new Date().toISOString(),
        });
      } catch (error) {
        console.error("Error fetching status:", error);
        res.status(500).json({ error: "Internal server error" });
      }
    });

    // Server-Sent Events endpoint
    this.app.get("/api/stream", (req, res) => {
      // Set SSE headers
      res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Cache-Control",
      });

      // Add client to the set
      this.sseClients.add(res);

      // Send initial data
      this.sendSSEMessage(res, {
        type: "connected",
        data: {
          message: "Connected to live vehicle updates",
          timestamp: new Date().toISOString(),
        },
      });

      // Send current vehicle data
      const vehicles = vehicleState.getAllVehicles();
      this.sendSSEMessage(res, {
        type: "initial_data",
        data: {
          vehicles,
          counts: vehicleState.getStatusCounts(),
          timestamp: new Date().toISOString(),
        },
      });

      // Handle client disconnect
      req.on("close", () => {
        this.sseClients.delete(res);
      });

      req.on("aborted", () => {
        this.sseClients.delete(res);
      });
    });

    // 404 handler
    this.app.use("*", (req, res) => {
      res.status(404).json({ error: "Endpoint not found" });
    });
  }

  private setupSSE(): void {
    // Listen for KV6 updates and broadcast to SSE clients
    eventBus.on(EventName.KV6_UPDATE, (update: KV6Update) => {
      this.broadcastSSE({
        type: "vehicle_update",
        data: {
          update,
          timestamp: new Date().toISOString(),
        },
      });
    });

    // Listen for connection status changes
    eventBus.on(EventName.CONNECTION_STATUS, (status) => {
      this.broadcastSSE({
        type: "connection_status",
        data: {
          status,
          timestamp: new Date().toISOString(),
        },
      });
    });

    // Send periodic status updates
    const statusInterval = setInterval(() => {
      const counts = vehicleState.getStatusCounts();
      this.broadcastSSE({
        type: "status_update",
        data: {
          counts,
          timestamp: new Date().toISOString(),
        },
      });
    }, 30000); // Every 30 seconds

    // Store interval for cleanup
    this.statusInterval = statusInterval;
  }

  private sendSSEMessage(res: express.Response, message: any): void {
    try {
      // Send with both event type and data
      if (message.type) {
        res.write(`event: ${message.type}\n`);
      }
      res.write(`data: ${JSON.stringify(message.data)}\n\n`);
    } catch (error) {
      console.error("Error sending SSE message:", error);
      this.sseClients.delete(res);
    }
  }

  private broadcastSSE(message: any): void {
    if (this.sseClients.size === 0) {
      return;
    }

    const disconnectedClients: express.Response[] = [];

    for (const client of this.sseClients) {
      try {
        // Send with proper event type
        if (message.type) {
          client.write(`event: ${message.type}\n`);
        }
        client.write(`data: ${JSON.stringify(message.data)}\n\n`);
      } catch (error) {
        console.error("Error sending SSE message to client:", error);
        disconnectedClients.push(client);
      }
    }

    // Clean up disconnected clients
    for (const client of disconnectedClients) {
      this.sseClients.delete(client);
    }
  }

  public start(): Promise<void> {
    return new Promise((resolve) => {
      this.server = this.app.listen(this.port, () => {
        console.log(`API server running on http://localhost:${this.port}`);
        console.log(
          `SSE stream available at http://localhost:${this.port}/api/stream`
        );
        resolve();
      });
    });
  }

  public stop(): Promise<void> {
    return new Promise((resolve) => {
      // Clear the status interval
      if (this.statusInterval) {
        clearInterval(this.statusInterval);
      }

      // Close all SSE client connections
      for (const client of this.sseClients) {
        try {
          client.end();
        } catch (error) {
          // Ignore errors on closing
        }
      }
      this.sseClients.clear();

      if (this.server) {
        this.server.close(() => {
          console.log("API server stopped");
          resolve();
        });
      } else {
        resolve();
      }
    });
  }

  public getClientCount(): number {
    return this.sseClients.size;
  }
}

export default APIServer;
