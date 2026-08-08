"""Game-agnostic staircase geometry for the raycast engine.

A :class:`StairDef` describes a straight run of steps that can be placed
in any raycasted world.  The :class:`RaycastCanvas` renders them as
horizontal treads and vertical risers, fog-faded by distance.

Example::

    from flet_game import StairDef

    stairs = StairDef(
        x=5.0, y=3.0,          # start position (centre X, front Y of step 0)
        axis="y",              # runs along Y
        n_steps=5, rise=0.12,  # 5 steps, 0.12 height each
        run=0.3, width=1.0,    # 0.3 depth each, 1.0 wide (centred on x=5.0)
        tread_color="#888888",
        riser_color="#555555",
    )
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StairDef:
    """A straight run of stairs in world space.

    Parameters
    ----------
    x, y : float
        World position of the stair's centre-front corner.  ``x`` is the
        centre of the stair width (perpendicular to the run axis).  ``y``
        is the front edge of the first step (closest to the viewer when
        ``axis="y"``).
    axis : str
        Which world axis the stairs run along.  ``"y"`` (default) means
        the steps extend along the Y axis (away from the viewer at the
        start).  ``"x"`` means they extend along the X axis.
    n_steps : int
        Number of steps (default 4).
    rise : float
        Height of each step in world units (default 0.12).
    run : float
        Depth of each step along the run axis in world units (default 0.3).
    width : float
        Width of the stairs perpendicular to the run axis, centred on the
        start position, in world units (default 1.0).
    tread_color : str
        Hex colour of the horizontal tread surface (default "#888888").
    riser_color : str
        Hex colour of the vertical riser face (default "#555555").
    tread_color_alt : str or None
        Alternate tread colour for even-numbered steps (0, 2, 4, ...).
        Creates a visible stripe pattern that makes individual steps
        distinguishable from the front.  ``None`` (default) uses
        ``tread_color`` for all steps.
    """

    x: float
    y: float
    axis: str = "y"
    n_steps: int = 4
    rise: float = 0.12
    run: float = 0.3
    width: float = 1.0
    tread_color: str = "#888888"
    riser_color: str = "#555555"
    tread_color_alt: str | None = None


@dataclass
class _StepGeom:
    """Pre-computed per-step geometry (internal)."""

    # Tread horizontal surface
    tread_height: float  # world height of this tread
    tread_y0: float      # Y bound start (along run axis)
    tread_y1: float      # Y bound end
    tread_x0: float      # X bound start (perpendicular)
    tread_x1: float      # X bound end
    # Riser vertical face (at the front edge of this step)
    riser_y: float       # Y of the riser plane (front edge)
    riser_h0: float      # bottom height of riser (= tread_height)
    riser_h1: float      # top height of riser (= tread_height + rise)


def build_step_geom(s: StairDef) -> list[_StepGeom]:
    """Build per-step geometry from a StairDef.

    Returns a list of ``_StepGeom`` (one per step, front-to-back order).
    """
    geom: list[_StepGeom] = []
    half_w = s.width / 2.0
    for i in range(s.n_steps):
        h = s.rise * (i + 1)  # cumulative height at top of this step
        if s.axis == "y":
            y0 = s.y + s.run * i
            y1 = s.y + s.run * (i + 1)
            x0 = s.x - half_w
            x1 = s.x + half_w
            riser_y = y0  # front edge
        else:  # axis == "x"
            # For axis="x", steps extend along X; y0/y1 are the width bounds
            # and x0/x1 are the depth bounds.  We store tread_y0/y1 as
            # the *along-axis* range regardless of axis, so the renderer
            # can use a single code path.
            y0 = s.x + s.run * i
            y1 = s.x + s.run * (i + 1)
            x0 = s.y - half_w
            x1 = s.y + half_w
            riser_y = y0
        geom.append(_StepGeom(
            tread_height=h,
            tread_y0=y0,
            tread_y1=y1,
            tread_x0=x0,
            tread_x1=x1,
            riser_y=riser_y,
            riser_h0=h - s.rise if i > 0 else 0.0,
            riser_h1=h,
        ))
    return geom
