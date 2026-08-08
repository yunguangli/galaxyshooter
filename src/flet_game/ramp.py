"""Game-agnostic ramp (slope) geometry for the raycast engine.

A :class:`RampDef` describes a straight inclined plane that rises from
ground level at its front edge to ``height`` at its back edge.  The
:class:`RaycastCanvas` renders it as a sloped top surface, triangular
side panels and a vertical back face, fog-faded by distance, and reports
continuous ground height via ``stair_height_at`` so cameras and billboard
sprites can ride the slope in first- and third-person views.

Example::

    from flet_game import RampDef

    ramp = RampDef(
        x=2.5, y=11.5,         # centre X, front Y (axis="y")
        axis="y",
        length=1.6, width=1.0, # run along axis, width perpendicular
        height=0.6,
        color="#b0b0b0",
        side_color="#808080",
    )
    rc.set_ramps([ramp])
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RampDef:
    """A straight ramp in world space.

    Parameters mirror :class:`StairDef`: ``x``/``y`` locate the centre-front
    (``x`` = centre of the width, ``y`` = front edge at height 0 for
    ``axis="y"``); the surface rises linearly to ``height`` at the back edge
    (``y + length``).  For ``axis="x"`` the roles of X/Y swap.
    """

    x: float
    y: float
    axis: str = "y"
    length: float = 2.0
    width: float = 1.0
    height: float = 0.5
    color: str = "#888888"
    side_color: str = "#555555"


@dataclass
class _RampGeom:
    """Pre-computed ramp bounds (internal)."""

    x0: float  # perpendicular bound start
    x1: float  # perpendicular bound end
    a0: float  # along-axis front edge (height 0)
    a1: float  # along-axis back edge (height = height)
    slope: float
    height: float


def build_ramp_geom(r: RampDef) -> _RampGeom:
    """Build footprint geometry from a RampDef."""
    half_w = r.width / 2.0
    if r.axis == "y":
        x0, x1 = r.x - half_w, r.x + half_w
        a0, a1 = r.y, r.y + r.length
    else:
        x0, x1 = r.y - half_w, r.y + half_w
        a0, a1 = r.x, r.x + r.length
    return _RampGeom(
        x0=x0, x1=x1, a0=a0, a1=a1,
        slope=r.height / max(r.length, 1e-6),
        height=r.height,
    )
