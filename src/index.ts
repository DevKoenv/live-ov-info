import NDOVConnector from "@/core/connector";
import createTUI from "@/tui";

// Create topic and endpoint constants
const TOPIC = "/ARR/KV6posinfo";
const ENDPOINT = "tcp://pubsub.besteffort.ndovloket.nl:7658";

// Initialize the TUI
const tui = createTUI();

// Create and start the ZMQ connector
const connector = new NDOVConnector(TOPIC, ENDPOINT);
connector.connect().catch((error) => {
  console.error("Failed to start client:", error);
  process.exit(1);
});

// Handle process termination
process.on("SIGINT", async () => {
  tui.cleanup();
  await connector.disconnect();
  process.exit(0);
});

// Handle uncaught exceptions to prevent crashes
process.on("uncaughtException", (error) => {
  console.error("Uncaught exception:", error);
});

process.on("unhandledRejection", (reason, promise) => {
  console.error("Unhandled rejection at:", promise, "reason:", reason);
});
