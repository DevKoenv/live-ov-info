# Live OV Info

A terminal-based application for displaying real-time public transport information from the Dutch NDOV Loket feed.

## Features

- **Multi-Operator Support**: Monitor all Dutch public transport operators (Arriva, Connexxion, GVB, HTM, NS, RET, Syntus, Veolia, Qbuzz)
- **Real-time Vehicle Tracking**: Live position updates with occupancy information
- **Dynamic Reference Data**: Automatically downloads and caches stop names and locations from NDOV feeds
- **Terminal Interface**: Rich, colored terminal display with live updates
- **Flexible Filtering**: Filter by line number, operator, or custom topics
- **Debug & Analysis**: Save messages for analysis and generate XML schema documentation

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python main.py
```

## Usage

### Monitor All Operators
```bash
python main.py --all-operators
```

### Monitor Specific Operators
```bash
python main.py --operators arriva connexxion gvb
```

### Filter by Line Number
```bash
python main.py --line 300
```

### Custom ZeroMQ Topics
```bash
python main.py --topics "/GVB/KV6posinfo" "/ARR/KV15messages"
```

### Disable Reference Data Loading
```bash
python main.py --no-reference-data
```

### Enable Debugging and Schema Generation
```bash
python main.py --debug --save-messages --schema
```

## Available Operators

- **arriva** - Regional buses (`/ARR/`)
- **connexxion** - Regional and city buses (`/CXX/`)
- **gvb** - Amsterdam public transport (`/GVB/`)
- **htm** - The Hague public transport (`/HTM/`)
- **ns** - Dutch Railways (`/NS/`)
- **ret** - Rotterdam public transport (`/RET/`)
- **syntus** - Regional transport (`/SYN/`)
- **veolia** - Regional transport (`/VTN/`)
- **qbuzz** - Regional buses (`/QBUZZ/`)

## Message Types

- **KV6posinfo** - Real-time vehicle positions (default)
- **KV15messages** - Service disruptions and messages
- **KV17cvlinfo** - Service information
- **KV8** - Journey planning info
- **KV7** - Journey times

## Data Sources

### Automatic Reference Data
The application fetches reference data from official NDOV sources:

1. **CHB Stops**: `https://data.ndovloket.nl/haltes/` - Legacy stop database (all operators)
2. **NeTEx Data**: `https://data.ndovloket.nl/netex/[operator]/` - Per-operator stops and lines
3. **Real-time Feed**: `tcp://pubsub.besteffort.ndovloket.nl:7658` - Live vehicle data

### Why Not TMF?
The original code referenced `www.tmf.nl` which doesn't exist. The correct sources are the NDOV Loket feeds listed above.

## Project Structure

```
live-ov-info/
├── main.py                 # Enhanced main application
├── src/
│   ├── data/               # Data models and processing
│   │   ├── models.py       # Vehicle and collection models
│   │   ├── parser.py       # XML parsing and message handling
│   │   └── references.py   # Dynamic reference data from NDOV
│   ├── network/            # Network connectivity
│   │   └── client.py       # Multi-operator ZeroMQ client
│   └── ui/                 # User interface
│       └── terminal.py     # Rich terminal display
├── cache/                  # Reference data cache (auto-created)
├── debug_messages/         # Debug output (when enabled)
└── requirements.txt        # Python dependencies
```

## Features Explained

### Multi-Operator Support
```bash
# Single operator (default: Arriva)
python main.py --operators arriva

# Multiple operators
python main.py --operators arriva qbuzz connexxion

# All operators
python main.py --all-operators
```

### Reference Data Integration
- Automatically downloads and caches stop names from NDOV feeds
- 24-hour cache for performance
- Enriches vehicle displays with human-readable information
- Background updates every 24 hours

### Advanced Terminal UI
- Color-coded vehicle status (ARRIVAL, DEPARTURE, ONROUTE, ONSTOP)
- Full-width table with vertical dividers between columns
- Multi-line support for long line names and stop names
- Live statistics (messages received, operators active)
- Real-time error reporting
- Reduced flickering with smart status caching

## Example Commands

```bash
# Monitor Amsterdam public transport only
python main.py --operators gvb

# All operators with line 1 filter
python main.py --all-operators --line 1

# Debug mode with message saving
python main.py --debug --save-messages --operators arriva

# Multiple message types from Arriva
python main.py --operators arriva --message-types KV6posinfo KV15messages

# Custom topics
python main.py --topics "/ARR/KV6posinfo" "/GVB/KV6posinfo"

# Fast startup without reference data
python main.py --no-reference-data --operators ns
```

## Development

### Adding New Operators
Update the `OPERATORS` dictionary in `src/network/client.py`:
```python
OPERATORS = {
    'new_operator': '/NEW/',
    # ... existing operators
}
```

### Extending Data Sources
Add new reference data sources in `src/data/references.py`:
```python
NETEX_SOURCES = {
    "new_operator": "https://data.ndovloket.nl/netex/new/",
    # ... existing sources
}
```

### Custom Message Processing
Extend message processing in `src/data/parser.py` for new KV message types.

## Troubleshooting

### No Vehicles Displayed
- Check if the operator is active (some don't run 24/7)
- Verify line number exists for the operator
- Try `--debug` to see raw messages

### Reference Data Issues
- Check internet connection for NDOV downloads
- Clear cache directory if data seems outdated
- Use `--no-reference-data` to skip downloads

### Connection Issues
- Verify firewall allows outbound TCP connections
- NDOV feed may be temporarily unavailable
- Try different operators if one is not responding
