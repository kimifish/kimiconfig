import pytest
import os
import sys
import tempfile
import yaml
import logging
from pathlib import Path

# Настройка логирования
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
# Добавляем путь к src в PYTHONPATH
src_path = str(Path(__file__).parent.parent / 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from kimiconfig import Config, _parse_args

@pytest.fixture(autouse=True)
def reset_singleton():
    """
    Фикстура для автоматического сброса синглтона Config после каждого теста.
    autouse=True означает, что фикстура будет применяться ко всем тестам автоматически.
    """
    yield  # Выполнение теста
    Config._reset()  # Сброс после теста

@pytest.fixture
def simple_config_file():
    """Фикстура для создания простого конфиг-файла"""
    config_data = {
        'host': 'localhost',
        'port': 8080,
        'debug': True,
        'numbers': [1, 2, 3],
        'nested': {
            'key': 'value',
            'number': 42
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.safe_dump(config_data, f)
        temp_file = f.name
        log.info(f'Created simple config file: {temp_file}')
        log.info(f'Content: {config_data}')
    
    yield temp_file
    os.unlink(temp_file)

@pytest.fixture
def nested_config_file():
    """Фикстура для создания конфиг-файла со сложной структурой"""
    config_data = {
        'webapi_options': {
            'host': '127.0.0.1',
            'port': 8080,
            'settings': {
                'timeout': 30,
                'retry': True,
                'max_attempts': 3
            }
        },
        'database': {
            'url': 'postgresql://localhost/db',
            'pool_size': 5
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.safe_dump(config_data, f)
        temp_file = f.name
        log.info(f'Created nested config file: {temp_file}')
        log.info(f'Content: {config_data}')
    
    yield temp_file
    os.unlink(temp_file)

@pytest.fixture
def multiple_config_files():
    """Фикстура для создания нескольких конфиг-файлов с перезаписью значений"""
    base_config = {
        'webapi': {
            'host': '127.0.0.1',
            'port': 8080,
            'debug': False
        },
        'base_value': 'not_overridden'
    }
    
    override_config = {
        'webapi': {
            'port': 9090,
            'debug': True
        },
        'override_value': 'new'
    }
    
    files = []
    for i, config in enumerate([base_config, override_config]):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.safe_dump(config, f)
            files.append(f.name)
            log.info(f'Created config file {i+1}: {f.name}')
            log.info(f'Content: {config}')
    
    yield files
    
    for file in files:
        os.unlink(file)

def test_simple_config(simple_config_file):
    """Тест базовой загрузки конфигурации"""
    cfg = Config(simple_config_file)
    
    assert cfg.host == 'localhost'
    assert cfg.port == 8080
    assert cfg.debug is True
    assert cfg.numbers == [1, 2, 3]
    assert cfg.nested['key'] == 'value'
    assert cfg.nested['number'] == 42

def test_nested_config_with_dataclasses(nested_config_file):
    """Тест загрузки конфигурации с использованием датаклассов"""
    cfg = Config(nested_config_file, use_dataclasses=True)
    log.debug(f'{cfg.__dict__=}')
    
    assert cfg.webapi_options.host == '127.0.0.1'
    assert cfg.webapi_options.port == 8080
    assert cfg.webapi_options.settings.timeout == 30
    assert cfg.webapi_options.settings.retry is True
    assert cfg.database.url == 'postgresql://localhost/db'
    assert cfg.database.pool_size == 5

def test_multiple_files_override(multiple_config_files):
    """Тест перезаписи значений при загрузке нескольких файлов"""
    cfg = Config(multiple_config_files)
    
    # Проверяем перезаписанные значения
    assert cfg.webapi['port'] == 9090  # Перезаписано из второго файла
    assert cfg.webapi['debug'] is True  # Перезаписано из второго файла
    assert cfg.webapi['host'] == '127.0.0.1'  # Не перезаписано
    assert cfg.base_value == 'not_overridden'  # Из первого файла
    assert cfg.override_value == 'new'  # Из второго файла

def test_cli_args():
    """Тест парсинга аргументов командной строки"""
    args = ['--host=localhost', '--port=8080', '--nested.value=test', '-v']
    result = _parse_args(args)
    
    assert result['host'] == 'localhost'
    assert result['port'] == 8080
    assert result['nested']['value'] == 'test'
    assert result['v'] is True

def test_config_with_cli_args(simple_config_file):
    """Тест конфигурации с аргументами командной строки"""
    cli_args = ['--port=9000', '--new_option=value']
    cfg = Config(simple_config_file, args=cli_args)
    
    assert cfg.port == 9000  # Перезаписано из CLI
    assert cfg.new_option == 'value'  # Добавлено из CLI
    assert cfg.host == 'localhost'  # Не изменено

def test_singleton():
    """Тест поведения синглтона"""
    cfg1 = Config()
    cfg1.test_value = 'test'
    
    cfg2 = Config()
    assert cfg2.test_value == 'test'  # Значение сохранено
    assert cfg1 is cfg2  # Тот же самый объект
    
    # Проверяем сброс
    Config._reset()
    cfg3 = Config()
    assert not hasattr(cfg3, 'test_value')  # Значение сброшено
    assert cfg3 is not cfg1  # Новый объект

def test_config_update():
    """Тест метода update"""
    cfg = Config()
    cfg.update('test_key', 'test_value')
    
    assert cfg.test_key == 'test_value'
    assert cfg.data['test_key'] == 'test_value'


def test_custom_env_prefix():
    # Установка тестовых переменных окружения с разными префиксами
    os.environ['MY_APP_DATABASE__HOST'] = 'localhost'
    os.environ['MY_APP_DATABASE__PORT'] = '5432'
    os.environ['MY_APP_DATABASE__SSL'] = 'true'
    os.environ['OTHER_PREFIX_SETTING'] = 'should_not_load'
    
    config_data = """
    database:
        host: default_host
        port: 1234
        ssl: false
    """
    
    with open('test_config.yaml', 'w') as f:
        f.write(config_data)
    
    try:
        # Создаем конфиг с пользовательским префиксом
        cfg = Config('test_config.yaml', env_prefix='MY_APP_', use_dataclasses=True)
        
        # Проверяем, что значения из переменных окружения с нужным префиксом загрузились
        assert cfg.database.host == 'localhost'
        assert cfg.database.port == 5432
        assert cfg.database.ssl == True
        
        # Проверяем, что переменная с другим префиксом не повлияла на конфиг
        assert not hasattr(cfg, 'OTHER_PREFIX_SETTING')
        assert not hasattr(cfg, 'setting')
        
    finally:
        # Очистка
        if os.path.exists('test_config.yaml'):
            os.remove('test_config.yaml')
        del os.environ['MY_APP_DATABASE__HOST']
        del os.environ['MY_APP_DATABASE__PORT']
        del os.environ['MY_APP_DATABASE__SSL']
        del os.environ['OTHER_PREFIX_SETTING']

def test_nested_env_variables_with_prefix():
    os.environ['MYAPP_SERVICE__API__URL'] = 'http://api.example.com'
    os.environ['MYAPP_SERVICE__API__VERSION'] = '2'
    os.environ['MYAPP_SERVICE__TIMEOUT'] = '30.5'
    
    try:
        cfg = Config(env_prefix='MYAPP_', use_dataclasses=True)
        
        # Проверяем правильность создания вложенной структуры
        assert cfg.service.api.url == 'http://api.example.com'
        assert cfg.service.api.version == 2
        assert cfg.service.timeout == 30.5
        
    finally:
        del os.environ['MYAPP_SERVICE__API__URL']
        del os.environ['MYAPP_SERVICE__API__VERSION']
        del os.environ['MYAPP_SERVICE__TIMEOUT']

def test_env_prefix_type_conversion():
    os.environ['TEST_VALUES__STRING'] = 'hello'
    os.environ['TEST_VALUES__INT'] = '42'
    os.environ['TEST_VALUES__FLOAT'] = '3.14'
    os.environ['TEST_VALUES__BOOL_TRUE'] = 'yes'
    os.environ['TEST_VALUES__BOOL_FALSE'] = 'no'
    
    try:
        cfg = Config(env_prefix='TEST_', use_dataclasses=True)
        
        # Проверяем автоматическое преобразование типов
        assert isinstance(cfg.values.string, str)
        assert cfg.values.string == 'hello'
        
        assert isinstance(cfg.values.int, int)
        assert cfg.values.int == 42
        
        assert isinstance(cfg.values.float, float)
        assert cfg.values.float == 3.14
        
        assert isinstance(cfg.values.bool_true, bool)
        assert cfg.values.bool_true == True
        
        assert isinstance(cfg.values.bool_false, bool)
        assert cfg.values.bool_false == False
        
    finally:
        del os.environ['TEST_VALUES__STRING']
        del os.environ['TEST_VALUES__INT']
        del os.environ['TEST_VALUES__FLOAT']
        del os.environ['TEST_VALUES__BOOL_TRUE']
        del os.environ['TEST_VALUES__BOOL_FALSE']
