"""HTTP API layer for WakeSafe.

Thin FastAPI routers that EXPOSE the existing, tested services over HTTP. They
import the service entry points and the frozen contract models; they never
reimplement scoring, matching or explanation logic.
"""
