"""
Plugin loader — discovers and registers Flask Blueprint plugins from app/plugins/.

A plugin is a Python package inside app/plugins/ that exposes:

  blueprint : flask.Blueprint   — the routes to register
  PLUGIN_META : dict            — {name, description, icon, nav_url, nav_section}

Plugins are loaded once at startup.  Failed plugins are logged and skipped.
"""
import importlib
import logging
import pkgutil
from pathlib import Path

logger = logging.getLogger(__name__)

_loaded: list[dict] = []  # [{meta, blueprint}, ...]


def load_plugins(app):
    """Import all valid plugins and register their blueprints with `app`."""
    global _loaded
    _loaded = []

    plugins_pkg_path = Path(__file__).parent / "plugins"
    if not plugins_pkg_path.exists():
        return

    for finder, name, is_pkg in pkgutil.iter_modules([str(plugins_pkg_path)]):
        if not is_pkg:
            continue
        module_name = f"app.plugins.{name}"
        try:
            mod = importlib.import_module(module_name)
        except Exception as e:
            logger.warning("Plugin %r failed to import: %s", name, e)
            continue

        bp   = getattr(mod, "blueprint", None)
        meta = getattr(mod, "PLUGIN_META", {})

        if bp is None:
            logger.warning("Plugin %r has no 'blueprint' attribute — skipping", name)
            continue

        if not meta.get("name"):
            meta["name"] = name

        try:
            app.register_blueprint(bp)
            _loaded.append({"meta": meta, "blueprint": bp})
            logger.info("Plugin loaded: %r  url_prefix=%s", name,
                        getattr(bp, "url_prefix", "/"))
        except Exception as e:
            logger.warning("Plugin %r blueprint registration failed: %s", name, e)


def get_plugin_nav() -> list[dict]:
    """Return nav items from all loaded plugins (for sidebar injection)."""
    items = []
    for entry in _loaded:
        m = entry["meta"]
        if m.get("nav_url"):
            items.append({
                "url":     m["nav_url"],
                "label":   m.get("name", "Plugin"),
                "icon":    m.get("icon", "ti-puzzle"),
                "section": m.get("nav_section", "Plugins"),
            })
    return items


def get_loaded_plugins() -> list[dict]:
    return [e["meta"] for e in _loaded]
