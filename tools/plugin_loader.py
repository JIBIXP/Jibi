"""
Chargeur automatique des outils créés par JIBI (tools/plugins/*.py).
Un plugin peut définir OUTILS = {"nom": {"fonction": f, "description": "...", "parametres": {...}}}
ou simplement exposer des fonctions publiques (docstring = description).
Un plugin qui plante est ignoré et journalisé : il ne casse jamais JIBI.
"""
import importlib
import inspect
import sys
from pathlib import Path

from tools.tool_registry import register_tool

PLUGINS_DIR = Path(__file__).resolve().parent / "plugins"


def _log(msg):
    try:
        from logging_jibi import log_event
        log_event("plugins", msg)
    except Exception:
        print(f"[plugins] {msg}")


def charger_plugins() -> dict:
    PLUGINS_DIR.mkdir(exist_ok=True)
    (PLUGINS_DIR / "__init__.py").touch(exist_ok=True)
    charges, erreurs = [], []
    for f in sorted(PLUGINS_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        nom_mod = f"tools.plugins.{f.stem}"
        try:
            mod = importlib.reload(sys.modules[nom_mod]) if nom_mod in sys.modules \
                else importlib.import_module(nom_mod)
            outils = getattr(mod, "OUTILS", None)
            if isinstance(outils, dict):
                for nom, spec in outils.items():
                    register_tool(nom, spec["fonction"], spec.get("description", ""),
                                  spec.get("parametres", {"type": "object", "properties": {}, "required": []}))
                    charges.append(nom)
            else:
                for nom, fn in inspect.getmembers(mod, inspect.isfunction):
                    if not nom.startswith("_") and fn.__module__ == mod.__name__:
                        register_tool(nom, fn, (fn.__doc__ or nom).strip().split("\n")[0])
                        charges.append(nom)
        except Exception as e:
            erreurs.append(f"{f.name}: {e}")
    _log(f"Plugins chargés : {len(charges)} outil(s) ; erreurs : {len(erreurs)}")
    for e in erreurs:
        _log(f"⚠️ {e}")
    return {"charges": charges, "erreurs": erreurs}