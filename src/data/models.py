from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, List

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

@dataclass
class Vehicle:
    """Represents a public transit vehicle (bus)"""
    id: str
    line: str
    journey: str
    status: str
    stop: str
    occupancy: str
    lat: str
    lon: str
    timestamp: str
    last_update: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    
    # Additional enrichment fields for reference data
    stop_name: Optional[str] = None
    stop_municipality: Optional[str] = None
    line_name: Optional[str] = None
    _operator: Optional[str] = None  # Internal field to track operator
    
    # BISON TMI8 specific fields
    delay_seconds: Optional[int] = None  # Delay in seconds from DELAY messages
    init_timestamp: Optional[str] = None  # When journey was initialized
    finish_timestamp: Optional[str] = None  # When journey finished
    finish_reason: Optional[str] = None  # 'END' or 'CANCEL'
    
    @classmethod
    def from_kv6_message(cls, msg, transformer):
        """Create a Vehicle instance from a KV6 message"""
        vehicle_number = msg.get('vehiclenumber')
        line_number = msg.get('lineplanningnumber')
        journey_number = msg.get('journeynumber')
        status = msg.get('_message_type', 'UNKNOWN')  # Should be set by parser
        occupancy = msg.get('occupancy', '0')
        
        # Extract RD coordinates 
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
            return None
        
        # Transform coordinates from RD to WGS84
        try:
            lon, lat = transformer.transform(rd_x, rd_y)
        except Exception as e:
            print(f"Coordinate transform error: {e}")
            return None
        
        # Determine operator from topic or other means if available
        operator = None
        if '_topic' in msg:
            topic = msg['_topic']
            # Extract operator from topic like "/ARR/KV6posinfo"
            if topic.startswith('/') and topic.count('/') >= 2:
                operator_code = topic.split('/')[1]
                # Map operator codes to names
                operator_map = {
                    'ARR': 'arriva',
                    'CXX': 'connexxion', 
                    'GVB': 'gvb',
                    'HTM': 'htm',
                    'NS': 'ns',
                    'RET': 'ret',
                    'SYN': 'syntus',
                    'VTN': 'veolia',
                    'QBUZZ': 'qbuzz'
                }
                operator = operator_map.get(operator_code)
        
        # Create the vehicle instance
        vehicle = cls(
            id=vehicle_number,
            line=line_number,
            journey=journey_number,
            status=status,
            stop=msg.get('userstopcode', 'N/A'),
            occupancy=OCCUPANCY_LEVELS.get(occupancy, "Unknown"),
            lat=f"{lat:.5f}",
            lon=f"{lon:.5f}",
            timestamp=msg.get('timestamp'),
        )
        
        # Set internal operator field for reference data enrichment
        if operator:
            vehicle._operator = operator
        
        # Handle BISON TMI8 specific fields based on message type
        if status == "INIT":
            vehicle.init_timestamp = vehicle.timestamp or datetime.now().isoformat()
        elif status == "DELAY":
            # Extract delay information if available
            delay_value = msg.get('delay') or msg.get('delayminutes') or msg.get('delaytime')
            if delay_value:
                try:
                    vehicle.delay_seconds = int(delay_value) * 60 if 'minutes' in str(delay_value).lower() else int(delay_value)
                except (ValueError, TypeError):
                    vehicle.delay_seconds = None
        elif status in ["END", "CANCEL"]:
            vehicle.finish_timestamp = vehicle.timestamp or datetime.now().isoformat()
            vehicle.finish_reason = status
        
        return vehicle

