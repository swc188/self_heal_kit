"""Sample target project used by the integration demonstration.

This mini "service" depends on a small config file. Its boot sequence calls the
self-heal engine over its own directory *before* running real logic, so a class
of file-format faults is repaired automatically instead of crashing the app.
"""
