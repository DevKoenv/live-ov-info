import gzip
import binascii
import xmltodict
from datetime import datetime
import os
import base64
import json
from typing import Optional, Dict, Any, Tuple, List

from .models import Vehicle

def extract_xml_from_binary(binary_data):
    """Extract XML content from binary data with handling for compressed data"""
    # Check for gzip compression (magic bytes 1F 8B)
    if binary_data.startswith(b'\x1f\x8b'):
        try:
            # Decompress the gzip data
            decompressed = gzip.decompress(binary_data)
            # Look for XML content in the decompressed data
            text_data = decompressed.decode('utf-8', errors='replace')
            xml_start = text_data.find('<')
            if xml_start >= 0:
                return text_data[xml_start:]
        except Exception as e:
            print(f"Decompression error: {e}")
            pass
    
    # If not gzipped or decompression failed, try the normal approach
    try:
        text_data = binary_data.decode('utf-8', errors='replace')
        xml_start = text_data.find('<')
        if xml_start >= 0:
            return text_data[xml_start:]
    except Exception:
        pass
    
    # Last resort - look for XML start tag in binary
    xml_start_tag = b'<'
    xml_start = binary_data.find(xml_start_tag)
    if xml_start >= 0:
        try:
            return binary_data[xml_start:].decode('utf-8', errors='replace')
        except Exception:
            pass
    
    return None

def parse_kv6_message(xml_content: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse KV6 XML content into structured data with message statistics"""
    stats = {
        "parsed": False,
        "error": None,
        "message_type": "UNKNOWN",
        "message_count": 0,
        "unknown_types": []  # Track unknown message types
    }
    
    messages = []
    
    try:
        # Parse the XML message
        data = xmltodict.parse(xml_content)
        
        # Extract KV6posinfo
        if 'VV_TM_PUSH' in data and 'KV6posinfo' in data['VV_TM_PUSH']:
            kv6 = data['VV_TM_PUSH']['KV6posinfo']
            
            # Process different message types
            known_types = ['ARRIVAL', 'DEPARTURE', 'ONROUTE', 'ONSTOP']
            found_types = set(kv6.keys()) if isinstance(kv6, dict) else set()
            unknown_types = [t for t in found_types if t not in known_types]
            
            if unknown_types:
                stats["unknown_types"] = unknown_types
                # Don't print here - let the client handle the error reporting
            
            for msg_type in known_types:
                if msg_type in kv6:
                    stats["message_type"] = msg_type
                    msgs = kv6[msg_type]
                    if not isinstance(msgs, list):
                        msgs = [msgs]
                    
                    for msg in msgs:
                        # Add message type for reference
                        msg['_message_type'] = msg_type
                        messages.append(msg)
                        stats["message_count"] += 1
            
            stats["parsed"] = True
        
    except Exception as e:
        stats["error"] = str(e)
    
    return messages, stats

def save_debug_message(data, info_type="debug", extra_info=None):
    """Save messages for debugging with better binary handling"""
    debug_dir = "debug_messages"
    os.makedirs(debug_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Ensure we're working with binary data
    if isinstance(data, str):
        binary_data = data.encode('utf-8')
    else:
        binary_data = data
    
    # Save the raw binary data
    bin_filename = f"{debug_dir}/{info_type}_{timestamp}.bin"
    with open(bin_filename, "wb") as f:
        f.write(binary_data)
    
    # Save a text file with information about the message
    txt_filename = f"{debug_dir}/{info_type}_{timestamp}.txt"
    with open(txt_filename, "w", encoding="utf-8") as f:
        f.write(f"Type: {info_type}\n")
        if extra_info:
            f.write(f"Info: {extra_info}\n")
        f.write(f"Message length: {len(binary_data)} bytes\n")
        
        # Check if it's gzipped
        is_gzipped = binary_data.startswith(b'\x1f\x8b')
        f.write(f"Compression: {'GZIP' if is_gzipped else 'None'}\n")
        
        # Show hex representation safely
        f.write(f"First 100 bytes (hex): {binascii.hexlify(binary_data[:100]).decode('ascii')}\n")
        
        # Try to decompress if gzipped
        if is_gzipped:
            try:
                decompressed = gzip.decompress(binary_data)
                f.write(f"Decompressed size: {len(decompressed)} bytes\n")
                
                # Save decompressed data to a separate file
                decomp_filename = f"{debug_dir}/{info_type}_{timestamp}_decompressed.bin"
                with open(decomp_filename, "wb") as df:
                    df.write(decompressed)
                f.write(f"Decompressed data saved to: {decomp_filename}\n")
                
                # Show decompressed data as UTF-8
                try:
                    decoded = decompressed.decode('utf-8', errors='replace')
                    f.write(f"Decompressed as UTF-8: {decoded[:500]}\n")
                    
                    # Try to find XML content
                    xml_start = decoded.find('<')
                    if xml_start >= 0:
                        f.write(f"XML content starts at position {xml_start}\n")
                        f.write(f"XML preview: {decoded[xml_start:xml_start+200]}\n")
                except Exception as e:
                    f.write(f"Cannot decode decompressed data as UTF-8: {str(e)}\n")
            except Exception as e:
                f.write(f"Decompression failed: {str(e)}\n")
        
        # Try to show as UTF-8 string, but handle binary data gracefully
        try:
            decoded = binary_data.decode('utf-8', errors='replace')
            f.write(f"As UTF-8 (raw): {decoded[:500]}\n")
            
            # Try to find XML content
            xml_start = decoded.find('<')
            if xml_start >= 0 and not is_gzipped:
                f.write(f"XML content starts at position {xml_start}\n")
                f.write(f"XML preview: {decoded[xml_start:xml_start+200]}\n")
        except Exception as e:
            f.write(f"Cannot decode as UTF-8: {str(e)}\n")
        
        # Add base64 representation for complete data recovery
        f.write(f"\nBase64 encoded full message:\n{base64.b64encode(binary_data).decode('ascii')}")
    
    return bin_filename, txt_filename

def update_schema_model(xml_dict, schema_model=None):
    """Update a schema model with the structure of an XML dictionary"""
    if schema_model is None:
        schema_model = {}
    
    if not isinstance(xml_dict, dict):
        return {"_type": type(xml_dict).__name__, "_example": str(xml_dict)[:100]}
    
    for key, value in xml_dict.items():
        if key not in schema_model:
            if isinstance(value, dict):
                schema_model[key] = update_schema_model(value)
            elif isinstance(value, list):
                if value:
                    # For lists, we'll just document the first item's structure
                    schema_model[key] = [update_schema_model(value[0])]
                else:
                    schema_model[key] = []
            else:
                schema_model[key] = {"_type": type(value).__name__, "_example": str(value)[:100]}
    
    return schema_model

def save_schema_model(schema_model, filename):
    """Save the schema model to a JSON file"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(schema_model, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving schema model: {e}")
        return False

