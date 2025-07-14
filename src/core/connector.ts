import * as zmq from 'zeromq';
import * as zlib from 'zlib';
import * as util from 'util';
import eventBus, { EventName } from '@/core/event-bus';
import kv6Parser from '@/core/parser';

// Promisify zlib functions
const gunzipAsync = util.promisify(zlib.gunzip);
const inflateAsync = util.promisify(zlib.inflate);

export class NDOVConnector {
  private subscriber: zmq.Subscriber;
  private isConnected: boolean = false;
  private reconnectTimer?: NodeJS.Timeout;
  private topic: string;
  private endpoint: string;
  private operator: string;

  /**
   * Create a new NDOV ZMQ connector
   * @param topic ZMQ topic to subscribe to (e.g. '/ARR/KV6posinfo')
   * @param endpoint ZMQ endpoint URL
   */
  constructor(
    topic: string = '/ARR/KV6posinfo',
    endpoint: string = 'tcp://pubsub.besteffort.ndovloket.nl:7658',
  ) {
    this.subscriber = new zmq.Subscriber();
    this.topic = topic;
    this.endpoint = endpoint;
    
    // Extract operator from topic (e.g. 'ARR' from '/ARR/KV6posinfo')
    this.operator = topic.split('/')[1] || 'ARR';
  }

  /**
   * Connect to the NDOV ZMQ feed and start handling messages
   */
  async connect(): Promise<void> {
    try {
      await this.subscriber.connect(this.endpoint);
      await this.subscriber.subscribe(this.topic);
      
      this.isConnected = true;
      eventBus.emit(EventName.CONNECTION_STATUS, {
        connected: true,
        topic: this.topic
      });
      
      // Start message processing loop
      this.processMessages();
    } catch (error) {
      this.handleConnectionError(error as Error);
    }
  }

  /**
   * Disconnect from the ZMQ feed
   */
  async disconnect(): Promise<void> {
    try {
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
      }
      
      this.isConnected = false;
      await this.subscriber.disconnect(this.endpoint);
      
      eventBus.emit(EventName.CONNECTION_STATUS, {
        connected: false,
        topic: this.topic
      });
    } catch (error) {
      console.error('Error during disconnect:', error);
    }
  }

  /**
   * Try different methods to decode binary content to readable XML
   */
  private async decodeContent(buffer: Buffer): Promise<string> {
    try {
      // First few bytes can indicate the compression format
      const header = buffer.slice(0, 3);
      
      // Check for gzip magic number (1F 8B)
      if (header[0] === 0x1F && header[1] === 0x8B) {
        const decompressed = await gunzipAsync(buffer);
        return decompressed.toString('utf8');
      }
      
      // Check for zlib header (78 01, 78 9C, or 78 DA)
      if (header[0] === 0x78 && (header[1] === 0x01 || header[1] === 0x9C || header[1] === 0xDA)) {
        const decompressed = await inflateAsync(buffer);
        return decompressed.toString('utf8');
      }
      
      // Try to decompress with zlib anyway (some implementations don't use proper headers)
      try {
        const decompressed = await inflateAsync(buffer);
        // Check if result looks like XML
        if (decompressed.toString('utf8').includes('<?xml') || 
            decompressed.toString('utf8').includes('<VV_TM_PUSH') || 
            decompressed.toString('utf8').includes('<KV6posinfo')) {
          return decompressed.toString('utf8');
        }
      } catch (e) {
        // Ignore decompression errors and try other methods
      }
      
      // Try different encodings
      const encodings = ['utf8', 'latin1', 'ascii'] as const;
      for (const encoding of encodings) {
        const decoded = buffer.toString(encoding);
        // If it looks like XML, return it
        if (decoded.includes('<?xml') || decoded.includes('<VV_TM_PUSH') || decoded.includes('<KV6posinfo')) {
          return decoded;
        }
      }
      
      // Fallback to directly extracting XML-like content
      const latin1Str = buffer.toString('latin1');
      const xmlStartIndex = Math.max(
        latin1Str.indexOf('<?xml'),
        latin1Str.indexOf('<VV_TM_PUSH'),
        latin1Str.indexOf('<KV6posinfo')
      );
      
      if (xmlStartIndex >= 0) {
        return latin1Str.substring(xmlStartIndex);
      }
      
      // If all else fails, return latin1 encoding which won't throw on binary data
      return buffer.toString('latin1');
    } catch (error) {
      console.error('Error decoding message:', error);
      // Fall back to Latin1 which can represent any byte without throwing
      return buffer.toString('latin1');
    }
  }

  /**
   * Main message processing loop
   */
  private async processMessages(): Promise<void> {
    try {
      // Process messages as long as we're connected
      while (this.isConnected) {
        try {
          // Receive the multipart message
          const [topicBuffer, contentBuffer] = await this.subscriber.receive();
          
          // Convert topic buffer to string
          const topicStr = topicBuffer.toString('utf8');
          
          // Skip if topic doesn't match
          if (topicStr !== this.topic) {
            continue;
          }
          
          // Try to decode the binary content to XML
          const contentStr = await this.decodeContent(contentBuffer);
          
          // Parse the XML content
          const messages = await kv6Parser.parseXml(contentStr, this.operator);
          
          // Emit each parsed message
          for (const message of messages) {
            eventBus.emit(EventName.KV6_UPDATE, message);
          }
        } catch (innerError) {
          // Log message processing error but don't break the loop
          console.error('Error processing message:', innerError);
        }
      }
    } catch (error) {
      this.handleConnectionError(error as Error);
    }
  }

  /**
   * Handle connection errors and auto-reconnect
   */
  private handleConnectionError(error: Error): void {
    this.isConnected = false;
    console.error('ZMQ connection error:', error);
    
    eventBus.emit(EventName.CONNECTION_ERROR, error);
    eventBus.emit(EventName.CONNECTION_STATUS, {
      connected: false,
      topic: this.topic
    });
    
    // Attempt to reconnect after delay
    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, 5000); // 5 second reconnect delay
  }
}

// Export the connector class
export default NDOVConnector;