# demo-service (sample target project)

A tiny example project used to demonstrate the self-heal engine integration.

- `config/settings.cfg` — the config the app reads at startup.
- `boot.py` — boot harness: runs the engine, then runs the app only if healed.
- `app.py` — the "real" application logic (reads config, reports status).
- `marker_healer.py` — a project-specific healer the app registers (for the
  unfixable-fault scenario).

Run the whole integration demo from the kit root:

    python run_integration_demo.py
