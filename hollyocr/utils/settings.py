"""Load/save user preferences as JSON in the per-user app-data directory.

Legacy sensitive keys are removed if found, so upgrades do not retain an old
cloud credential from versions that offered external model integrations.
"""

import json
import os

from .paths import get_config_path, get_legacy_config_paths, unique_paths

# Kept only to scrub credentials from configuration files created by old builds.
SENSITIVE_SETTINGS_KEYS = {"deepseek_api_key"}

CONFIG_FILE = get_config_path()


def load_settings():
    """Load user preferences from JSON file."""
    legacy_paths = [CONFIG_FILE, *get_legacy_config_paths()]
    for config_path in unique_paths(legacy_paths):
        if not config_path.exists():
            continue
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if not isinstance(loaded, dict):
                    return {}
                cleaned = dict(loaded)
                changed = False
                for secret_key in SENSITIVE_SETTINGS_KEYS:
                    if secret_key in cleaned:
                        cleaned.pop(secret_key, None)
                        changed = True
                if changed or config_path != CONFIG_FILE:
                    save_settings(cleaned)
                return cleaned
        except (OSError, json.JSONDecodeError, UnicodeError, TypeError, ValueError):
            continue
    return {}


def save_settings(settings):
    """Save user preferences to JSON file."""
    temp_path = None
    try:
        safe_settings = dict(settings or {})
        for secret_key in SENSITIVE_SETTINGS_KEYS:
            safe_settings.pop(secret_key, None)
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp_path = CONFIG_FILE.with_name(f".{CONFIG_FILE.name}.{os.getpid()}.tmp")
        with open(temp_path, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(safe_settings, f)
        if os.name != 'nt':
            os.chmod(temp_path, 0o600)
        os.replace(temp_path, CONFIG_FILE)

        # Ocultar arquivo no Windows para não poluir a pasta
        if os.name == 'nt':
            try:
                import ctypes
                # 0x02 = Hidden attribute
                ctypes.windll.kernel32.SetFileAttributesW(str(CONFIG_FILE), 0x02)
            except (AttributeError, OSError):
                return

    except (OSError, TypeError, ValueError) as e:
        print(f"Failed to save settings: {e}")
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
