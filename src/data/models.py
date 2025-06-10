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
            
        return vehicle

@dataclass
class VehicleCollection:
    """Collection of vehicles with helper methods"""
    vehicles: Dict[str, Vehicle] = field(default_factory=dict)
    
    def add_or_update(self, vehicle):
        """Add or update a vehicle in the collection"""
        if vehicle:
            self.vehicles[vehicle.id] = vehicle
    
    def get_sorted(self):
        """Return vehicles sorted by ID"""
        return sorted(self.vehicles.items())
    
    def get_filtered(self, line=None, limit=0):
        """Return filtered and limited vehicles"""
        items = self.vehicles.items()
        
        # Apply line filter if specified
        if line:
            items = [(vid, v) for vid, v in items if v.line == line]
            
        # Sort the items
        items = sorted(items)
        
        # Apply limit if specified
        if limit > 0:
            items = items[:limit]
            
        return items
    
    def __len__(self):
        return len(self.vehicles)
    
    def to_dict(self):
        """Convert to dictionary format for backward compatibility"""
        return {
            vehicle.id: {
                'line': vehicle.line,
                'journey': vehicle.journey,
                'status': vehicle.status,
                'stop': vehicle.stop,
                'occupancy': vehicle.occupancy,
                'lat': vehicle.lat,
                'lon': vehicle.lon,
                'timestamp': vehicle.timestamp,
                'last_update': vehicle.last_update
            } for vehicle in self.vehicles.values()
        }