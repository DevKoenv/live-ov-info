from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
import time
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional

from ..data.models import Vehicle, VehicleCollection

class TerminalUI:
    """Rich terminal interface for displaying live bus data"""
    
    def __init__(self, refresh_rate=1.0):
        self.console = Console()
        self.refresh_rate = refresh_rate
        self.live = None
        self.running = False
        self.header_timer = None
        
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
            Layout(name="footer", size=3)  # Increased footer size for better error display
        )
        
        # Initial content with time
        initial_header = self._create_header()
        layout["header"].update(initial_header)
        layout["main"].update("Waiting for data...")
        layout["footer"].update(Panel("Ready", title="Status"))
        
        self.console.show_cursor(False)  # Hide cursor for cleaner display
        
        self.live = Live(
            layout, 
            console=self.console, 
            refresh_per_second=self.refresh_rate,    # Standard refresh rate
            auto_refresh=True,       # Keep auto-refresh enabled
            transient=False         # Prevent clearing screen
        )
        self.live.start()
        
        # Start header update timer
        self._start_header_timer()
        
        return layout
    
    def _start_header_timer(self):
        """Start a timer to update the header every second"""
        if not self.running:
            return
            
        # Update header with current time
        if self.live and self.live.renderable:
            try:
                header = self._create_header()
                self.live.renderable["header"].update(header)
            except Exception:
                pass  # Ignore errors during header update
        
        # Schedule next update
        self.header_timer = threading.Timer(1.0, self._start_header_timer)
        self.header_timer.daemon = True
        self.header_timer.start()
    
    def _create_header(self):
        """Create the header with title and current time"""
        current_time = datetime.now().strftime("%H:%M:%S")
        
        # Create a text object with proper spacing
        header_text = Text()
        header_text.append("Live Bus Tracker", style="bold blue")
        
        # Calculate spacing to right-align the time
        console_width = self.console.size.width
        title_length = len("Live Bus Tracker")
        time_length = len(current_time)
        padding_length = console_width - title_length - time_length - 4  # -4 for panel padding
        
        if padding_length > 0:
            header_text.append(" " * padding_length)
        else:
            header_text.append("  ")  # Minimum spacing
            
        header_text.append(current_time, style="dim")
        
        return Panel(header_text, border_style="blue")
    
    def update(self, vehicles, stats, errors, topic, line_filter=None, limit=20, extra_status=None, view_collection="active"):
        """Update the display with new data"""
        if not self.live or not self.running:
            return
        
        try:
            # Get filtered vehicles from specified collection
            if view_collection == "all":
                # Show all vehicles from all collections
                filtered_vehicles = vehicles.get_all_vehicles()
                if line_filter:
                    filtered_vehicles = [(vid, v) for vid, v in filtered_vehicles if v.line == line_filter]
                filtered_vehicles = sorted(filtered_vehicles)[:limit] if limit > 0 else sorted(filtered_vehicles)
            else:
                filtered_vehicles = vehicles.get_filtered(line=line_filter, limit=limit, collection=view_collection)
            
            # Create table and status panel (header updates separately)
            table = self._create_vehicle_table(filtered_vehicles, vehicles, line_filter, limit, view_collection)
            status_panel = self._create_status_panel(stats, errors, vehicles, line_filter, extra_status)
            
            # Update layout (skip header as it updates automatically)
            layout = self.live.renderable
            layout["main"].update(table)
            layout["footer"].update(status_panel)
            
        except Exception as e:
            if self.running:
                self.console.print(f"[red]Display update error: {e}[/red]")
    
    def _create_vehicle_table(self, filtered_vehicles, vehicles, line_filter, limit, view_collection="active"):
        """Create the vehicle table"""
        table = Table(
            show_header=True, 
            header_style="bold magenta", 
            show_lines=True,
            expand=True,
            show_edge=True,
            padding=(0, 1),
        )
        table.add_column("Vehicle", style="cyan", no_wrap=False, min_width=8)
        table.add_column("Line", style="green", no_wrap=False, min_width=15)
        table.add_column("Status", style="yellow", no_wrap=False, min_width=10)
        table.add_column("Stop", style="blue", no_wrap=False, min_width=6)
        table.add_column("Occupancy", style="red", no_wrap=False, min_width=12)
        table.add_column("Position", style="white", no_wrap=False, min_width=20)
        table.add_column("Updated", style="dim", no_wrap=False, min_width=8)
        
        # Create table title with collection info
        collection_stats = vehicles.get_collection_stats()
        
        # Customize title based on view
        if view_collection == "active":
            table_title = f"Active Vehicles ({len(filtered_vehicles)}"
            if limit and collection_stats["active"] > limit:
                table_title += f" of {collection_stats['active']}"
        elif view_collection == "initialized":
            table_title = f"Initialized Vehicles ({len(filtered_vehicles)}"
            if limit and collection_stats["initialized"] > limit:
                table_title += f" of {collection_stats['initialized']}"
        elif view_collection == "finished":
            table_title = f"Finished Vehicles ({len(filtered_vehicles)}"
            if limit and collection_stats["finished"] > limit:
                table_title += f" of {collection_stats['finished']}"
        else:  # all
            table_title = f"All Vehicles ({len(filtered_vehicles)}"
            if limit and collection_stats["total"] > limit:
                table_title += f" of {collection_stats['total']}"
        
        if line_filter:
            table_title += f" - Line {line_filter}"
        
        table_title += f") | A:{collection_stats['active']} I:{collection_stats['initialized']} F:{collection_stats['finished']}"
        
        table.title = table_title
        table.title_style = "bold blue"
        
        # Add rows to table
        for vehicle_id, vehicle in filtered_vehicles:
            # Color code status based on BISON TMI8 specification
            status_style = self._get_status_style(vehicle.status)
            
            # Format line with name if available
            line_display = self._format_line_display(vehicle)
            
            # Format stop with name if available
            stop_display = self._format_stop_display(vehicle)
            
            table.add_row(
                vehicle_id,
                line_display,
                Text(vehicle.status, style=status_style),
                stop_display,
                vehicle.occupancy,
                f"{vehicle.lat}, {vehicle.lon}",
                vehicle.last_update
            )
        
        return table
    
    def _create_status_panel(self, stats, errors, vehicles, line_filter, extra_status):
        """Create the status panel"""
        collection_stats = vehicles.get_collection_stats()
        
        status_parts = [
            f"Total: {stats['total_messages']}",
            f"XML: {stats['xml_messages']}",
            f"Binary: {stats['binary_messages']}",
            f"Updates: {stats['vehicle_updates']}",
            f"Vehicles: {collection_stats['total']} (A:{collection_stats['active']}/I:{collection_stats['initialized']}/F:{collection_stats['finished']})"
        ]
        
        if extra_status:
            for key, value in extra_status.items():
                status_parts.append(f"{key}: {value}")
        
        status_text = " | ".join(status_parts)
        
        if line_filter:
            status_text += f" | Filter: Line {line_filter}"
        
        # Enhanced error display with categorization
        if errors:
            recent_errors = list(errors)[-3:]
            
            # Categorize errors
            critical_errors = [e for e in recent_errors if "Connection" in e or "ZMQ error" in e]
            warning_errors = [e for e in recent_errors if "Unknown" in e or "parsing" in e]
            
            error_parts = []
            if critical_errors:
                error_parts.append(f"[bold red]Critical ({len(critical_errors)}):[/bold red]")
                error_parts.extend([f"  • {error}" for error in critical_errors])
            
            if warning_errors:
                error_parts.append(f"[bold yellow]Warnings ({len(warning_errors)}):[/bold yellow]")
                error_parts.extend([f"  • {error}" for error in warning_errors])
            
            if not critical_errors and not warning_errors:
                error_parts = [f"[bold blue]Recent Issues ({len(recent_errors)}):[/bold blue]"] + [f"  • {error}" for error in recent_errors]
            
            error_text = "\n".join(error_parts)
            panel_style = "red" if critical_errors else ("yellow" if warning_errors else "blue")
            
            return Panel(
                f"{status_text}\n\n{error_text}", 
                title=f"Feed Status ({len(errors)} total errors)", 
                border_style=panel_style
            )
        else:
            return Panel(status_text, title="Feed Status", border_style="green")
    
    def _get_status_style(self, status):
        """Get the color style for a vehicle status"""
        status_styles = {
            "ARRIVAL": "green",
            "DEPARTURE": "red", 
            "ONROUTE": "blue",
            "ONSTOP": "yellow",
            "INIT": "cyan",
            "END": "magenta",
            "DELAY": "bold red",
            "OFFROUTE": "bold yellow",
            "CANCEL": "bold red"
        }
        return status_styles.get(status, "dim")
    
    def _format_line_display(self, vehicle):
        """Format line display with name if available"""
        line_display = vehicle.line
        if hasattr(vehicle, 'line_name') and vehicle.line_name:
            # Simple concatenation - let Rich handle wrapping
            line_display = f"{vehicle.line} - {vehicle.line_name}"
        return line_display
    
    def _format_stop_display(self, vehicle):
        """Format stop display with name if available"""
        stop_display = vehicle.stop
        if hasattr(vehicle, 'stop_name') and vehicle.stop_name and vehicle.stop_name != vehicle.stop:
            # Show stop code and name on separate lines
            stop_display = f"{vehicle.stop}\n{vehicle.stop_name}"
        return stop_display
    
    def stop(self):
        """Stop the live display"""
        self.running = False
        
        # Stop header timer
        if self.header_timer:
            self.header_timer.cancel()
            
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