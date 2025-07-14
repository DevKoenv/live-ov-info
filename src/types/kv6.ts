/**
 * KV6 message types according to BISON TMI8 specification
 */
export enum KV6MessageType {
  ARRIVAL = "ARRIVAL", // Vehicle arrived at stop
  DEPARTURE = "DEPARTURE", // Vehicle departed from stop
  ONROUTE = "ONROUTE", // Position update while en route
  ONSTOP = "ONSTOP", // Vehicle stationary at stop
  INIT = "INIT", // Journey initialization/start
  END = "END", // Journey termination/end
  DELAY = "DELAY", // Journey delayed
  OFFROUTE = "OFFROUTE", // Vehicle off route
  CANCEL = "CANCEL", // Journey cancelled
}

/**
 * Base interface for all KV6 messages
 */
export interface KV6BaseMessage {
  operator: "ARR"; // Arriva
  dataOwnerCode: string;
  lineplanningnumber: string;
  journeynumber: string;
  reinforcementnumber: number;
  timestamp: Date;
  vehiclenumber: string;
  source: string;
}

/**
 * Position-related messages (ARRIVAL, DEPARTURE, ONROUTE, ONSTOP)
 */
export interface KV6PositionMessage extends KV6BaseMessage {
  type:
    | KV6MessageType.ARRIVAL
    | KV6MessageType.DEPARTURE
    | KV6MessageType.ONROUTE
    | KV6MessageType.ONSTOP;
  userstopcode: string;
  passagesequencenumber: number;
  rd_x: number; // RD coordinate X
  rd_y: number; // RD coordinate Y
  punctuality?: number; // Seconds ahead/behind schedule
  occupancy?: number; // 0-6 occupancy level
}

/**
 * Journey state messages (INIT, END, DELAY, CANCEL, OFFROUTE)
 */
export interface KV6JourneyStateMessage extends KV6BaseMessage {
  type:
    | KV6MessageType.INIT
    | KV6MessageType.END
    | KV6MessageType.DELAY
    | KV6MessageType.CANCEL
    | KV6MessageType.OFFROUTE;
  userstopcode?: string;
  punctuality?: number;
}

/**
 * Union type for all KV6 messages
 */
export type KV6Message = KV6PositionMessage | KV6JourneyStateMessage;

/**
 * Normalized output message format for consumers
 */
export interface KV6Update {
  operator: "ARR";
  type: KV6MessageType;
  journeyNumber: string;
  vehicleNumber: string;
  lineNumber: string;
  timestamp: Date;
  stopCode?: string;
  latitude?: number;
  longitude?: number;
  punctuality?: number; // Seconds ahead/behind schedule
  occupancy?: number; // 0-6 occupancy level
}
