import zmq
import xmltodict
import pyproj
import time
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from datetime import datetime
import argparse
import collections
import os
import base64
import json
import binascii
import gzip

# BISON Occupancy levels mapping
OCCUPANCY_LEVELS = {
    "0": "Unknown",
    "1": "Empty",
    "2": "Many seats",
    "3": "Few seats",
    "4": "Standing only",
    "5": "Full",
    "6": "Not accepting passengers"
}

def parse_arguments():
    parser = argparse.ArgumentParser(description="Live Arriva Bus Information Terminal")
    parser.add_argument("--line", type=str, help="Filter by line number")
    parser.add_argument("--limit", type=int, default=20, help="Limit number of buses shown")
    parser.add_argument("--refresh", type=float, default=1.0, help="Refresh rate in seconds")
    parser.add_argument("--debug", action="store_true", help="Show debug messages for binary data")
    parser.add_argument("--topic", type=str, default="/ARR/KV6posinfo", help="ZeroMQ topic to subscribe to")
    parser.add_argument("--save-messages", action="store_true", help="Save all XML messages for analysis")
    parser.add_argument("--schema", action="store_true", help="Generate XML schema documentation (default: disabled)")
    parser.add_argument("--schema-file", type=str, default="xml_schema.json", help="File to save discovered XML schema")
    return parser.parse_args()

def create_display_layout():
    """Create a layout with areas for the table and error messages"""
    layout = Layout()
    layout.split(
        Layout(name="table"),
        Layout(name="errors", size=5)
    )
    return layout

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

def extract_xml_from_binary(binary_data):
    """Extract XML content from binary data with better handling for compressed data"""
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

def vehicle_info_getter(vehicles_dict):
    """Create a callback function to get vehicle info"""
    def get_vehicle_info(vehicle_id):
        return vehicles_dict.get(vehicle_id)
    return get_vehicle_info

