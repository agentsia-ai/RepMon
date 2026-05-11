"""RepMon — reputation monitoring and domain health engine."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("repmon")
except PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = ["__version__"]
