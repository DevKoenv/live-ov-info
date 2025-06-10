import zmq
import time
from typing import Tuple, List, Dict, Any, Optional
from datetime import datetime
import collections

from ..data.parser import extract_xml_from_binary, parse_kv6_message

# NDOV ZeroMQ endpoints and operator configuration
NDOV_ENDPOINTS = {
    "realtime": {
        "host": "pubsub.besteffort.ndovloket.nl",
        "port": 7658,
        "description": "Real-time vehicle positions and service info"
    },
    # Add other endpoints when discovered
}

# Operator mappings based on REALTIME.TXT
OPERATORS = {
    'arriva': '/ARR/',
    'connexxion': '/CXX/',
    'gvb': '/GVB/',  # Amsterdam
    'htm': '/HTM/',  # Den Haag
    'ns': '/NS/',    # Nederlandse Spoorwegen
    'ret': '/RET/',  # Rotterdam
    'syntus': '/SYN/',
    'veolia': '/VTN/',  # Veolia Transport Nederland
    'qbuzz': '/QBUZZ/',
}

# Available message types
MESSAGE_TYPES = [
    'KV6posinfo',  # Vehicle positions
    'KV8',         # Journey planning
    'KV17cvlinfo', # Service messages
    'KV15messages',# Disruptions
    'KV7',         # Journey times
]