def main():
    args = parse_arguments()
    
    # Setup ZeroMQ subscriber
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://pubsub.besteffort.ndovloket.nl:7658")
    
    # Try different subscription options
    topic = args.topic
    socket.setsockopt_string(zmq.SUBSCRIBE, topic)
    
    # Setup coordinate transformation (Dutch RD to WGS84)
    transformer = pyproj.Transformer.from_crs("EPSG:28992", "EPSG:4326", always_xy=True)
    
    # Setup rich console
    console = Console()
    console.print(f"[bold green]Connecting to NDOV Loket...[/bold green]")
    console.print(f"[bold blue]Subscribing to topic: {topic}[/bold blue]")
    console.print("[bold yellow]Waiting for bus position updates...[/bold yellow]")
    console.print("Press [bold red]Ctrl+C[/bold red] to exit")
    
    # Dictionary to store the latest positions of vehicles
    vehicles = {}
    
    # Keep track of recent errors (limited to last 5)
    recent_errors = collections.deque(maxlen=5)
    
    # Message statistics
    stats = {
        "xml_messages": 0,
        "binary_messages": 0,
        "invalid_xml": 0,
        "vehicle_updates": 0,
        "total_messages": 0
    }
    
    # Schema model to document XML structure (only if enabled)
    schema_model = {} if args.schema else None
    
    # Create layout for display
    layout = create_display_layout()
    
    # Directory for raw messages
    if args.save_messages or args.debug:
        raw_dir = "raw_messages"
        os.makedirs(raw_dir, exist_ok=True)
        debug_dir = "debug_messages"
        os.makedirs(debug_dir, exist_ok=True)
    
    try:
        # Create the live display
        with Live(layout, refresh_per_second=1/args.refresh, screen=True) as live:
            while True:
                try:
                    # Set a timeout for receiving messages
                    if socket.poll(100):
                        stats["total_messages"] += 1
                        
                        # Receive multipart message
                        message_parts = socket.recv_multipart()
                        
                        # Usually, first part is topic, second is body
                        topic = message_parts[0]
                        body = message_parts[1] if len(message_parts) > 1 else b''
                        
                        # Save raw message for analysis
                        if args.save_messages and stats["total_messages"] <= 20:
                            raw_filename = f"raw_messages/message_{stats['total_messages']}.bin"
                            with open(raw_filename, "wb") as f:
                                for part in message_parts:
                                    f.write(part)
                                    f.write(b'\n---PART---\n')
                        
                        # Save the first message for debugging
                        if args.save_messages and stats["total_messages"] == 1:
                            save_debug_message(body, "first_message", f"First message received, topic: {topic}")
                            
                        # Extract XML content from binary data
                        xml_content = extract_xml_from_binary(body)
                        
                        if xml_content:
                            stats["xml_messages"] += 1
                            
                            # Save example XML messages
                            if args.save_messages and stats["xml_messages"] <= 5:
                                save_debug_message(xml_content, "xml_message", f"XML message #{stats['xml_messages']}")
                            
                            try:
                                # Parse the XML message
                                data = xmltodict.parse(xml_content)
                                
                                # Update schema model if enabled
                                if args.schema and schema_model is not None:
                                    schema_model = update_schema_model(data, schema_model)
                                    
                                    # Save schema at milestones
                                    if stats["xml_messages"] in [1, 10, 50, 100]:
                                        save_schema_model(schema_model, f"{args.schema_file}.{stats['xml_messages']}")
                                
                                # Extract KV6posinfo - with improved debugging
                                if 'VV_TM_PUSH' in data and 'KV6posinfo' in data['VV_TM_PUSH']:
                                    kv6 = data['VV_TM_PUSH']['KV6posinfo']
                                    
                                    # Save the first KV6posinfo message for detailed analysis
                                    if args.save_messages and "kv6_saved" not in stats:
                                        stats["kv6_saved"] = True
                                        save_debug_message(xml_content, "kv6_message", "First KV6posinfo message")
                                        
                                        # Also save the parsed structure
                                        with open("debug_messages/kv6_structure.json", "w", encoding="utf-8") as f:
                                            json.dump(kv6, f, indent=2)
                                    
                                    # Process different message types
                                    for msg_type in ['ARRIVAL', 'DEPARTURE', 'ONROUTE', 'ONSTOP']:
                                        if msg_type in kv6:
                                            messages = kv6[msg_type]
                                            if not isinstance(messages, list):
                                                messages = [messages]
                                                
                                            for msg in messages:
                                                # Extract relevant information
                                                vehicle_number = msg.get('vehiclenumber')
                                                line_number = msg.get('lineplanningnumber')
                                                
                                                # Apply line filter if specified
                                                if args.line and line_number != args.line:
                                                    continue
                                                    
                                                journey_number = msg.get('journeynumber')
                                                timestamp = msg.get('timestamp')
                                                occupancy = msg.get('occupancy', '0')
                                                
                                                # Debug the first vehicle message
                                                if args.save_messages and "first_vehicle_saved" not in stats:
                                                    stats["first_vehicle_saved"] = True
                                                    with open("debug_messages/first_vehicle.json", "w", encoding="utf-8") as f:
                                                        json.dump(msg, f, indent=2)
                                                
                                                # RD coordinates 
                                                # Note: The XML might have different field names, let's try alternatives
                                                rd_x = 0
                                                rd_y = 0
                                                for x_field in ['rd-x', 'rdx', 'x']:
                                                    if x_field in msg:
                                                        try:
                                                            rd_x = float(msg.get(x_field, 0))
                                                            break
                                                        except (ValueError, TypeError):
                                                            pass
                                                            
                                                for y_field in ['rd-y', 'rdy', 'y']:
                                                    if y_field in msg:
                                                        try:
                                                            rd_y = float(msg.get(y_field, 0))
                                                            break
                                                        except (ValueError, TypeError):
                                                            pass
                                                
                                                # Skip if no coordinates
                                                if rd_x == 0 and rd_y == 0:
                                                    continue
                                                
                                                # Transform coordinates
                                                try:
                                                    lon, lat = transformer.transform(rd_x, rd_y)
                                                except Exception as e:
                                                    error_time = datetime.now().strftime("%H:%M:%S")
                                                    recent_errors.append(f"[{error_time}] Coordinate transform error: {e}")
                                                    continue
                                                
                                                # Update vehicle info
                                                vehicles[vehicle_number] = {
                                                    'line': line_number,
                                                    'journey': journey_number,
                                                    'status': msg_type,
                                                    'stop': msg.get('userstopcode', 'N/A'),
                                                    'occupancy': OCCUPANCY_LEVELS.get(occupancy, "Unknown"),
                                                    'lat': f"{lat:.5f}",
                                                    'lon': f"{lon:.5f}",
                                                    'timestamp': timestamp,
                                                    'last_update': datetime.now().strftime("%H:%M:%S")
                                                }
                                                stats["vehicle_updates"] += 1
                            except Exception as xml_error:
                                error_time = datetime.now().strftime("%H:%M:%S")
                                recent_errors.append(f"[{error_time}] XML parsing error: {xml_error}")
                                if args.save_messages:
                                    save_debug_message(xml_content, "xml_error", str(xml_error))
                        else:
                            # This is probably a control message or non-XML data
                            stats["binary_messages"] += 1
                            if args.debug:
                                error_time = datetime.now().strftime("%H:%M:%S")
                                hex_preview = binascii.hexlify(body[:20]).decode('ascii')
                                recent_errors.append(f"[{error_time}] Binary data: {hex_preview}...")
                    
                    # Create a fresh table each update (prevents header duplication)
                    table = Table(title="Live Arriva Bus Positions")
                    table.add_column("Vehicle", style="cyan")
                    table.add_column("Line", style="green")
                    table.add_column("Journey", style="yellow")
                    table.add_column("Status", style="magenta")
                    table.add_column("Stop", style="blue")
                    table.add_column("Occupancy", style="red")
                    table.add_column("Lat", style="white", justify="right")
                    table.add_column("Lon", style="white", justify="right")
                    table.add_column("Updated", style="dim")
                    
                    # Sort and limit vehicles
                    sorted_vehicles = sorted(vehicles.items())
                    if args.limit > 0:
                        sorted_vehicles = sorted_vehicles[:args.limit]
                    
                    for vehicle, info in sorted_vehicles:
                        # Color-code the occupancy
                        occupancy_style = "green"
                        if info['occupancy'] in ["Few seats", "Standing only"]:
                            occupancy_style = "yellow"
                        elif info['occupancy'] in ["Full", "Not accepting passengers"]:
                            occupancy_style = "red"
                            
                        table.add_row(
                            vehicle,
                            info['line'],
                            info['journey'],
                            info['status'],
                            info['stop'],
                            f"[{occupancy_style}]{info['occupancy']}[/{occupancy_style}]",
                            info['lat'],
                            info['lon'],
                            info['last_update']
                        )
                    
                    # Update title with count information
                    line_filter = f" (Line: {args.line})" if args.line else ""
                    table.title = f"Live Arriva Bus Positions - Showing {len(table.rows)}/{len(vehicles)} buses{line_filter}"
                    
                    # Create stats and error panel
                    stats_text = f"Total: {stats['total_messages']} | XML: {stats['xml_messages']} | Binary: {stats['binary_messages']} | Updates: {stats['vehicle_updates']}"
                    topic_text = f"Topic: {topic!r}"
                    schema_text = "Schema: Enabled" if args.schema else "Schema: Disabled"
                    error_text = "\n".join(recent_errors) if recent_errors else "No errors"
                    error_panel = Panel(f"{stats_text}\n{topic_text} | {schema_text}\n\n{error_text}", title="Feed Status", border_style="yellow")
                    
                    # Update layout with new content
                    layout["table"].update(table)
                    layout["errors"].update(error_panel)
                    
                    # Refresh the display
                    live.update(layout)
                    
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    error_time = datetime.now().strftime("%H:%M:%S")
                    recent_errors.append(f"[{error_time}] Error: {e}")
                    time.sleep(0.5)  # Short pause to prevent error flood
    
    except KeyboardInterrupt:
        console.print("\n[bold green]Shutting down...[/bold green]")
        # Save the schema model if enabled
        if args.schema and schema_model is not None:
            if save_schema_model(schema_model, args.schema_file):
                console.print(f"[bold blue]XML schema saved to {args.schema_file}[/bold blue]")
            else:
                console.print(f"[bold red]Failed to save XML schema[/bold red]")
    finally:
        socket.close()
        context.term()

if __name__ == "__main__":
    main()
