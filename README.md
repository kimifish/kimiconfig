# kimiconfig

A flexible configuration management system for Python applications.

[![PyPI version](https://badge.fury.io/py/kimiconfig.svg)](https://badge.fury.io/py/kimiconfig)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/pypi/pyversions/kimiconfig.svg)](https://pypi.org/project/kimiconfig/)
[![Downloads](https://static.pepy.tech/badge/kimiconfig)](https://pepy.tech/project/kimiconfig)

## Description

`kimiconfig` is a powerful yet easy-to-use library for managing configurations in your Python projects. It allows you to load settings from various sources, such as YAML/JSON files, environment variables, and command-line arguments, merging them into a single configuration object. The library also supports dataclass integration, monitoring configuration file changes, and much more.

## Key Features

* **Multiple Configuration Sources**: Load settings from YAML/JSON files, environment variables, and command-line arguments.
* **Hierarchical Overrides**: Settings from later sources override settings from earlier ones.
* **Singleton Pattern**: Ensures a single instance of the configuration object throughout the application.
* **Dataclass Integration**: Automatically convert nested dictionaries to dataclasses for improved type hinting and convenient access.
* **File Change Monitoring**: Automatically reload configuration when files change (optional).
* **Deep Dictionary Updates**: Correctly merge nested data structures.
* **Configuration Validation**: Check for the presence of required keys in the configuration.
* **Save Configuration**: Ability to save the current configuration to a file.
* **Formatted Output**: Conveniently display the current configuration using Rich (optional).
* **Environment Variable Prefix Support**: Easily configure a prefix for environment variables.
* **Command-Line Argument Processing**: Supports both full (`--key=value`) and short (`-k`) flags.
* **Callback Registration**: Ability to register functions to be called after configuration updates.

## Installation

You can install `kimiconfig` using pip:

```bash
git clone https://github.com/kimifish/kimiconfig
cd kimiconfig
pip install .
```

To include optional Rich support for formatted output:

```bash
pip install ".[full]"
```

## Usage

### Basic Usage

Create a `config.yaml` file:

```yaml
host: "localhost"
port: 8080
debug: true

database:
  type: "sqlite"
  file: "app.db"
```

In your Python code:

```python
from kimiconfig import Config

# Initialize with a single config file
cfg = Config('config.yaml')

print(cfg.host)  # Output: localhost
print(cfg.port)  # Output: 8080
print(cfg.database.type) # Output: sqlite

# Access nested values
if cfg.debug:
    print("Debug mode is ON")

# Values can also be accessed like a dictionary
print(cfg.data['database']['file']) # Output: app.db
# or
from dataclasses import asdict
print(asdict(cfg.database)['file'])
```

### Multiple Configuration Files

Settings from later files will override earlier ones.

`base.yaml`:

```yaml
service_name: "My Awesome App"
logging:
  level: "INFO"
```

`override.yaml`:

```yaml
logging:
  level: "DEBUG" # This will override the level from base.yaml
  format: "%(asctime)s - %(levelname)s - %(message)s"
```

```python
from kimiconfig import Config

cfg = Config(['base.yaml', 'override.yaml'])

print(cfg.service_name)  # Output: My Awesome App
print(cfg.logging.level)   # Output: DEBUG
print(cfg.logging.format)  # Output: %(asctime)s - %(levelname)s - %(message)s
```

### Environment Variables

Environment variables can override file configurations. By default, `kimiconfig` looks for variables prefixed with `DEFAULT_APP_`. You can change this prefix. Use double underscores `__` (or just dots if your OS supports) to denote nesting.

```bash
export DEFAULT_APP_PORT=9000
export DEFAULT_APP_DATABASE__TYPE="postgresql"
```

```python
from kimiconfig import Config

# Assuming config.yaml from the first example
cfg = Config('config.yaml', env_prefix='DEFAULT_APP_')

print(cfg.port)  # Output: 9000 (overridden by env var)
print(cfg.database.type) # Output: postgresql (overridden by env var)
print(cfg.host) # Output: localhost (from config.yaml)
```

### Command-Line Arguments

Command-line arguments have the highest precedence.

```python
import sys
from kimiconfig import Config

# Simulate command line arguments: ['--debug=false', '--database.file=prod.db']
# In a real script, sys.argv[1:] would be used.
cli_args = ['--debug=false', '--database.file=prod.db']

cfg = Config('config.yaml', args=cli_args)

print(cfg.debug) # Output: False
print(cfg.database.file) # Output: prod.db
```

### File Change Monitoring

Enable `watch_mtime=True` to automatically reload the configuration if any of the source files are modified.

```python
from kimiconfig import Config
import time

cfg = Config('config.yaml', watch_mtime=True, watch_interval=5) # Check every 5 seconds

print(f"Initial port: {cfg.port}")

# Modify config.yaml (e.g., change port to 8888)
# Wait for more than 'watch_interval' seconds
time.sleep(10)

print(f"Updated port: {cfg.port}") # Should show the new port if file was changed
```

### Registering Update Callbacks

You can register functions to be executed after the configuration is updated (e.g., due to file changes).

```python
from kimiconfig import Config
import time

def on_config_updated():
    print("Configuration has been updated!")
    # Re-initialize services or apply new settings
    # For example, if logging level changed:
    # setup_logging(cfg.logging.level)

cfg = Config('config.yaml', watch_mtime=True)
cfg.register_update_callback(on_config_updated)

# ... (rest of your application)
# If config.yaml changes, on_config_updated will be called.
```

### Validating Configuration

Ensure that specific keys exist in your configuration.

```python
from kimiconfig import Config

cfg = Config('config.yaml')

try:
    cfg.validate_config([
        "host",
        "port",
        "database.type",
        "database.file",
        "non_existent_key" # This will cause an error
    ])
except ValueError as e:
    print(f"Configuration validation error: {e}")
    # Output: Configuration validation error: Missing configuration keys: non_existent_key
```

Wildcards (`%`) can be used for validating nested structures:

```python
# Assuming a config like:
# servers:
#   server1:
#     address: "192.168.1.1"
#   server2:
#     address: "192.168.1.2"
cfg.validate_config(["servers.%.address"]) # Checks if all items under 'servers' have an 'address'
```

### Saving Configuration

Save the current merged configuration to a new file.

```python
from kimiconfig import Config

cfg = Config('config.yaml')
# ... potentially load from env, args, or update runtime ...
cfg.update("new_setting.value", 123)

cfg.save('current_config.yaml') # Saves as YAML
cfg.save('current_config.json', format='json') # Saves as JSON
```

### Printing Configuration (Rich Integration)

If `rich` is installed (`kimiconfig[full]`), you can print a nicely formatted view of the configuration.

```python
from kimiconfig import Config

cfg = Config('config.yaml')
cfg.print_config()
# Or get the table as a string
# table_str = cfg.get_table_view()
# print(table_str)
```

## Configuration Loading Order (Precedence)

1. **Runtime Updates**: Values set using `cfg.update()`
2. **Command-Line Arguments**: Parsed from `args`
3. **Environment Variables**: Loaded based on `env_prefix`
4. **Configuration Files**: Loaded in the order specified. Later files override earlier ones.
5. **Default Values**: (If you structure your code to provide defaults before loading `kimiconfig`)

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue.

1. Fork the repository.
2. Create your feature branch (`git checkout -b feature/AmazingFeature`).
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
