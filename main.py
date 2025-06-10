#!/usr/bin/env python3
"""
Live OV Info - Real-time public transport information terminal
"""

import argparse
import pyproj
import time
from datetime import datetime

from src.data.models import Vehicle, VehicleCollection
from src.data.parser import save_debug_message, update_schema_model, save_schema_model
from src.data.references import ReferenceData
from src.network.client import NDOVClient
from src.ui.terminal import TerminalUI

def parse_arguments():
    parser = argparse.ArgumentParser(description="Live Public Transport Information Terminal")
    parser.add_argument("--line", type=str, help="Filter by line number")
    parser.add_argument("--limit", type=int, default=10, help="Limit number of vehicles shown")
    parser.add_argument("--refresh", type=int, default=4, help="Refresh rate in seconds")
    parser.add_argument("--debug", action="store_true", help="Show debug messages for binary data")
    
    # Network options
    parser.add_argument("--operators", type=str, nargs="+", default=["arriva"], 
                       help="Operators to monitor (arriva, connexxion, gvb, htm, ns, ret, syntus, veolia, qbuzz)")
    parser.add_argument("--all-operators", action="store_true", help="Monitor all operators")
    parser.add_argument("--topics", type=str, nargs="+", help="Custom ZeroMQ topics to subscribe to")
    parser.add_argument("--message-types", type=str, nargs="+", default=["KV6posinfo"],
                       help="Message types to subscribe to (KV6posinfo, KV15messages, KV17cvlinfo)")
    
    # Data options
    parser.add_argument("--save-messages", action="store_true", help="Save all XML messages for analysis")
    parser.add_argument("--schema", action="store_true", help="Generate XML schema documentation (default: disabled)")
    parser.add_argument("--schema-file", type=str, default="xml_schema.json", help="File to save discovered XML schema")
    parser.add_argument("--no-reference-data", action="store_true", help="Disable automatic reference data loading")
    
    return parser.parse_args()

def main():
    args = parse_arguments()
    
    # Setup coordinate transformation (Dutch RD to WGS84)
    transformer = pyproj.Transformer.from_crs("EPSG:28992", "EPSG:4326", always_xy=True)
    
    # Initialize reference data (only if not disabled)
    reference_data = None
    if not args.no_reference_data:
        try:
            reference_data = ReferenceData(operators=args.operators)
        except Exception as e:
            print(f"Warning: Could not initialize reference data: {e}")
    
    # Initialize network client based on arguments
    try:
        if args.topics:
            # Custom topics specified
            client = NDOVClient(topics=args.topics)
        elif args.all_operators:
            # All operators with specified message types
            all_topics = []
            from src.network.client import OPERATORS
            for operator_prefix in OPERATORS.values():
                for msg_type in args.message_types:
                    all_topics.append(f"{operator_prefix}{msg_type}")
            client = NDOVClient(topics=all_topics)
        else:
            # Specific operators with message types
            topics = []
            from src.network.client import OPERATORS
            for operator in args.operators:
                if operator.lower() in OPERATORS:
                    operator_prefix = OPERATORS[operator.lower()]
                    for msg_type in args.message_types:
                        topics.append(f"{operator_prefix}{msg_type}")
                else:
                    print(f"Warning: Unknown operator '{operator}', skipping")
            
            if not topics:
                print("Error: No valid operators specified")
                return 1
            
            client = NDOVClient(topics=topics)
    except Exception as e:
        print(f"Error initializing network client: {e}")
        return 1
    
    # Initialize UI
    ui = TerminalUI(args.refresh)
    ui.print_welcome(client.topics)
    
    # Connect to NDOV feed
    if not client.connect():
        ui.print_error("Failed to connect to NDOV feed")
        return 1
    
    # Initialize vehicle collection
    vehicles = VehicleCollection()
    
    # Schema model to document XML structure (only if enabled)
    schema_model = {} if args.schema else None
    
    # Debug tracking
    debug_saved = {
        "first_message": False,
        "kv6_saved": False,
        "first_vehicle_saved": False
    }
    
    try:
        # Start the live display
        layout = ui.start()
        
        while True:
            try:
                # Receive message from the network
                topic, body = client.receive_message()
                
                if topic is None:
                    continue
                
                # Save the first message for debugging
                if args.save_messages and not debug_saved["first_message"]:
                    debug_saved["first_message"] = True
                    save_debug_message(body, "first_message", f"First message received, topic: {topic}")
                
                # Process the message
                messages, parse_stats = client.process_message(topic, body)
                
                # Process each vehicle message
                for msg in messages:
                    # Save the first KV6posinfo message for detailed analysis
                    if args.save_messages and not debug_saved["kv6_saved"]:
                        debug_saved["kv6_saved"] = True
                        import json
                        os.makedirs("debug_messages", exist_ok=True)
                        with open("debug_messages/kv6_structure.json", "w", encoding="utf-8") as f:
                            json.dump(msg, f, indent=2)
                    
                    # Save the first vehicle message
                    if args.save_messages and not debug_saved["first_vehicle_saved"]:
                        debug_saved["first_vehicle_saved"] = True
                        import json
                        os.makedirs("debug_messages", exist_ok=True)
                        with open("debug_messages/first_vehicle.json", "w", encoding="utf-8") as f:
                            json.dump(msg, f, indent=2)
                    
                    # Apply line filter at message level if specified
                    if args.line and msg.get('lineplanningnumber') != args.line:
                        continue
                    
                    # Create vehicle from message
                    vehicle = Vehicle.from_kv6_message(msg, transformer)
                    
                    if vehicle:
                        # Enrich with reference data if available
                        if reference_data:
                            reference_data.enrich_vehicle(vehicle)
                        
                        # Add to collection
                        vehicles.add_or_update(vehicle)
                
                # Update schema model if enabled
                if args.schema and schema_model is not None and messages:
                    for msg in messages:
                        schema_model = update_schema_model(msg, schema_model)
                        
                        # Save schema at milestones
                        if client.stats["xml_messages"] in [1, 10, 50, 100]:
                            save_schema_model(schema_model, f"{args.schema_file}.{client.stats['xml_messages']}")
                
                # Update the UI (only refresh if significant changes occurred)
                extra_status = {}
                if args.schema:
                    extra_status["Schema"] = "Enabled"
                
                # Add operator stats if available
                stats_summary = client.get_stats_summary()
                if stats_summary.get("by_operator"):
                    extra_status["Operators"] = stats_summary["by_operator"]
                
                ui.update(
                    vehicles=vehicles,
                    stats=client.stats,
                    errors=list(client.recent_errors),
                    topic=str(client.topics),
                    line_filter=args.line,
                    limit=args.limit,
                    extra_status=extra_status
                )
                
            except KeyboardInterrupt:
                raise
            except Exception as e:
                client.record_error(f"Processing error: {e}")
                time.sleep(0.5)  # Short pause to prevent error flood
    
    except KeyboardInterrupt:
        ui.print_success("Shutting down...")
        
        # Save the schema model if enabled
        if args.schema and schema_model is not None:
            if save_schema_model(schema_model, args.schema_file):
                ui.print_info(f"XML schema saved to {args.schema_file}")
            else:
                ui.print_error("Failed to save XML schema")
    
    finally:
        ui.stop()
        client.disconnect()
        if reference_data:
            reference_data.shutdown()
        return 0

if __name__ == "__main__":
    import os
    exit(main())