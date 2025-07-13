import csv
import json
from datetime import datetime
from typing import List, Dict, Any
import os

class VehicleExporter:
    """Export vehicle data to various formats for analysis"""
    
    def __init__(self, output_dir="exports"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
    
    def export_bison_tmi8_sets(self, vehicles, filename_prefix=None):
        """Export three BISON TMI8 compliant CSV files according to specification"""
        if filename_prefix is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename_prefix = f"bison_tmi8_{timestamp}"
        
        results = {}
        
        # 1. Future journeys (not implemented in current system - will be empty)
        results['future'] = self._export_future_journeys(f"{filename_prefix}_future_journeys.csv")
        
        # 2. Active journeys (initialized + delay tracking)
        results['active'] = self._export_active_journeys(vehicles, f"{filename_prefix}_active_journeys.csv")
        
        # 3. Finished journeys (completed or cancelled)
        results['finished'] = self._export_finished_journeys(vehicles, f"{filename_prefix}_finished_journeys.csv")
        
        return results
    
    def _export_future_journeys(self, filename):
        """Export future journeys CSV (placeholder - not implemented)"""
        filepath = os.path.join(self.output_dir, filename)
        
        headers = [
            'journey_id', 'vehicle_id', 'line', 'line_name', 'planned_start_time',
            'planned_end_time', 'route_description', 'operator', 'status'
        ]
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(headers)
                # No future journey data available in current implementation
                writer.writerow(['# Future journeys not implemented in current system'])
            
            return filepath, 0
        
        except Exception as e:
            print(f"Error exporting future journeys: {e}")
            return None, 0
    
    def _export_active_journeys(self, vehicles, filename):
        """Export active journeys CSV (initialized + active vehicles with delay tracking)"""
        filepath = os.path.join(self.output_dir, filename)
        
        headers = [
            'vehicle_id', 'journey_id', 'line', 'line_name', 'status', 'current_stop', 
            'stop_name', 'stop_municipality', 'occupancy', 'latitude', 'longitude',
            'init_timestamp', 'delay_seconds', 'delay_minutes', 'last_update', 
            'operator', 'topic', 'message_type'
        ]
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(headers)
                
                # Get both initialized and active vehicles
                initialized_vehicles = vehicles.initialized_vehicles.items()
                active_vehicles = vehicles.active_vehicles.items()
                
                count = 0
                
                # Write initialized vehicles
                for vehicle_id, vehicle in initialized_vehicles:
                    delay_minutes = vehicle.delay_seconds / 60 if vehicle.delay_seconds else 0
                    row = [
                        vehicle_id,
                        vehicle.journey,
                        vehicle.line,
                        getattr(vehicle, 'line_name', ''),
                        vehicle.status,
                        vehicle.stop,
                        getattr(vehicle, 'stop_name', ''),
                        getattr(vehicle, 'stop_municipality', ''),
                        vehicle.occupancy,
                        vehicle.lat,
                        vehicle.lon,
                        getattr(vehicle, 'init_timestamp', ''),
                        vehicle.delay_seconds or 0,
                        delay_minutes,
                        vehicle.last_update,
                        getattr(vehicle, '_operator', ''),
                        getattr(vehicle, '_topic', ''),
                        getattr(vehicle, '_message_type', '')
                    ]
                    writer.writerow(row)
                    count += 1
                
                # Write active vehicles
                for vehicle_id, vehicle in active_vehicles:
                    delay_minutes = vehicle.delay_seconds / 60 if vehicle.delay_seconds else 0
                    row = [
                        vehicle_id,
                        vehicle.journey,
                        vehicle.line,
                        getattr(vehicle, 'line_name', ''),
                        vehicle.status,
                        vehicle.stop,
                        getattr(vehicle, 'stop_name', ''),
                        getattr(vehicle, 'stop_municipality', ''),
                        vehicle.occupancy,
                        vehicle.lat,
                        vehicle.lon,
                        getattr(vehicle, 'init_timestamp', ''),
                        vehicle.delay_seconds or 0,
                        delay_minutes,
                        vehicle.last_update,
                        getattr(vehicle, '_operator', ''),
                        getattr(vehicle, '_topic', ''),
                        getattr(vehicle, '_message_type', '')
                    ]
                    writer.writerow(row)
                    count += 1
            
            return filepath, count
        
        except Exception as e:
            print(f"Error exporting active journeys: {e}")
            return None, 0
    
    def _export_finished_journeys(self, vehicles, filename):
        """Export finished journeys CSV (completed or cancelled with timestamps)"""
        filepath = os.path.join(self.output_dir, filename)
        
        headers = [
            'vehicle_id', 'journey_id', 'line', 'line_name', 'finish_status', 
            'finish_reason', 'final_stop', 'stop_name', 'stop_municipality',
            'occupancy', 'latitude', 'longitude', 'init_timestamp', 
            'finish_timestamp', 'journey_duration', 'delay_seconds', 
            'last_update', 'operator', 'topic', 'message_type'
        ]
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(headers)
                
                count = 0
                for vehicle_id, vehicle in vehicles.finished_vehicles.items():
                    # Calculate journey duration if both timestamps are available
                    journey_duration = ""
                    if vehicle.init_timestamp and vehicle.finish_timestamp:
                        try:
                            init_dt = datetime.fromisoformat(vehicle.init_timestamp.replace('Z', '+00:00'))
                            finish_dt = datetime.fromisoformat(vehicle.finish_timestamp.replace('Z', '+00:00'))
                            duration = finish_dt - init_dt
                            journey_duration = str(duration.total_seconds() / 60)  # Duration in minutes
                        except:
                            journey_duration = "N/A"
                    
                    row = [
                        vehicle_id,
                        vehicle.journey,
                        vehicle.line,
                        getattr(vehicle, 'line_name', ''),
                        vehicle.status,
                        getattr(vehicle, 'finish_reason', vehicle.status),
                        vehicle.stop,
                        getattr(vehicle, 'stop_name', ''),
                        getattr(vehicle, 'stop_municipality', ''),
                        vehicle.occupancy,
                        vehicle.lat,
                        vehicle.lon,
                        getattr(vehicle, 'init_timestamp', ''),
                        getattr(vehicle, 'finish_timestamp', ''),
                        journey_duration,
                        vehicle.delay_seconds or 0,
                        vehicle.last_update,
                        getattr(vehicle, '_operator', ''),
                        getattr(vehicle, '_topic', ''),
                        getattr(vehicle, '_message_type', '')
                    ]
                    writer.writerow(row)
                    count += 1
            
            return filepath, count
        
        except Exception as e:
            print(f"Error exporting finished journeys: {e}")
            return None, 0
    
    def export_to_csv(self, vehicles, filename=None):
        """Export all vehicles to CSV file (legacy method)"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"active_vehicles_{timestamp}.csv"
        
        filepath = os.path.join(self.output_dir, filename)
        
        # Define CSV headers
        headers = [
            'vehicle_id', 'line', 'line_name', 'status', 'stop', 'stop_name', 
            'stop_municipality', 'occupancy', 'latitude', 'longitude', 
            'last_update', 'operator', 'topic', 'message_type'
        ]
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(headers)
                
                # Write vehicle data
                for vehicle_id, vehicle in vehicles.get_all_vehicles():
                    row = [
                        vehicle_id,
                        vehicle.line,
                        getattr(vehicle, 'line_name', ''),
                        vehicle.status,
                        vehicle.stop,
                        getattr(vehicle, 'stop_name', ''),
                        getattr(vehicle, 'stop_municipality', ''),
                        vehicle.occupancy,
                        vehicle.lat,
                        vehicle.lon,
                        vehicle.last_update,
                        getattr(vehicle, '_operator', ''),
                        getattr(vehicle, '_topic', ''),
                        getattr(vehicle, '_message_type', '')
                    ]
                    writer.writerow(row)
            
            return filepath, len(vehicles)
        
        except Exception as e:
            print(f"Error exporting to CSV: {e}")
            return None, 0
    
    def export_to_json(self, vehicles, filename=None):
        """Export all vehicles to JSON file for detailed analysis"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"active_vehicles_{timestamp}.json"
        
        filepath = os.path.join(self.output_dir, filename)
        
        try:
            vehicle_data = []
            for vehicle_id, vehicle in vehicles.get_all_vehicles():
                vehicle_dict = {
                    'vehicle_id': vehicle_id,
                    'line': vehicle.line,
                    'line_name': getattr(vehicle, 'line_name', ''),
                    'status': vehicle.status,
                    'stop': vehicle.stop,
                    'stop_name': getattr(vehicle, 'stop_name', ''),
                    'stop_municipality': getattr(vehicle, 'stop_municipality', ''),
                    'occupancy': vehicle.occupancy,
                    'coordinates': {
                        'latitude': vehicle.lat,
                        'longitude': vehicle.lon
                    },
                    'last_update': vehicle.last_update,
                    'metadata': {
                        'operator': getattr(vehicle, '_operator', ''),
                        'topic': getattr(vehicle, '_topic', ''),
                        'message_type': getattr(vehicle, '_message_type', '')
                    }
                }
                vehicle_data.append(vehicle_dict)
            
            export_data = {
                'export_timestamp': datetime.now().isoformat(),
                'total_vehicles': len(vehicle_data),
                'vehicles': vehicle_data
            }
            
            with open(filepath, 'w', encoding='utf-8') as jsonfile:
                json.dump(export_data, jsonfile, indent=2, ensure_ascii=False)
            
            return filepath, len(vehicles)
        
        except Exception as e:
            print(f"Error exporting to JSON: {e}")
            return None, 0
    
    def export_summary_stats(self, vehicles, filename=None):
        """Export summary statistics to CSV"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"vehicle_summary_{timestamp}.csv"
        
        filepath = os.path.join(self.output_dir, filename)
        
        try:
            # Collect statistics
            stats = {
                'by_status': {},
                'by_line': {},
                'by_operator': {},
                'by_occupancy': {}
            }
            
            for vehicle_id, vehicle in vehicles.get_all_vehicles():
                # Count by status
                stats['by_status'][vehicle.status] = stats['by_status'].get(vehicle.status, 0) + 1
                
                # Count by line
                stats['by_line'][vehicle.line] = stats['by_line'].get(vehicle.line, 0) + 1
                
                # Count by operator
                operator = getattr(vehicle, '_operator', 'unknown')
                stats['by_operator'][operator] = stats['by_operator'].get(operator, 0) + 1
                
                # Count by occupancy
                stats['by_occupancy'][vehicle.occupancy] = stats['by_occupancy'].get(vehicle.occupancy, 0) + 1
            
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write status summary
                writer.writerow(['Status Summary'])
                writer.writerow(['Status', 'Count'])
                for status, count in sorted(stats['by_status'].items()):
                    writer.writerow([status, count])
                writer.writerow([])
                
                # Write line summary
                writer.writerow(['Line Summary'])
                writer.writerow(['Line', 'Count'])
                for line, count in sorted(stats['by_line'].items()):
                    writer.writerow([line, count])
                writer.writerow([])
                
                # Write operator summary
                writer.writerow(['Operator Summary'])
                writer.writerow(['Operator', 'Count'])
                for operator, count in sorted(stats['by_operator'].items()):
                    writer.writerow([operator, count])
                writer.writerow([])
                
                # Write occupancy summary
                writer.writerow(['Occupancy Summary'])
                writer.writerow(['Occupancy', 'Count'])
                for occupancy, count in sorted(stats['by_occupancy'].items()):
                    writer.writerow([occupancy, count])
            
            return filepath, len(vehicles)
        
        except Exception as e:
            print(f"Error exporting summary stats: {e}")
            return None, 0