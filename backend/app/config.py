"""Legacy compatibility shim — re-exports from the new ``app.core.config``.

All imports from ``app.config`` continue to work.
"""
import warnings
warnings.warn(
    'Import from app.core.config instead of app.config',
    DeprecationWarning,
    stacklevel=2,
)
from app.core.config import Settings, settings, Environment, LogLevel  # noqa: F401

__all__ = ['Settings', 'settings', 'Environment', 'LogLevel']
