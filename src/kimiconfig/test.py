#!/usr/bin/python
from config import Config
from rich.console import Console
 
console=Console()
c = Config(args=["--level0.level1=ASD", "--level0.test=WER"], use_dataclasses=True)
c.update("logging.markup", False)
# c.load_files(["/home/kimifish/.config/i3-commander/config.yaml"])
c.load_files(["/home/kimifish/bin/test.yaml"])
c.update("level0.level1.level2", "Ok")
c.load_args(["--logging.date_format=SDFEWR", "--level0.level1.load_args=test"])
c.print_config()
 
console.print(f"data['level0'] - {c.data['level0']}")
console.print(f"level0 - {type(c.level0)} - {c.level0}")
console.print(f"level1 - {type(c.level0.level1)} - {c.level0.level1}")
console.print(f"level2 - {type(c.level0.level1.level2)} - {c.level0.level1.level2}")
