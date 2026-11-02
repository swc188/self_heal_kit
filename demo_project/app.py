"""The sample project's real application logic.

Reads the project config and reports a status. This only runs after the boot
harness has confirmed the self-heal engine reached HEALED.
"""


import os


def run_app(app_dir):
    cfg_path = os.path.join(app_dir, "config", "settings.cfg")
    cfg = {}
    with open(cfg_path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            cfg[key.strip()] = val.strip().strip('"')
    return {
        "status": "APP_RAN",
        "app_name": cfg.get("app_name"),
        "log_level": cfg.get("log_level"),
        "port": cfg.get("port"),
        "config_keys": sorted(cfg.keys()),
    }
