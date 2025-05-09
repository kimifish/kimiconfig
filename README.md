# kimiConfig

A flexible configuration management system for Python applications with support for multiple data sources.

## Key Features

- Support for multiple YAML configuration files with hierarchical overrides
- Command line arguments integration
- Environment variables support
- Automatic file change monitoring
- Dataclass conversion for nested structures
- Rich formatting for configuration display
- Deep dictionary updates
- Runtime configuration updates

## Installation

```bash
pip install kimiconfig
```

## Basic Usage Examples

```python
from kimiconfig import Config

# Basic usage
cfg = Config('config.yaml')
print(cfg.host)  # Access config values as attributes

# Multiple config files
cfg = Config(['base.yaml', 'override.yaml'])

# With CLI args and file watching
cfg = Config('config.yaml', 
            args=['--port=8080'],
            watch_mtime=True)

# Using dataclasses for nested configs
cfg = Config('config.yaml', use_dataclasses=True)
print(cfg.database.host)  # Type hints work

# Runtime updates
cfg.update('server.port', 9000)
```

## Documentation

Detailed documentation is available in the module's docstrings.

## License

MIT 