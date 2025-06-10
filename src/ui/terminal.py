from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
import time
from datetime import datetime
from typing import Dict, List, Any, Optional

from ..data.models import Vehicle, VehicleCollection

def create_display_layout():
    """Create a layout with areas for the table and error messages"""
    layout = Layout()
    layout.split(
        Layout(name="table"),
        Layout(name="errors", size=5)
    )
    return layout

class TerminalUI:
    """Rich terminal interface for displaying live bus data"""
    
    def __init__(self, refresh_rate=1.0):
        self.console = Console()
        self.refresh_rate = refresh_rate
        self.live = None
        self.running = False
        self.last_stats = None  # Cache last stats to reduce flickering
        self.last_status_panel = None  # Cache status panel
        
    def print_welcome(self, topics):
        """Print welcome message with topic information"""
        if isinstance(topics, str):
            topics = [topics]
        
        welcome_text = f"""
[bold blue]Live OV Info - Real-time Public Transport Terminal[/bold blue]

Subscribed to topics:
{chr(10).join(f"  • {topic}" for topic in topics)}

[dim]Press Ctrl+C to exit[/dim]
        """
        self.console.print(Panel(welcome_text.strip(), title="Welcome", border_style="blue"))
    
    def start(self):
        """Start the live display"""
        self.running = True
        
        # Create initial layout
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=6)  # Increased footer size for better error display
        )
        
        # Initial content
        layout["header"].update(Panel("Live Bus Tracker", style="bold blue"))
        layout["main"].update("Waiting for data...")
        layout["footer"].update(Panel("Ready", title="Status"))
        
        self.live = Live(layout, console=self.console, refresh_per_second=1/self.refresh_rate)
        self.live.start()
        
        return layout
    
    def update(self, vehicles, stats, errors, topic, line_filter=None, limit=20, extra_status=None):
        """Update the display with new data"""
        if not self.live or not self.running:
            return
        
        try:
            # Create table for vehicles with full width and dividers
            table = Table(
                show_header=True, 
                header_style="bold magenta", 
                show_lines=True,  # Add vertical lines between columns
                expand=True,      # Take up full terminal width
                show_edge=True,   # Show outer borders
                padding=(0, 1),   # Small padding for readability
            )
            table.add_column("Vehicle", style="cyan", no_wrap=False, min_width=8)
            table.add_column("Line", style="green", no_wrap=False, min_width=15)
            table.add_column("Status", style="yellow", no_wrap=False, min_width=10)
            table.add_column("Stop", style="blue", no_wrap=False, min_width=6)
            table.add_column("Occupancy", style="red", no_wrap=False, min_width=12)
            table.add_column("Position", style="white", no_wrap=False, min_width=20)
            table.add_column("Updated", style="dim", no_wrap=False, min_width=8)
            
            # Get filtered vehicles
            filtered_vehicles = vehicles.get_filtered(line=line_filter, limit=limit)
            
            # Create table title with count and filter info
            table_title = f"Live Vehicles ({len(filtered_vehicles)}"
            if line_filter:
                table_title += f" - Line {line_filter}"
            if limit and len(vehicles) > limit:
                table_title += f" of {len(vehicles)}"
            table_title += ")"
            
            # Set table title
            table.title = table_title
            table.title_style = "bold blue"
            
            # Add rows to table
            for vehicle_id, vehicle in filtered_vehicles:
                # Color code status
                status_style = ""
                if vehicle.status == "ARRIVAL":
                    status_style = "green"
                elif vehicle.status == "DEPARTURE":
                    status_style = "red"
                elif vehicle.status == "ONROUTE":
                    status_style = "blue"
                elif vehicle.status == "ONSTOP":
                    status_style = "yellow"
                
                # Format line with name if available
                line_display = vehicle.line
                if hasattr(vehicle, 'line_name') and vehicle.line_name:
                    # If line name is long, put it on a new line
                    if len(vehicle.line_name) > 30:
                        line_display = f"{vehicle.line}\n{vehicle.line_name}"
                    else:
                        line_display = f"{vehicle.line} - {vehicle.line_name}"
                
                # Format stop with name if available
                stop_display = vehicle.stop
                if hasattr(vehicle, 'stop_name') and vehicle.stop_name and vehicle.stop_name != vehicle.stop:
                    # If stop name is long, put it on a new line
                    if len(vehicle.stop_name) > 20:
                        stop_display = f"{vehicle.stop}\n{vehicle.stop_name}"
                    else:
                        stop_display = f"{vehicle.stop}\n{vehicle.stop_name}"
                
                table.add_row(
                    vehicle_id,
                    line_display,
                    Text(vehicle.status, style=status_style),
                    stop_display,
                    vehicle.occupancy,
                    f"{vehicle.lat}, {vehicle.lon}",
                    vehicle.last_update
                )
            
            # Create status panel (only update if stats changed to reduce flickering)
            current_stats_key = f"{stats['total_messages']}-{stats['xml_messages']}-{stats['vehicle_updates']}-{len(vehicles)}-{len(errors)}"
            
            if self.last_stats != current_stats_key or self.last_status_panel is None:
                status_parts = [
                    f"Total: {stats['total_messages']}",
                    f"XML: {stats['xml_messages']}",
                    f"Binary: {stats['binary_messages']}",
                    f"Updates: {stats['vehicle_updates']}",
                    f"Vehicles: {len(vehicles)}"
                ]
                
                if extra_status:
                    for key, value in extra_status.items():
                        status_parts.append(f"{key}: {value}")
                
                status_text = " | ".join(status_parts)
                
                if line_filter:
                    status_text += f" | Filter: Line {line_filter}"
                
                # Enhanced error display
                if errors:
                    # Show last 3 errors with proper formatting
                    recent_errors = list(errors)[-3:]  # Get last 3 errors
                    error_text = "\n".join(f"• {error}" for error in recent_errors)
                    panel_style = "yellow" if len(errors) < 5 else "red"
                    self.last_status_panel = Panel(
                        f"{status_text}\n\n[bold red]Recent Errors ({len(errors)} total):[/bold red]\n{error_text}", 
                        title="Feed Status", 
                        border_style=panel_style
                    )
                else:
                    self.last_status_panel = Panel(status_text, title="Feed Status", border_style="green")
                
                self.last_stats = current_stats_key
            
            # Update layout
            layout = self.live.renderable
            layout["main"].update(table)
            layout["footer"].update(self.last_status_panel)
            
        except Exception as e:
            if self.running:
                self.console.print(f"[red]Display update error: {e}[/red]")
    
    def stop(self):
        """Stop the live display"""
        self.running = False
        if self.live:
            self.live.stop()
    
    def print_error(self, message):
        """Print an error message"""
        self.console.print(f"[bold red]Error:[/bold red] {message}")
    
    def print_info(self, message):
        """Print an info message"""
        self.console.print(f"[bold blue]Info:[/bold blue] {message}")
    
    def print_success(self, message):
        """Print a success message"""
        self.console.print(f"[bold green]Success:[/bold green] {message}")