@dataclass
class VehicleCollection:
    """Collection of vehicles with BISON TMI8 lifecycle management"""
    
    # Active vehicles currently in service (DEPARTURE, ARRIVAL, ONROUTE, ONSTOP, OFFROUTE)
    active_vehicles: Dict[str, Vehicle] = field(default_factory=dict)
    
    # Vehicles that have been initialized but not yet started active service (INIT, DELAY)
    initialized_vehicles: Dict[str, Vehicle] = field(default_factory=dict)
    
    # Vehicles that have finished their journey (END, CANCEL)
    finished_vehicles: Dict[str, Vehicle] = field(default_factory=dict)
    
    def add_or_update(self, vehicle):
        """Add or update a vehicle based on BISON TMI8 lifecycle"""
        if not vehicle:
            return
        
        vehicle_id = vehicle.id
        
        # Handle different message types according to BISON TMI8 specification
        if vehicle.status == "INIT":
            # Vehicle journey is initialized - move to initialized collection
            self._move_vehicle_to_initialized(vehicle_id, vehicle)
            
        elif vehicle.status == "DELAY":
            # Vehicle is delayed - could be before start or during journey
            if vehicle_id in self.active_vehicles:
                # Update active vehicle with delay info
                self.active_vehicles[vehicle_id] = vehicle
            else:
                # Move to initialized collection (delayed before start)
                self._move_vehicle_to_initialized(vehicle_id, vehicle)
            
        elif vehicle.status in ["ARRIVAL", "DEPARTURE", "ONROUTE", "ONSTOP", "OFFROUTE"]:
            # Vehicle is actively in service - move to active collection
            self._move_vehicle_to_active(vehicle_id, vehicle)
            
        elif vehicle.status in ["END", "CANCEL"]:
            # Vehicle journey has ended - move to finished collection
            self._move_vehicle_to_finished(vehicle_id, vehicle)
            
        else:
            # Unknown status - keep in active for safety
            self.active_vehicles[vehicle_id] = vehicle
    
    def _move_vehicle_to_initialized(self, vehicle_id, vehicle):
        """Move vehicle to initialized collection"""
        # Remove from other collections
        self.active_vehicles.pop(vehicle_id, None)
        self.finished_vehicles.pop(vehicle_id, None)
        # Add to initialized
        self.initialized_vehicles[vehicle_id] = vehicle
    
    def _move_vehicle_to_active(self, vehicle_id, vehicle):
        """Move vehicle to active collection"""
        # Remove from other collections
        self.initialized_vehicles.pop(vehicle_id, None)
        self.finished_vehicles.pop(vehicle_id, None)
        # Add to active
        self.active_vehicles[vehicle_id] = vehicle
    
    def _move_vehicle_to_finished(self, vehicle_id, vehicle):
        """Move vehicle to finished collection"""
        # Remove from other collections
        self.active_vehicles.pop(vehicle_id, None)
        self.initialized_vehicles.pop(vehicle_id, None)
        # Add to finished
        self.finished_vehicles[vehicle_id] = vehicle
    
    def get_filtered(self, line=None, limit=0, collection="active"):
        """Return filtered and limited vehicles from specified collection"""
        if collection == "active":
            items = self.active_vehicles.items()
        elif collection == "initialized":
            items = self.initialized_vehicles.items()
        elif collection == "finished":
            items = self.finished_vehicles.items()
        else:
            items = self.active_vehicles.items()
        
        # Apply line filter if specified
        if line:
            items = [(vid, v) for vid, v in items if v.line == line]
            
        # Sort the items
        items = sorted(items)
        
        # Apply limit if specified
        if limit > 0:
            items = items[:limit]
            
        return items
    
    def get_all_vehicles(self):
        """Get all vehicles from all collections as list of tuples (vehicle_id, vehicle)"""
        all_vehicles = []
        all_vehicles.extend(self.active_vehicles.items())
        all_vehicles.extend(self.initialized_vehicles.items())
        all_vehicles.extend(self.finished_vehicles.items())
        return all_vehicles
    
    def get_by_status(self, status):
        """Get vehicles filtered by status from all collections"""
        all_vehicles = self.get_all_vehicles()
        return [(vid, v) for vid, v in all_vehicles if v.status == status]
    
    def get_by_line(self, line):
        """Get vehicles filtered by line from all collections"""
        all_vehicles = self.get_all_vehicles()
        return [(vid, v) for vid, v in all_vehicles if v.line == line]
    
    def get_by_operator(self, operator):
        """Get vehicles filtered by operator from all collections"""
        all_vehicles = self.get_all_vehicles()
        return [(vid, v) for vid, v in all_vehicles if getattr(v, '_operator', '') == operator]
    
    def get_collection_stats(self):
        """Get statistics about vehicle collections"""
        return {
            "active": len(self.active_vehicles),
            "initialized": len(self.initialized_vehicles),
            "finished": len(self.finished_vehicles),
            "total": len(self.active_vehicles) + len(self.initialized_vehicles) + len(self.finished_vehicles)
        }
    
    def cleanup_old_finished(self, max_finished=1000):
        """Remove old finished vehicles to prevent memory growth"""
        if len(self.finished_vehicles) > max_finished:
            # Keep only the most recent finished vehicles
            sorted_finished = sorted(
                self.finished_vehicles.items(), 
                key=lambda x: x[1].last_update, 
                reverse=True
            )
            self.finished_vehicles = dict(sorted_finished[:max_finished])
    
    def __len__(self):
        """Return total number of vehicles across all collections"""
        return len(self.active_vehicles) + len(self.initialized_vehicles) + len(self.finished_vehicles)