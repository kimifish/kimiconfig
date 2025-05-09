"""
Configuration Management Module

This module provides a flexible configuration management system with the following features:
- Singleton pattern implementation
- YAML file loading and monitoring
- Command line arguments support
- Environment variables support 
    (use '__' instead of '.' in env variables to separate sections, 
    though '.' is also supported)
- Dataclass integration
- Deep dictionary updates
- File change monitoring
- Rich formatting output

Example:
    ```python
    from kimiUtils.config import Config
    
    # Basic usage
    cfg = Config('config.yaml')
    print(cfg.host)  # Access config values as attributes
    
    # With dataclasses and file monitoring
    cfg = Config('config.yaml', use_dataclasses=True, watch_mtime=True)
    
    # Multiple config files
    cfg = Config(['base.yaml', 'override.yaml'])
    ```
"""

import os
import time
from typing import Dict, Any, Union, List
import yaml
from dataclasses import make_dataclass, is_dataclass, asdict
import logging
import threading
import json

KEY_COLOR = 'wheat1'
SOURCE_COLOR = 'grey30'

log = logging.getLogger(__name__)


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]



def _parse_args(args: List[str]) -> Dict[str, Any]:
    """
    Parse command line arguments into a dictionary
    
    Args:
        args: List of command line arguments
        
    Returns:
        Dictionary with parsed arguments
    """
    result = {}
    for arg in args:
        if arg.startswith('--'):
            if '=' in arg:
                key, value = arg[2:].split('=', 1)
                if '.' in key:
                    parts = key.split('.')
                    current = result
                    for part in parts[:-1]:
                        if part not in current:
                            current[part] = {}
                        current = current[part]
                    current[parts[-1]] = _convert_value(value)
                else:
                    result[key] = _convert_value(value)
            else:
                result[arg[2:]] = True
        elif arg.startswith('-'):
            result[arg[1:]] = True
    return result


def _convert_value(value: Any) -> Any:
    """
    Convert string values to appropriate types
    
    Args:
        value: Value to convert
        
    Returns:
        Converted value of appropriate type
    """
    if not isinstance(value, str):
        return value
        
    # Check for boolean values
    if value.lower() in ('true', 'yes', 'y', '1'):
        return True
    if value.lower() in ('false', 'no', 'n', '0'):
        return False
    
    # Check for numbers
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


