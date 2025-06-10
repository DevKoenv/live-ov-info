import gzip
import requests
import xml.etree.ElementTree as ET
from typing import Dict, Optional, List, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import threading
import time
import re
import json
import os

@dataclass
class StopInfo:
    """Information about a public transport stop"""
    code: str
    name: str
    municipality: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    stop_type: str = "bus"  # bus, tram, metro, train
    operator: str = ""

@dataclass
class LineInfo:
    """Information about a transport line"""
    operator_code: str
    line_number: str
    line_name: str = ""
    transport_type: str = "bus"
    route_description: str = ""

@dataclass
class VehicleInfo:
    """Information about a vehicle"""
    vehicle_id: str
    operator: str
    vehicle_type: str = "bus"
    capacity: Optional[int] = None
    accessible: bool = False

class ReferenceData:
    """Handles dynamic reference data from NDOV feeds organized by operator"""
    
    # NDOV NeTEx data sources by operator
    NETEX_SOURCES = {
        "arriva": "https://data.ndovloket.nl/netex/arr/",
        "qbuzz": "https://data.ndovloket.nl/netex/qbuzz/", 
        "connexxion": "https://data.ndovloket.nl/netex/cxx/",
        "gvb": "https://data.ndovloket.nl/netex/gvb/",
        "htm": "https://data.ndovloket.nl/netex/htm/",
        "ret": "https://data.ndovloket.nl/netex/ret/",
        "ns": "https://data.ndovloket.nl/netex/ns/",
        # Add more operators as needed
    }
    
    # Legacy CHB stops source (contains all operators)
    CHB_STOPS_SOURCE = "https://data.ndovloket.nl/haltes/"
    
    def __init__(self, operators=None, auto_update=True, update_interval_hours=24):
        """Initialize reference data for specific operators"""
        if operators is None:
            operators = ["arriva"]  # Default to Arriva only
        elif isinstance(operators, str):
            operators = [operators]
        
        self.operators = [op.lower() for op in operators]
        self.stops: Dict[str, StopInfo] = {}
        self.lines: Dict[str, Dict[str, LineInfo]] = {}  # operator -> line_id -> LineInfo
        self.vehicles: Dict[str, VehicleInfo] = {}
        
        # Auto-update settings
        self.auto_update = auto_update
        self.update_interval = timedelta(hours=update_interval_hours)
        self.last_update = None
        self.update_thread = None
        self.running = True
        
        # Cache directory
        self.cache_dir = "cache"
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Start initial data load
        self._load_initial_data()
        
        # Start auto-update thread if enabled
        if auto_update:
            self._start_update_thread()
    
    def _load_initial_data(self):
        """Load initial reference data for configured operators"""
        print(f"Loading reference data for operators: {', '.join(self.operators)}")
        
        # Load operator-specific data from NeTEx (skip CHB for now, focus on Arriva)
        for operator in self.operators:
            if operator in self.NETEX_SOURCES:
                try:
                    self._load_netex_operator_data(operator)
                    print(f"Loaded NeTEx data for {operator}")
                except Exception as e:
                    print(f"Warning: Could not load NeTEx data for {operator}: {e}")
            else:
                print(f"Warning: No NeTEx source configured for operator '{operator}'")
        
        self.last_update = datetime.now()
    
    def _start_update_thread(self):
        """Start background thread for periodic updates"""
        def update_worker():
            while self.running:
                if self.last_update and datetime.now() - self.last_update > self.update_interval:
                    try:
                        self._load_initial_data()
                        self.last_update = datetime.now()
                        print(f"Reference data updated at {self.last_update.strftime('%H:%M:%S')}")
                    except Exception as e:
                        print(f"Failed to update reference data: {e}")
                
                time.sleep(3600)  # Check every hour
        
        self.update_thread = threading.Thread(target=update_worker, daemon=True)
        self.update_thread.start()
    
    def _load_chb_stops_data(self):
        """Load stops data from CHB (legacy) source - contains all operators"""
        cache_file = os.path.join(self.cache_dir, "chb_stops.json")
        
        # Try cache first
        if os.path.exists(cache_file):
            try:
                cache_time = os.path.getmtime(cache_file)
                if datetime.now().timestamp() - cache_time < 86400:  # 24 hour cache
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_data = json.load(f)
                        for stop_data in cached_data:
                            if stop_data.get('code'):  # Only load valid stops
                                stop = StopInfo(**stop_data)
                                self.stops[stop.code] = stop
                    print(f"Loaded {len(self.stops)} stops from CHB cache")
                    return
            except Exception as e:
                print(f"CHB cache loading failed: {e}")
        
        # Fetch from live source
        try:
            # Get directory listing
            response = requests.get(self.CHB_STOPS_SOURCE, timeout=30)
            response.raise_for_status()
            
            # Find latest CHB export file
            html = response.text
            export_files = re.findall(r'ExportCHB\d+\.xml\.gz', html)
            
            if not export_files:
                print("No CHB export files found")
                return
            
            # Get the latest file (sorted by date in filename)
            latest_file = sorted(export_files)[-1]
            file_url = f"{self.CHB_STOPS_SOURCE}{latest_file}"
            
            print(f"Downloading CHB stops data from {latest_file}...")
            
            # Download and decompress
            response = requests.get(file_url, timeout=300)
            response.raise_for_status()
            xml_data = gzip.decompress(response.content)
            
            # Parse XML - CHB format uses TMI namespace
            root = ET.fromstring(xml_data)
            
            # The actual namespace and structure needs to be determined from real data
            # This is a best-guess based on typical TMI/CHB formats
            namespaces = {
                'tmi': 'http://www.tmf.nl/',
                'chb': 'http://www.tm-solutions.nl/schema/kv1_0'  # Alternative namespace
            }
            
            stops_parsed = 0
            
            # Try different possible element names and namespaces
            for ns_prefix, ns_uri in namespaces.items():
                ns = {ns_prefix: ns_uri}
                
                # Try various stop element names
                for stop_xpath in [f'.//{ns_prefix}:Stop', f'.//{ns_prefix}:Halte', './/Stop', './/Halte']:
                    try:
                        for stop_element in root.findall(stop_xpath, ns):
                            code = None
                            name = None
                            lat = lon = None
                            municipality = ""
                            
                            # Try different attribute and element names for stop code
                            for code_attr in ['UserStopCode', 'StopCode', 'Code', 'TimingPointCode']:
                                if stop_element.get(code_attr):
                                    code = stop_element.get(code_attr)
                                    break
                            
                            # Try different ways to get stop name
                            name = (stop_element.get('Name') or 
                                   stop_element.get('StopName') or
                                   stop_element.findtext(f'.//{ns_prefix}:Name', namespaces=ns) or
                                   stop_element.findtext('.//Name'))
                            
                            # Try to get municipality
                            municipality = (stop_element.get('Municipality') or
                                          stop_element.findtext(f'.//{ns_prefix}:Municipality', namespaces=ns) or
                                          stop_element.findtext('.//Municipality') or "")
                            
                            # Try to get coordinates
                            location = stop_element.find(f'.//{ns_prefix}:Location', ns) or stop_element.find('.//Location')
                            if location is not None:
                                try:
                                    lat_elem = location.find(f'.//{ns_prefix}:Latitude', ns) or location.find('.//Latitude')
                                    lon_elem = location.find(f'.//{ns_prefix}:Longitude', ns) or location.find('.//Longitude')
                                    
                                    if lat_elem is not None and lon_elem is not None:
                                        lat = float(lat_elem.text)
                                        lon = float(lon_elem.text)
                                except (ValueError, AttributeError):
                                    pass
                            
                            if code and name:
                                stop = StopInfo(
                                    code=code,
                                    name=name,
                                    municipality=municipality,
                                    lat=lat,
                                    lon=lon,
                                    operator="multiple"  # CHB contains all operators
                                )
                                self.stops[code] = stop
                                stops_parsed += 1
                        
                        if stops_parsed > 0:
                            break  # Found valid stops, stop trying other XPaths
                            
                    except Exception as e:
                        continue  # Try next xpath
                
                if stops_parsed > 0:
                    break  # Found valid stops, stop trying other namespaces
            
            print(f"Parsed {stops_parsed} stops from CHB data")
            
            # Save to cache
            if stops_parsed > 0:
                cache_data = [
                    {
                        "code": stop.code,
                        "name": stop.name,
                        "municipality": stop.municipality,
                        "lat": stop.lat,
                        "lon": stop.lon,
                        "stop_type": stop.stop_type,
                        "operator": stop.operator
                    }
                    for stop in self.stops.values()
                ]
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f, indent=2, ensure_ascii=False)
                print(f"Cached {len(cache_data)} stops to {cache_file}")
            
        except Exception as e:
            print(f"Error loading CHB stops data: {e}")
    
    def _load_netex_operator_data(self, operator):
        """Load operator-specific data from NeTEx source"""
        if operator not in self.NETEX_SOURCES:
            print(f"No NeTEx source for operator: {operator}")
            return
        
        cache_file = os.path.join(self.cache_dir, f"netex_{operator}.json")
        
        # Try cache first
        if os.path.exists(cache_file):
            try:
                cache_time = os.path.getmtime(cache_file)
                if datetime.now().timestamp() - cache_time < 86400:  # 24 hour cache
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_data = json.load(f)
                        self._load_cached_netex_data(operator, cached_data)
                    print(f"Loaded NeTEx data for {operator} from cache")
                    return
            except Exception as e:
                print(f"NeTEx cache loading failed for {operator}: {e}")
        
        # Fetch from live source
        try:
            source_url = self.NETEX_SOURCES[operator]
            response = requests.get(source_url, timeout=30)
            response.raise_for_status()
            
            # Find latest NeTEx file for this operator
            html = response.text
            netex_files = re.findall(r'NeTEx_[^"]+\.xml\.gz', html)
            
            if not netex_files:
                print(f"No NeTEx files found for {operator}")
                return
            
            # Get the latest file
            latest_file = sorted(netex_files)[-1]
            file_url = f"{source_url}{latest_file}"
            
            print(f"Downloading NeTEx data for {operator} from {latest_file}...")
            
            # Download and decompress
            response = requests.get(file_url, timeout=300)
            response.raise_for_status()
            xml_data = gzip.decompress(response.content)
            
            # Parse NeTEx XML
            root = ET.fromstring(xml_data)
            
            # NeTEx namespace
            ns = {'netex': 'http://www.netex.org.uk/netex'}
            
            operator_data = {
                "stops": [],
                "lines": [],
                "vehicles": []
            }
            
            # Extract stops
            for stop_place in root.findall('.//netex:StopPlace', ns):
                try:
                    code = stop_place.get('id')
                    name_elem = stop_place.find('.//netex:Name', ns)
                    name = name_elem.text if name_elem is not None else code
                    
                    if code and name:
                        # Get coordinates
                        lat = lon = None
                        location = stop_place.find('.//netex:Location', ns)
                        if location is not None:
                            lat_elem = location.find('.//netex:Latitude', ns)
                            lon_elem = location.find('.//netex:Longitude', ns)
                            if lat_elem is not None and lon_elem is not None:
                                try:
                                    lat = float(lat_elem.text)
                                    lon = float(lon_elem.text)
                                except ValueError:
                                    pass
                        
                        # Get municipality if available
                        municipality = ""
                        locality = stop_place.find('.//netex:LocalityRef', ns)
                        if locality is not None:
                            municipality = locality.get('ref', '')
                        
                        stop_data = {
                            "code": code,
                            "name": name,
                            "municipality": municipality,
                            "lat": lat,
                            "lon": lon,
                            "stop_type": "bus",
                            "operator": operator
                        }
                        operator_data["stops"].append(stop_data)
                        
                        # Create StopInfo object
                        stop = StopInfo(**stop_data)
                        self.stops[code] = stop
                
                except Exception as e:
                    continue  # Skip problematic stops
            
            # Extract lines
            for line in root.findall('.//netex:Line', ns):
                try:
                    line_id = line.get('id')
                    public_code = line.get('PublicCode') or line_id
                    name_elem = line.find('.//netex:Name', ns)
                    line_name = name_elem.text if name_elem is not None else ""
                    
                    if line_id:
                        line_data = {
                            "operator_code": operator,
                            "line_number": public_code,
                            "line_name": line_name,
                            "transport_type": "bus"
                        }
                        operator_data["lines"].append(line_data)
                        
                        # Create LineInfo object
                        if operator not in self.lines:
                            self.lines[operator] = {}
                        line_info = LineInfo(**line_data)
                        self.lines[operator][public_code] = line_info
                
                except Exception as e:
                    continue  # Skip problematic lines
            
            # Save to cache
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(operator_data, f, indent=2, ensure_ascii=False)
            
            print(f"Loaded {len(operator_data['stops'])} stops and {len(operator_data['lines'])} lines for {operator}")
            
        except Exception as e:
            print(f"Error loading NeTEx data for {operator}: {e}")
    
    def _load_cached_netex_data(self, operator, cached_data):
        """Load cached NeTEx data into memory"""
        # Load stops
        for stop_data in cached_data.get("stops", []):
            if stop_data.get('code'):
                stop = StopInfo(**stop_data)
                self.stops[stop.code] = stop
        
        # Load lines
        if operator not in self.lines:
            self.lines[operator] = {}
        for line_data in cached_data.get("lines", []):
            if line_data.get('line_number'):
                line_info = LineInfo(**line_data)
                self.lines[operator][line_data['line_number']] = line_info
        
        # Load vehicles (if any)
        for vehicle_data in cached_data.get("vehicles", []):
            if vehicle_data.get('vehicle_id'):
                vehicle_info = VehicleInfo(**vehicle_data)
                self.vehicles[vehicle_data['vehicle_id']] = vehicle_info
    
    def get_stop_info(self, stop_id):
        """Get information about a specific stop"""
        return self.stops.get(stop_id)
    
    def get_stop_name(self, stop_id):
        """Get the name of a stop"""
        stop_info = self.get_stop_info(stop_id)
        if stop_info:
            return stop_info.name
        return stop_id
    
    def get_line_info(self, operator, line_id):
        """Get information about a specific line"""
        operator_lines = self.lines.get(operator, {})
        
        # Try exact match first
        if line_id in operator_lines:
            return operator_lines[line_id]
        
        # Try fuzzy matching for line numbers (e.g., "23117" should match "ARR:Line:23117#BW:P974")
        for stored_line_id, line_info in operator_lines.items():
            # Extract the numeric part after "Line:" and before "#"
            if ":Line:" in stored_line_id:
                try:
                    # Extract line number from stored format like "ARR:Line:23117#BW:P974"
                    line_part = stored_line_id.split(":Line:")[-1].split("#")[0]
                    if line_part == line_id:
                        return line_info
                except:
                    continue
        
        return None
    
    def get_line_name(self, operator, line_id):
        """Get the name/description of a line"""
        line_info = self.get_line_info(operator, line_id)
        if line_info:
            return line_info.line_name
        return None
    
    def get_vehicle_info(self, vehicle_id):
        """Get information about a specific vehicle"""
        return self.vehicles.get(vehicle_id)
    
    def enrich_vehicle(self, vehicle):
        """Add reference data to a vehicle object"""
        # Add stop name if available
        if hasattr(vehicle, 'stop') and vehicle.stop != 'N/A':
            stop_info = self.get_stop_info(vehicle.stop)
            if stop_info:
                vehicle.stop_name = stop_info.name
                vehicle.stop_municipality = stop_info.municipality
        
        # Add line name if available and we know the operator
        if hasattr(vehicle, 'line') and hasattr(vehicle, '_operator'):
            line_name = self.get_line_name(vehicle._operator, vehicle.line)
            if line_name:
                vehicle.line_name = line_name
        
        return vehicle
    
    def get_stats(self):
        """Get statistics about loaded reference data"""
        return {
            "stops": len(self.stops),
            "lines_by_operator": {op: len(lines) for op, lines in self.lines.items()},
            "vehicles": len(self.vehicles),
            "last_update": self.last_update.isoformat() if self.last_update else None
        }
    
    def shutdown(self):
        """Shutdown the reference data system"""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=5)