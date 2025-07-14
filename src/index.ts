import NDOVConnector from "@/core/connector";
import createTUI from "@/tui";
import APIServer from "@/api/server";

// Create topic and endpoint constants
const TOPIC = "/ARR/KV6posinfo";
const ENDPOINT = "tcp://pubsub.besteffort.ndovloket.nl:7658";

// Configuration
const API_PORT = parseInt(process.env.API_PORT || "3000");
const ENABLE_TUI = process.env.ENABLE_TUI !== "false";

async function main() {
  try {
    // Initialize the API server
    const apiServer = new APIServer(API_PORT);
    await apiServer.start();

    // Initialize the TUI (optional)
    let tui: any = null;
    if (ENABLE_TUI) {
      tui = createTUI();
    }

    // Create and start the ZMQ connector
    const connector = new NDOVConnector(TOPIC, ENDPOINT);
    await connector.connect();

    console.log('🚀 Live OV Info system started successfully!');
    console.log(`📡 Connected to: ${ENDPOINT}`);
    console.log(`🎯 Subscribed to: ${TOPIC}`);
    console.log(`🌐 API server: http://localhost:${API_PORT}`);
    console.log(`📊 Live stream: http://localhost:${API_PORT}/api/stream`);
    if (ENABLE_TUI) {
      console.log('🖥️  TUI enabled');
    }

    // Handle process termination
    const shutdown = async () => {
      console.log('\n🛑 Shutting down...');
      if (tui) {
        tui.cleanup();
      }
      await apiServer.stop();
      await connector.disconnect();
      process.exit(0);
    };

    process.on("SIGINT", shutdown);
    process.on("SIGTERM", shutdown);

  } catch (error) {
    console.error("❌ Failed to start system:", error);
    process.exit(1);
  }
}

// Handle uncaught exceptions to prevent crashes
process.on("uncaughtException", (error) => {
  console.error("Uncaught exception:", error);
});

process.on("unhandledRejection", (reason, promise) => {
  console.error("Unhandled rejection at:", promise, "reason:", reason);
});

// Start the application
main();