class Config(metaclass=Singleton):
    """
    Configuration management class implementing singleton pattern.
    Provides flexible configuration handling with support for multiple sources and formats.

    Features:
    - Multiple configuration files support with hierarchical overrides
    - Command line arguments integration
    - Environment variables support 
        (use '__' instead of '.' in env variables to separate sections, 
        though '.' is also supported)
    - Automatic file change monitoring
    - Dataclass conversion for nested structures
    - Rich formatting for configuration display
    - Deep dictionary updates
    - Runtime configuration updates
    
    Attributes:
        data (dict): Combined configuration data
        shutdown_flag (bool): Flag to stop the polling thread
                              Can be used as shutdown flag for other threads
    Args:
        file (Union[str, List[str]]): Path(s) to YAML configuration file(s). Later files override earlier ones.
        args (List[str], optional): Command line arguments to parse and apply.
        use_dataclasses (bool): Convert nested dictionaries to dataclasses for better type hints.
        watch_mtime (bool): Enable automatic config reload when files change.
        watch_interval (int): Interval in seconds for checking file modifications.

    Example:
        ```python
        # Basic usage with single config file
        cfg = Config('config.yaml')
        print(cfg.server_host)  # Access as attributes
        
        # Multiple config files with overrides
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

    Note:
        The class implements singleton pattern, so multiple instantiations
        will return the same object. Use _reset() for testing purposes.
    """

    def __init__(self, file: Union[str, List[str]] = '', 
                 args: List[str] = None, 
                 use_dataclasses: bool = False,
                 env_prefix: str = 'DEFAULT_APP_',
                 watch_mtime: bool = False, 
                 watch_interval: int = 15):
        self._use_dataclasses = use_dataclasses
        self.data = {}
        self._file_data = {}
        self._args_data = {}
        self._env_data = {}
        self._runtime_update_data = {}
        self._args = {}
        self.shutdown_flag = False
        self._init_default_logging()
        
        # Convert file to list
        self.files = [file] if isinstance(file, str) and file else \
                    list(file) if file else []
        self.file_stamps = {}
        
        # Load configuration from files
        if self.files:
            for f in self.files:
                if os.path.exists(f):
                    self.file_stamps[f] = os.stat(f).st_mtime
            self._load_from_files()

        # Load configuration from environment variables
        self._load_from_env(env_prefix)
        
        # Process command line arguments
        if args:
            self._args = _parse_args(args)
            self._load_from_args(self._args)
        
        self._update_data_from_all_x_data()._update_attributes_from_data()

        # Start polling in separate thread if enabled
        if watch_mtime:
            self.polling_thread = threading.Thread(
                target=self._config_file_polling_thread,
                args=(watch_interval,)
            )
            self.polling_thread.daemon = True
            self.polling_thread.start()

    def _init_default_logging(self):
        self.logging = {
            'level': "INFO",
            'format': "%(message)s",
            'date_format': "[%X]",
            'markup': True,
            'rich_tracebacks': True,
            'show_time': True,
            'show_path': False 
        }

    def _load_from_args(self, args_dict: Dict[str, Any]) -> None:
        """
        Update configuration from arguments dictionary
        
        Args:
            args_dict: Dictionary with arguments
        """
        for key, value in args_dict.items():
            if '.' in key:
                parts = key.split('.')
                current = {}
                temp = current
                for part in parts[:-1]:
                    temp[part] = {}
                    temp = temp[part]
                temp[parts[-1]] = _convert_value(value)
                self._deep_update(self._args_data, current, 'CLI args')
            else:
                self._deep_update(self._args_data, {key: _convert_value(value)}, 'CLI args')

    def _load_from_env(self, prefix: str = 'DEFAULT_APP_'):
        """Loads configuration from environment variables"""
        env_data = {}
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):].lower().replace('__', '.')
                if '.' in config_key:
                    parts = config_key.split('.')
                    current = env_data
                    for part in parts[:-1]:
                        current = current.setdefault(part, {})
                    current[parts[-1]] = _convert_value(value)
                else:
                    env_data[config_key] = _convert_value(value)
        self._deep_update(self._env_data, env_data, 'environment')

    def _deep_update(self, d: dict, u: dict, source: str = 'unknown') -> None:
        """
        Recursively updates dictionary d with data from dictionary u
        
        Args:
            d: Target dictionary
            u: Source dictionary
            source: Source identifier (file/env/args/runtime)
        """
        for k, v in u.items():
            if isinstance(v, dict):
                d[k] = d.get(k, {})
                if isinstance(d[k], dict):
                    self._deep_update(d[k], v, source)
                else:
                    d[k] = v
            else:
                d[k] = v

    def _load_from_files(self):
        """Loads configuration from all files"""
        self._file_data.clear()
        for file in self.files:
            try:
                with open(file, 'r') as f:
                    if file.lower().endswith(('.yaml', '.yml')):
                        new_data = yaml.safe_load(f) or {}
                    elif file.lower().endswith('.json'):
                        new_data = json.load(f) or {}
                    self._deep_update(self._file_data, new_data, f'{file}')
            except Exception as e:
                log.error(f"Error loading configuration from {file}: {e}")

    def _dict_to_dataclass(self, data: Dict[str, Any], class_name: str = 'ConfigData') -> Any:
        """
        Recursively converts a dictionary to a dataclass.
        
        Args:
            data: Dictionary to convert
            class_name: Name of the created class
            
        Returns:
            Instance of the dataclass
        """
        fields = []
        values = {}
        
        for key, value in data.items():
            # Convert key to string and replace spaces and dots with underscores
            key_str = str(key).translate(str.maketrans({' ': '_', '.': '_', '-': '_'}))
            
            if isinstance(value, dict):
                # Recursively create a dataclass for the nested dictionary
                nested_class_name = f"{class_name}_{key_str}"
                field_type = self._dict_to_dataclass(value, nested_class_name)
                fields.append((key_str, field_type, None))
                values[key_str] = field_type
            else:
                # Use Any for simple types to avoid typing issues
                fields.append((key_str, Any, None))
                values[key_str] = value
        
        # Dynamically create a new dataclass
        dynamic_class = make_dataclass(class_name, fields)
        # Create and return an instance with our values
        return dynamic_class(**values)

    def _update_data_from_all_x_data(self):
        """Updates configuration data"""
        self._deep_update(self.data, self._file_data)  # Order is important as data can be overwritten
        self._deep_update(self.data, self._env_data)
        self._deep_update(self.data, self._args_data)
        self._deep_update(self.data, self._runtime_update_data)
        return self

    def _update_attributes_from_data(self):
        """Updates class attributes from configuration data"""
        if self._use_dataclasses:
            for k, v in self.data.items():
                if isinstance(v, dict):
                    # Create a dataclass directly, without additional calls
                    setattr(self, k, self._dict_to_dataclass(v, f"Config_{k}"))
                else:
                    setattr(self, k, v)
        else:
            for k, v in self.data.items():
                setattr(self, k, v)

    def update(self, key: str, value: Any):
        """Updates a value in the configuration"""
        if '.' in key:
            parts = key.split('.')
            current = {}
            temp = current
            for part in parts[:-1]:
                temp[part] = {}
                temp = temp[part]
            temp[parts[-1]] = value
            self._deep_update(self._runtime_update_data, current, 'runtime_update')
        else:
            self._deep_update(self._runtime_update_data, {key: value}, 'runtime_update')
        self._update_data_from_all_x_data()._update_attributes_from_data()

    def _config_file_polling_thread(self, interval: int):
        """Monitors changes in all configuration files"""
        while not self.shutdown_flag:
            time.sleep(interval)
            reload_needed = False
            
            for file in self.files:
                if not os.path.exists(file):
                    continue
                    
                current_stamp = os.stat(file).st_mtime
                if current_stamp != self.file_stamps.get(file):
                    self.file_stamps[file] = current_stamp
                    reload_needed = True
            
            if reload_needed:
                self._file_data.clear()  # Clear old data
                self._load_from_yaml()  # Reload all files
                self._update_data_from_all_x_data()._update_attributes_from_data()

    def load_files(self, files: List[str]):
        """Loads configuration from files"""
        if isinstance(files, str):
            files = [files]
        self.files.extend(files)
        self._load_from_files()
        self._update_data_from_all_x_data()._update_attributes_from_data()
    
    def load_args(self, args=List[str]):
        if isinstance(args, str):
            args = [args,]
        self._load_from_args(_parse_args(args))
        self._update_data_from_all_x_data()._update_attributes_from_data()

    def shutdown(self):
        """Stops the polling"""
        self.shutdown_flag = True

    def save(self, new_file: str = None, format: str = 'yaml') -> None:
        """Saves the current configuration to a file"""
        try:
            if not new_file:
                new_file = self.file
            with open(new_file, 'w') as f:
                if format == 'yaml':
                    yaml.safe_dump(self.config, f, default_flow_style=False, allow_unicode=True)
                elif format == 'json':
                    json.dump(self.config, f, indent=4)
            log.info(f"Configuration successfully saved to {new_file}")
        except Exception as e:
            log.error(f"Error saving configuration: {e}")

    def format_attributes(self, show_private: bool = False) -> str:
        """
        Returns a nicely formatted representation of all attributes and their values.
        
        Args:
            show_private: Whether to include private attributes (starting with '_')
            
        Returns:
            str: Formatted representation of attributes
        """
        try:
            from rich.console import Console
            from rich.tree import Tree
        except ImportError:
            raise ImportError("To use format_attributes, you need to install 'rich' (pip install rich)")
        
        console = Console(record=True)
        tree = Tree("📄 [bold light_sky_blue3]Configuration[/bold light_sky_blue3] ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄")
        
        def _add_dict_to_tree(d: dict, tree: Tree) -> None:
            for key, value in d.items():
                if not show_private and str(key).startswith('_'):
                    continue
                if isinstance(value, dict):
                    branch = tree.add(f"[{KEY_COLOR}]{key}[/{KEY_COLOR}]")
                    _add_dict_to_tree(value, branch)
                elif isinstance(value, (list, tuple)):
                    branch = tree.add(f"[{KEY_COLOR}]{key}[/{KEY_COLOR}]")
                    for i, item in enumerate(value):
                        branch.add(f"[green]{i}:[/green] {item}")
                elif isinstance(value, (int, float)):
                    tree.add(f"[{KEY_COLOR}]{key}[/{KEY_COLOR}]: [pale_green3]{value}[/pale_green3]")
                elif isinstance(value, bool):
                    color = 'green' if value else 'red'
                    tree.add(f"[{KEY_COLOR}]{key}[/{KEY_COLOR}]: [{color}]{value}[/{color}]")
                elif value is None:
                    tree.add(f"[{KEY_COLOR}]{key}[/{KEY_COLOR}]: [dim]None[/dim]")
                else:
                    tree.add(f"[{KEY_COLOR}]{key}[/{KEY_COLOR}]: {value}")
        
        _add_dict_to_tree(self.data, tree)
        tree.add(f"[dim]Config file:[/dim] {self.files}")
        
        console.print(tree)
        return console.export_text()

    def print_config(self, show_private: bool = False) -> None:
        """
        Prints the configuration to the console in a nice format.
        
        Args:
            show_private: Whether to include private attributes
        """
        self.format_attributes(show_private)

    def get_table_view(self) -> str:
        """
        Returns the configuration as a table.
        
        Returns:
            str: Tabular representation of the configuration
        """
        try:
            from rich.console import Console
            from rich.table import Table
        except ImportError:
            raise ImportError("To use get_table_view, you need to install 'rich' (pip install rich)")
        
        console = Console(record=True)
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Section", style="dim")
        table.add_column("Key", style="yellow")
        table.add_column("Value", style="green")
        table.add_column("Type", style="blue")
        
        def _add_to_table(data: dict, section: str = "") -> None:
            """Recursively adds items to the table"""
            for key, value in data.items():
                if isinstance(value, dict):
                    new_section = f"{section}.{key}" if section else key
                    _add_to_table(value, new_section)
                else:
                    table.add_row(
                        section,
                        key,
                        str(value),
                        type(value).__name__
                    )
        
        _add_to_table(self.data)
        console.print(table)
        return console.export_text()

    @classmethod
    def _reset(cls):
        """Resets the singleton for testing"""
        if hasattr(cls, '_instances'):
            cls._instances.clear()


if __name__ == '__main__':

    import sys

    cfg = Config('/home/kimifish/bin/test.yaml', use_dataclasses=True, args=sys.argv[1:])
    # cfg.print_config()
    # print_dict(cfg.data)
    cfg.sdh = 'sdf'
    cfg.update('mqtt_port', 2222)
    cfg.print_config()
    cfg.get_table_view()
    # print(cfg.window_position_patterns.Python_Console)

    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            cfg.shutdown()
            sys.exit(0)

#           YAML example
# webapi_options:
#   host: "192.168.196.100"
#   port: 5003
#   log_level: "info"
#   use_ssl: False
# tts_options:
#   put_accent: True
#   put_yo: True
#   sample_rate: 24000
#   speaker: 'xenia'
#   speaker_by_assname:
#     "николай": 'aidar'
#   threads: 1
#   v: "2.0"