class NDOVClient:
    """Enhanced client for connecting to multiple NDOV Loket ZeroMQ feeds"""
    
    def __init__(self, topics=None, endpoint="realtime"):
        """Initialize client with specific topics and endpoint"""
        if topics is None:
            topics = ["/ARR/KV6posinfo"]  # Default to Arriva positions
        elif isinstance(topics, str):
            topics = [topics]
        
        self.topics = topics
        self.endpoint = endpoint
        self.endpoint_config = NDOV_ENDPOINTS.get(endpoint)
        
        if not self.endpoint_config:
            raise ValueError(f"Unknown endpoint: {endpoint}")
        
        self.context = None
        self.socket = None
        self.connected = False
        self.stats = {
            "xml_messages": 0,
            "binary_messages": 0,
            "invalid_xml": 0,
            "vehicle_updates": 0,
            "total_messages": 0,
            "messages_by_operator": {}
        }
        self.recent_errors = collections.deque(maxlen=5)
    
    @classmethod
    def for_arriva(cls, message_types=None):
        """Create client specifically for Arriva with specified message types"""
        if message_types is None:
            message_types = ["KV6posinfo"]
        elif isinstance(message_types, str):
            message_types = [message_types]
        
        topics = [f"/ARR/{msg_type}" for msg_type in message_types]
        return cls(topics=topics)
    
    @classmethod
    def for_operator(cls, operator, message_types=None):
        """Create client for a specific operator"""
        if operator.lower() not in OPERATORS:
            raise ValueError(f"Unknown operator: {operator}. Available: {list(OPERATORS.keys())}")
        
        if message_types is None:
            message_types = ["KV6posinfo"]
        elif isinstance(message_types, str):
            message_types = [message_types]
        
        operator_prefix = OPERATORS[operator.lower()]
        topics = [f"{operator_prefix}{msg_type}" for msg_type in message_types]
        return cls(topics=topics)
    
    @classmethod
    def for_multiple_operators(cls, operators, message_type="KV6posinfo"):
        """Create client for multiple operators with same message type"""
        topics = []
        for operator in operators:
            if operator.lower() not in OPERATORS:
                print(f"Warning: Unknown operator '{operator}', skipping")
                continue
            topic = f"{OPERATORS[operator.lower()]}{message_type}"
            topics.append(topic)
        
        if not topics:
            raise ValueError("No valid operators provided")
        
        return cls(topics=topics)
    
    def connect(self):
        """Connect to the NDOV Loket ZeroMQ feed"""
        try:
            self.context = zmq.Context()
            self.socket = self.context.socket(zmq.SUB)
            
            # Connect to the configured endpoint
            endpoint_url = f"tcp://{self.endpoint_config['host']}:{self.endpoint_config['port']}"
            self.socket.connect(endpoint_url)
            
            # Subscribe to all specified topics
            for topic in self.topics:
                self.socket.setsockopt_string(zmq.SUBSCRIBE, topic)
                print(f"Subscribed to: {topic}")
            
            self.connected = True
            print(f"Connected to {endpoint_url}")
            return True
        except Exception as e:
            self.record_error(f"Connection error: {e}")
            return False
    
    def record_error(self, error_message):
        """Record an error message and write it to a file, with session dividers."""
        error_time = datetime.now().strftime("%H:%M:%S")
        formatted_error = f"[{error_time}] {error_message}"
        self.recent_errors.append(formatted_error)
        try:
            log_file = "ndov_client_errors.log"
            # Add a divider if this is the first error in this session
            if not hasattr(self, "_error_log_initialized"):
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write("\n" + "="*40 + f" NEW SESSION {datetime.now().isoformat()} " + "="*40 + "\n")
                self._error_log_initialized = True
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(formatted_error + "\n")
        except Exception:
            pass
    
    def _extract_operator_from_topic(self, topic_bytes):
        """Extract operator code from topic"""
        try:
            topic_str = topic_bytes.decode('utf-8')
            for operator, prefix in OPERATORS.items():
                if topic_str.startswith(prefix):
                    return operator
            return "unknown"
        except:
            return "unknown"
    
    def receive_message(self, timeout=100) -> Tuple[Optional[bytes], Optional[bytes]]:
        """Receive a message from the ZeroMQ feed"""
        if not self.connected or not self.socket:
            self.record_error("Not connected to ZeroMQ feed")
            return None, None
        
        try:
            # Set a timeout for receiving messages
            if self.socket.poll(timeout):
                self.stats["total_messages"] += 1
                
                # Receive multipart message
                message_parts = self.socket.recv_multipart()
                
                # Usually, first part is topic, second is body
                topic = message_parts[0]
                body = message_parts[1] if len(message_parts) > 1 else b''
                
                # Track messages by operator
                operator = self._extract_operator_from_topic(topic)
                self.stats["messages_by_operator"][operator] = self.stats["messages_by_operator"].get(operator, 0) + 1
                
                return topic, body
        except zmq.ZMQError as e:
            self.record_error(f"ZMQ error: {e}")
        except Exception as e:
            self.record_error(f"Error receiving message: {e}")
        
        return None, None
    
    def process_message(self, topic: bytes, body: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Process a message body and extract data"""
        # Extract XML content from binary data
        xml_content = extract_xml_from_binary(body)
        
        if xml_content:
            self.stats["xml_messages"] += 1
            
            # Parse the XML message
            messages, parse_stats = parse_kv6_message(xml_content)
            
            if parse_stats["parsed"]:
                # Add topic info to each message for operator identification
                operator = self._extract_operator_from_topic(topic)
                for msg in messages:
                    msg['_operator'] = operator
                    msg['_topic'] = topic.decode('utf-8', errors='replace')
                
                self.stats["vehicle_updates"] += len(messages)
                
                # Handle unknown message types
                if parse_stats.get("unknown_types"):
                    unknown_list = ", ".join(parse_stats["unknown_types"])
                    self.record_error(f"Unknown KV6 message types found: {unknown_list}")
                
                return messages, parse_stats
            else:
                self.stats["invalid_xml"] += 1
                if parse_stats.get("error"):
                    self.record_error(f"XML parsing error: {parse_stats['error']}")
        else:
            # This is probably a control message or non-XML data
            self.stats["binary_messages"] += 1
        
        return [], {"parsed": False}
    
    def get_stats_summary(self):
        """Get a formatted summary of statistics"""
        operator_stats = " | ".join([f"{op}: {count}" for op, count in self.stats["messages_by_operator"].items()])
        return {
            "total": self.stats["total_messages"],
            "xml": self.stats["xml_messages"], 
            "binary": self.stats["binary_messages"],
            "updates": self.stats["vehicle_updates"],
            "by_operator": operator_stats
        }
    
    def disconnect(self):
        """Disconnect from the ZeroMQ feed"""
        if self.socket:
            self.socket.close()
        if self.context:
            self.context.term()
        self.connected = False