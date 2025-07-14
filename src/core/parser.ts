import * as fs from "fs";
import * as xml2js from "xml2js";
import { type KV6Update, KV6MessageType } from "@/types/kv6";
import { convertRdToWgs84 } from "@/utils/coordinates";
import { normalizeKeys } from "@/utils/object";

export class KV6Parser {
  private xmlParser: xml2js.Parser;

  constructor() {
    this.xmlParser = new xml2js.Parser({
      explicitArray: false,
      mergeAttrs: true,
      explicitRoot: true,
      trim: true,
      attrNameProcessors: [(name) => name.toLowerCase()],
      tagNameProcessors: [(name) => name],
    });
  }

  /**
   * Parse KV6 XML content and return structured messages
   */
  async parseXml(
    xmlContent: string,
    operator: string = "ARR"
  ): Promise<KV6Update[]> {
    try {
      // Skip empty messages
      if (!xmlContent || xmlContent.trim() === "") {
        return [];
      }

      // Debug content in development mode
      if (process.env.NODE_ENV === "development") {
        const contentPreview =
          xmlContent.length > 200
            ? `${xmlContent.substring(0, 200)}...`
            : xmlContent;
        console.log(
          `Parsing XML (${xmlContent.length} bytes): ${contentPreview}`
        );
      }

      const parsed = await this.xmlParser.parseStringPromise(xmlContent);

      // Debug parsed structure in development mode
      if (process.env.NODE_ENV === "development") {
        console.log("Parsed XML structure keys:", Object.keys(parsed));
      }

      // Handle different possible XML structures
      let kv6 = null;

      if (parsed.VV_TM_PUSH?.KV6posinfo) {
        kv6 = parsed.VV_TM_PUSH.KV6posinfo;
      } else if (parsed.KV6posinfo) {
        kv6 = parsed.KV6posinfo;
      } else {
        // If in development mode, log the full parsed structure for debugging
        if (process.env.NODE_ENV === "development") {
          console.log("Parsed XML structure:", JSON.stringify(parsed, null, 2));
          console.log("No KV6posinfo found in parsed XML");
        }
        return [];
      }

      const results: KV6Update[] = [];

      // Process each message type
      for (const type of Object.values(KV6MessageType)) {
        if (kv6[type]) {
          // Handle both array and single object cases
          const messages = Array.isArray(kv6[type]) ? kv6[type] : [kv6[type]];

          for (const msg of messages) {
            const normalizedMsg = normalizeKeys(msg);
            results.push(
              this.normalizeMessage(
                normalizedMsg,
                type as KV6MessageType,
                operator
              )
            );
          }
        }
      }

      return results;
    } catch (error) {
      // Log more details about the error
      console.error("Error parsing KV6 XML:", error);

      // In development mode, log the raw XML that caused the error
      if (process.env.NODE_ENV === "development") {
        console.error("Raw XML content that caused error:");
        console.error(xmlContent.substring(0, 500) + "...");
      }

      return [];
    }
  }

  /**
   * Normalize raw message to consistent output format
   */
  private normalizeMessage(
    rawMessage: any,
    type: KV6MessageType,
    operator: string
  ): KV6Update {
    // Extract basic properties present in all message types
    const base = {
      operator: operator as "ARR",
      type,
      journeyNumber: rawMessage.journeynumber,
      vehicleNumber: rawMessage.vehiclenumber,
      lineNumber: rawMessage.lineplanningnumber,
      timestamp: new Date(rawMessage.timestamp),
      stopCode: rawMessage.userstopcode,
      punctuality: rawMessage.punctuality
        ? Number(rawMessage.punctuality)
        : undefined,
    };

    // Add position data if available
    if (rawMessage.rd_x !== undefined && rawMessage.rd_y !== undefined) {
      const position = convertRdToWgs84(
        Number(rawMessage.rd_x),
        Number(rawMessage.rd_y)
      );

      if ("error" in position) {
        console.error(
          `Invalid RD coordinates for vehicle ${rawMessage.vehiclenumber}:`,
          position.error.message
        );
        return base; // Return base without position if conversion fails
      }

      return {
        ...base,
        latitude: position.latitude,
        longitude: position.longitude,
        occupancy: rawMessage.occupancy
          ? Number(rawMessage.occupancy)
          : undefined,
      };
    }

    return base;
  }
}

// Export singleton instance
export const kv6Parser = new KV6Parser();
export default kv6Parser;
