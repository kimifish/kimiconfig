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
from typing import Dict, Any, Union, List, Callable
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
        file (Union[str, List[str]]): Path(s) to YAML or JSON configuration file(s). Later files override earlier ones.
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
                 args: List[str]|None = None, 
                 use_dataclasses: bool = True,
                 env_prefix: str = 'DEFAULT_APP_',
                 watch_mtime: bool = False, 
                 watch_interval: int = 15):
        self._use_dataclasses = use_dataclasses
        self.data = {}
        # Inside data is stored by source and merges (from top to bottom) to 'self.data' after any change:
        self._file_data = {}
        self._env_data = {}
        self._args_data = {}
        self._runtime_update_data = {}

        # For runtime variables sometimes it's useful placing them in one branch.
        self.runtime: dict

        self._args = {}
        self.shutdown_flag = False
        self._update_callbacks: List[Callable[[], None]] = []
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

    def _validate_attribute_override(self, data_to_check: Dict[str, Any]):
        """
        Checks if any top-level keys in data_to_check would override
        existing methods or "protected" attributes of the Config instance.
        """
        conflicting_keys = []
        # Consider attributes of the class itself (methods, class variables)
        # and also instance-specific attributes that might be critical (e.g., _file_data)
        # dir(self) gives all attributes, including methods and inherited ones.
        # We are primarily interested in preventing override of methods and core attributes.
        instance_attrs = dir(self)

        for key in data_to_check.keys():
            if key in instance_attrs:
                # Check if it's a method or a "protected" variable (by convention, starts with '_')
                # We allow overriding normal data attributes that might have been set by previous configs.
                attr = getattr(self, key)
                if callable(attr):
                    conflicting_keys.append(key)
                # Example of protecting specific non-method attributes if needed:
                # elif key in ['data', '_file_data', '_env_data', '_args_data', '_runtime_update_data', 'shutdown_flag']:
                #     conflicting_keys.append(key)

        if conflicting_keys:
            conflicting_keys.sort()
            raise ValueError(
                f"Configuration keys conflict with existing class attributes/methods: {', '.join(conflicting_keys)}. "
                f"Please rename these keys in your configuration."
            )

    def _update_data_from_all_x_data(self):
        """Updates configuration data and validates before applying attributes"""
        # Clear and rebuild self.data from all sources
        self.data.clear()
        self._deep_update(self.data, self._file_data)
        self._deep_update(self.data, self._env_data)
        self._deep_update(self.data, self._args_data)
        self._deep_update(self.data, self._runtime_update_data)
        
        # Validate before attempting to set attributes
        self._validate_attribute_override(self.data)
        return self

    def _update_attributes_from_data(self):
        """Updates class attributes from configuration data"""
        if self._use_dataclasses:
            for k, v in self.data.items():
                if isinstance(v, dict):
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
                self._load_from_files()  # Reload all files
                self._update_data_from_all_x_data()._update_attributes_from_data()
                for callback in self._update_callbacks:
                    try:
                        callback()
                    except Exception as e:
                        log.error(f"Error executing update callback {getattr(callback, '__name__', 'unknown')}: {e}")

    def load_files(self, files: list[str]):
        """Loads configuration from files"""
        if isinstance(files, str):
            files = [files]
        self.files.extend(files)
        self._load_from_files()
        self._update_data_from_all_x_data()._update_attributes_from_data()
    
    def load_args(self, args: list[str]):
        if isinstance(args, str):
            args = [args,]
        self._load_from_args(_parse_args(args))
        self._update_data_from_all_x_data()._update_attributes_from_data()

    def register_update_callback(self, callback: Callable[[], None]) -> None:
        """
        Registers a callback function to be executed after configuration is updated.

        Args:
            callback: A function to be called when the configuration changes.
                      The callback should not take any arguments.
        """
        if callable(callback):
            self._update_callbacks.append(callback)
        else:
            log.warning(f"Attempted to register a non-callable object as a callback: {callback}")

    def validate_config(self, keys_to_validate: List[str]) -> None:
        """
        Validates that a list of specified keys (potentially with wildcards)
        exist in the configuration.

        Args:
            keys_to_validate: A list of strings, where each string is a dot-separated
                              key. The '%' character can be used as a wildcard to match
                              any key at that specific level. For example, "mqtt.servers.%.address"
                              checks that all children of "mqtt.servers" have an "address" key.
                              If "mqtt.servers" has no children, it's not an error.

        Raises:
            ValueError: If any of the specified keys are not found, containing a list
                        of all missing keys.
        """
        missing_keys = []
        for key_str in keys_to_validate:
            if not self._is_key_present_recursive(self.data, key_str.split('.')):
                missing_keys.append(key_str)
        
        if missing_keys:
            # Sort for consistent error messages, helpful for tests
            missing_keys.sort()
            raise ValueError(f"Missing configuration keys: {', '.join(missing_keys)}")

    def _is_key_present_recursive(self, current_data: Any, path_parts: List[str]) -> bool:
        """
        Internal recursive helper to check for key presence with wildcard support.
        """
        if not path_parts:
            # All parts of the key path have been successfully traversed.
            return True

        part = path_parts[0]
        remaining_parts = path_parts[1:]

        if part == '%':
            if not isinstance(current_data, dict):
                # Expected a dictionary to expand wildcard '%', but found something else
                # or current_data is None (e.g. parent key did not exist).
                return False

            if not current_data:
                # Current level is an empty dictionary.
                return True

            if not remaining_parts:
                # Key is like "a.b.%". This means "a.b" must be a dictionary.
                # If we are here, current_data is a dictionary (possibly empty), which is valid.
                return True

            # Wildcard '%' followed by more path parts (e.g., "%.address").
            # All children must satisfy the remaining_parts.
            all_children_valid = True
            # If current_data is an empty dict, the loop won't run, all_children_valid remains True.
            for child_node in current_data.values():
                if not self._is_key_present_recursive(child_node, remaining_parts):
                    all_children_valid = False
                    break  # If one child fails, the whole wildcard pattern fails for this level.
            
            return all_children_valid
        
        else: # Regular key part
            if not isinstance(current_data, dict) or part not in current_data:
                # Key part not found, or current_data is not a dictionary to look into.
                return False
            
            # Move to the next level of nesting.
            return self._is_key_present_recursive(current_data[part], remaining_parts)

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

