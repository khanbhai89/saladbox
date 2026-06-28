"""Tool auto-discovery and registration."""

from saladbox.tools.base import BaseTool
from saladbox.tools.browser import BrowserTool
from saladbox.tools.calculator import CalculatorTool
from saladbox.tools.clipboard import ClipboardTool
from saladbox.tools.code_editor import CodeEditorTool
from saladbox.tools.color import ColorTool
from saladbox.tools.datetime_tool import DateTimeTool
from saladbox.tools.docker import DockerTool
from saladbox.tools.encoding import EncodingTool
from saladbox.tools.filesystem import FileSystemTool
from saladbox.tools.finance import FinanceTool
from saladbox.tools.git import GitTool
from saladbox.tools.http_client import HttpClientTool
from saladbox.tools.image_gen import ImageGenTool
from saladbox.tools.json_yaml import JsonYamlTool
from saladbox.tools.location import LocationTool
from saladbox.tools.notes import NotesTool
from saladbox.tools.open_url import OpenURLTool
from saladbox.tools.password import PasswordTool
from saladbox.tools.process_manager import ProcessManagerTool
from saladbox.tools.python_exec import PythonExecTool
from saladbox.tools.qrcode_tool import QRCodeTool
from saladbox.tools.reminder import ReminderTool
from saladbox.tools.scheduler import SchedulerTool
from saladbox.tools.screen_capture import ScreenCaptureTool
from saladbox.tools.shell import ShellTool
from saladbox.tools.system_monitor import SystemMonitorTool
from saladbox.tools.text import TextTool
from saladbox.tools.timer import TimerTool
from saladbox.tools.translate import TranslateTool
from saladbox.tools.unit_converter import UnitConverterTool
from saladbox.tools.url import URLTool
from saladbox.tools.weather import WeatherTool
from saladbox.tools.web_search import WebSearchTool

TOOL_MAP: dict[str, type[BaseTool]] = {
    "shell": ShellTool,
    "python_exec": PythonExecTool,
    "browser": BrowserTool,
    "filesystem": FileSystemTool,
    "system_monitor": SystemMonitorTool,
    "scheduler": SchedulerTool,
    "process_manager": ProcessManagerTool,
    "code_editor": CodeEditorTool,
    "git": GitTool,
    "reminder": ReminderTool,
    "web_search": WebSearchTool,
    "calculator": CalculatorTool,
    "datetime_tool": DateTimeTool,
    "clipboard": ClipboardTool,
    "notes": NotesTool,
    "weather": WeatherTool,
    "http_client": HttpClientTool,
    "json_yaml": JsonYamlTool,
    "encoding": EncodingTool,
    "text": TextTool,
    "password": PasswordTool,
    "finance": FinanceTool,
    "timer": TimerTool,
    "qrcode": QRCodeTool,
    "translate": TranslateTool,
    "color": ColorTool,
    "unit_converter": UnitConverterTool,
    "url": URLTool,
    "location": LocationTool,
    "docker": DockerTool,
    "open_url": OpenURLTool,
    "screen_capture": ScreenCaptureTool,
    "image_gen": ImageGenTool,
}


def get_enabled_tools(config: dict[str, bool]) -> list[BaseTool]:
    """Instantiate and return tools that are enabled in config."""
    tools = []
    for name, tool_cls in TOOL_MAP.items():
        if config.get(name, False):
            tools.append(tool_cls())
    return tools
