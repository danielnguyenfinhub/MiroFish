"""
API路由模块
"""

from flask import Blueprint

graph_bp = Blueprint("graph", __name__)
simulation_bp = Blueprint("simulation", __name__)
report_bp = Blueprint("report", __name__)

from . import (  # noqa: E402
    graph,  # noqa: F401
    report,  # noqa: F401
    simulation,  # noqa: F401
)