class MessageParser:
    """Parser for KV6 messages with schema discovery"""
    
    def __init__(self, debug=False, save_messages=False, transformer=None, references=None):
        self.debug = debug
        self.save_messages = save_messages
        self.transformer = transformer
        self.references = references  # Reference data manager
        self.messages_seen = 0
        self.valid_messages = 0
        self.message_types = set()
        
        # Schema discovery
        self.discovered_schemas = {}
        
        # Create debug directory if needed
        if self.save_messages:
            os.makedirs("debug_messages", exist_ok=True)
    
    def parse_message(self, topic, data):
        """Parse a message from a topic"""
        self.messages_seen += 1
        
        if self.debug:
            print(f"Message {self.messages_seen} from {topic}: {len(data)} bytes")
        
        # Save message for debugging if enabled
        if self.save_messages:
            save_debug_message(data, "message", extra_info=f"Topic: {topic}")
        
        # Extract XML from binary data
        xml_content = extract_xml_from_binary(data)
        if not xml_content:
            if self.debug:
                print(f"Could not extract XML from message")
            return []
        
        # Parse KV6 message
        messages, stats = parse_kv6_message(xml_content)
        
        if stats["parsed"]:
            self.valid_messages += len(messages)
            self.message_types.add(stats["message_type"])
            
            # Add topic information to each message for operator detection
            for msg in messages:
                msg['_topic'] = topic
            
            if self.debug:
                print(f"Parsed {len(messages)} {stats['message_type']} messages")
            
            # Update schema discovery
            if messages:
                self._update_schema_discovery(stats["message_type"], messages[0])
        
        return messages
    
    def create_vehicles(self, messages):
        """Create Vehicle objects from parsed messages and enrich with reference data"""
        vehicles = []
        
        for msg in messages:
            if self.transformer:
                vehicle = Vehicle.from_kv6_message(msg, self.transformer)
                if vehicle:
                    # Enrich with reference data if available
                    if self.references:
                        vehicle = self.references.enrich_vehicle(vehicle)
                    vehicles.append(vehicle)
        
        return vehicles
    
    def _update_schema_discovery(self, message_type, sample_message):
        """Update schema discovery with sample message"""
        if message_type not in self.discovered_schemas:
            self.discovered_schemas[message_type] = {}
        
        self.discovered_schemas[message_type] = update_schema_model(
            sample_message, 
            self.discovered_schemas[message_type]
        )
    
    def save_schemas(self, filename="discovered_schemas.json"):
        """Save discovered schemas to file"""
        return save_schema_model(self.discovered_schemas, filename)
    
    def get_stats(self):
        """Get parser statistics"""
        return {
            "messages_seen": self.messages_seen,
            "valid_messages": self.valid_messages,
            "message_types": list(self.message_types),
            "schema_count": len(self.discovered_schemas)
        }