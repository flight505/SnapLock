"""
CylinderFrame — a local cylindrical coordinate system for SnapLock
operations on an arbitrary-oriented container.

The existing receiver/lid builders assume the cylinder axis is parallel
to world +Z, so they can sketch on world XZ. The interface builder's
first version inherited that restriction from the borrowed slot/column
logic. This module lifts it: given a cylindrical BRepFace of any
orientation, we extract a frame (origin, axis, perp) and provide
pure-math helpers that convert (R, Z_along_axis, theta) in the frame
to world (x, y, z).

The pure-math layer is offline-testable. The Fusion API layer
(_construct_radial_plane, _construct_cross_section_plane, etc.) sits
on top and only runs inside Fusion.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple


# ============================================================
# Pure math: offline-testable vector operations
# ============================================================

def _normalize(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    mag = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if mag < 1e-12:
        raise ValueError(f"Cannot normalize zero vector: {v}")
    return (v[0] / mag, v[1] / mag, v[2] / mag)


def _cross(
    a: Tuple[float, float, float],
    b: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(
    a: Tuple[float, float, float],
    b: Tuple[float, float, float],
) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def pick_perpendicular(axis: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """
    Pick an arbitrary unit vector perpendicular to `axis`. Used to establish
    the "radial reference" for a cylinder's frame (any perpendicular works —
    the frame is rotationally symmetric around the axis anyway).

    We bias toward world X when possible, falling back to world Y for
    near-X-aligned axes. This gives stable, reproducible perp choices
    across test runs.
    """
    ax = _normalize(axis)
    # Prefer crossing with world +X; if axis is nearly parallel to X,
    # use world +Y instead.
    if abs(ax[0]) < 0.9:
        reference = (1.0, 0.0, 0.0)
    else:
        reference = (0.0, 1.0, 0.0)
    perp = _cross(ax, reference)
    # axis × reference ⊥ axis; normalize it
    return _normalize(perp)


def cylindrical_to_world(
    origin: Tuple[float, float, float],
    axis: Tuple[float, float, float],
    perp: Tuple[float, float, float],
    r: float,
    z_along: float,
    theta_rad: float = 0.0,
) -> Tuple[float, float, float]:
    """
    Convert (R, Z_along_axis, theta) in a cylindrical frame to world (x, y, z).

    The frame is defined by (origin, axis, perp) where:
      - origin: a point on the cylinder axis (world coords)
      - axis: unit vector along the cylinder axis
      - perp: unit vector perpendicular to axis, sets theta=0 direction

    Pure Python — offline-testable, no Fusion dependency.
    """
    ax = _normalize(axis)
    p1 = _normalize(perp)
    # Second perpendicular: right-handed basis from ax × p1
    p2 = _cross(ax, p1)
    p2 = _normalize(p2)

    cos_t = math.cos(theta_rad)
    sin_t = math.sin(theta_rad)

    # Direction of the radial vector at angle theta
    rx = cos_t * p1[0] + sin_t * p2[0]
    ry = cos_t * p1[1] + sin_t * p2[1]
    rz = cos_t * p1[2] + sin_t * p2[2]

    return (
        origin[0] + r * rx + z_along * ax[0],
        origin[1] + r * ry + z_along * ax[1],
        origin[2] + r * rz + z_along * ax[2],
    )


def world_to_frame(
    origin: Tuple[float, float, float],
    axis: Tuple[float, float, float],
    perp: Tuple[float, float, float],
    point: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    """
    Inverse of cylindrical_to_world. Return (R, Z_along_axis, theta_rad)
    for a world point in the given frame.

    Pure Python — offline-testable.
    """
    ax = _normalize(axis)
    p1 = _normalize(perp)
    p2 = _normalize(_cross(ax, p1))

    rel = (
        point[0] - origin[0],
        point[1] - origin[1],
        point[2] - origin[2],
    )

    z_along = _dot(rel, ax)
    r_comp_1 = _dot(rel, p1)
    r_comp_2 = _dot(rel, p2)
    r = math.sqrt(r_comp_1 * r_comp_1 + r_comp_2 * r_comp_2)
    theta = math.atan2(r_comp_2, r_comp_1)
    return (r, z_along, theta)


# ============================================================
# Fusion API layer — runtime only
# ============================================================

@dataclass
class CylinderFrame:
    """
    A local cylindrical coordinate system for a selected cylindrical face.

    Stored as plain tuples of floats so the whole object is picklable,
    offline-constructable, and doesn't hold Fusion references that could
    go stale across feature operations.

    All coordinates in centimeters (Fusion native).
    """
    origin: Tuple[float, float, float]   # on cylinder axis
    axis: Tuple[float, float, float]     # unit vector, along cylinder axis
    perp: Tuple[float, float, float]     # unit vector, perpendicular to axis
    radius_cm: float                     # cylinder radius
    face_top_cm: float                   # z_along_axis of the highest point on the face
    face_bot_cm: float                   # z_along_axis of the lowest point on the face

    @property
    def face_height_cm(self) -> float:
        return self.face_top_cm - self.face_bot_cm

    @property
    def is_world_z_aligned(self) -> bool:
        """True if the cylinder axis is parallel (or anti-parallel) to world +Z."""
        return abs(self.axis[2]) > 0.999

    def point_at(
        self,
        r: float,
        z_along: float,
        theta_rad: float = 0.0,
    ) -> Tuple[float, float, float]:
        """Return world (x, y, z) at the given cylindrical coordinates in this frame."""
        return cylindrical_to_world(
            self.origin, self.axis, self.perp, r, z_along, theta_rad,
        )


def frame_from_cylinder_face(face) -> Optional[CylinderFrame]:
    """
    Extract a CylinderFrame from a Fusion BRepFace. Returns None if the
    face isn't cylindrical.

    Unlike the v0.10.0 _read_face_frame helper, this works for cylinders
    of any orientation — not just world-Z-aligned ones. The frame's axis
    is read directly from the cylinder's geometry.axis, and face_top/bot
    are computed by projecting the face's edge vertices onto the axis.
    """
    # Import inside the function so the module stays importable offline
    import adsk.core  # type: ignore

    geom = face.geometry
    if not isinstance(geom, adsk.core.Cylinder):
        return None

    origin = (geom.origin.x, geom.origin.y, geom.origin.z)
    axis_raw = (geom.axis.x, geom.axis.y, geom.axis.z)
    axis = _normalize(axis_raw)
    perp = pick_perpendicular(axis)
    radius = geom.radius

    # Project face vertices onto the axis to find the face's extent along it
    min_z_along = float("inf")
    max_z_along = float("-inf")
    for ei in range(face.edges.count):
        edge = face.edges.item(ei)
        for vertex in (edge.startVertex, edge.endVertex):
            if vertex is None:
                continue
            vp = vertex.geometry
            # (vp - origin) · axis
            rel_x = vp.x - origin[0]
            rel_y = vp.y - origin[1]
            rel_z = vp.z - origin[2]
            z_along = rel_x * axis[0] + rel_y * axis[1] + rel_z * axis[2]
            if z_along < min_z_along:
                min_z_along = z_along
            if z_along > max_z_along:
                max_z_along = z_along

    if min_z_along == float("inf"):
        # Fall back to bounding box projection
        bb = face.boundingBox
        for pt in (bb.minPoint, bb.maxPoint):
            rel_x = pt.x - origin[0]
            rel_y = pt.y - origin[1]
            rel_z = pt.z - origin[2]
            z_along = rel_x * axis[0] + rel_y * axis[1] + rel_z * axis[2]
            if z_along < min_z_along:
                min_z_along = z_along
            if z_along > max_z_along:
                max_z_along = z_along

    return CylinderFrame(
        origin=origin,
        axis=axis,
        perp=perp,
        radius_cm=radius,
        face_top_cm=max_z_along,
        face_bot_cm=min_z_along,
    )


def world_z_aligned_frame(
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    radius_cm: float = 0.0,
) -> CylinderFrame:
    """
    Construct a frame aligned with world +Z at a given origin.

    Used by the interface builder when falling back to the world-aligned
    case (equivalent to the receiver_builder's hardcoded behavior). Also
    useful for tests.
    """
    return CylinderFrame(
        origin=origin,
        axis=(0.0, 0.0, 1.0),
        perp=(1.0, 0.0, 0.0),
        radius_cm=radius_cm,
        face_top_cm=0.0,
        face_bot_cm=0.0,
    )


# ============================================================
# Sketch plane construction (Fusion-only)
# ============================================================

def _make_scratch_sketch_points(component, world_points):
    """
    Host construction references via SketchPoint objects on a throwaway sketch.

    Rationale: in the current Fusion document mode, direct calls to
    `component.constructionPoints.add` and `component.constructionAxes.add`
    fail with "Environment is not supported" — an undocumented restriction
    that appeared somewhere in the 2024+ parametric-design path. Sketch
    points, however, work universally. And ConstructionPlaneInput's
    setByThreePoints + ConstructionAxisInput's setByTwoPoints both accept
    SketchPoint objects as equivalent inputs to ConstructionPoint.

    We host all the reference points on ONE hidden scratch sketch per call
    so the timeline doesn't get cluttered with N construction-point nodes.

    Args:
        component: the component to create the sketch in
        world_points: list of (x, y, z) tuples in cm

    Returns:
        (sketch, [SketchPoint, ...]) — the scratch sketch and its points,
        indexed in the same order as `world_points`.
    """
    import adsk.core  # type: ignore

    sketch = component.sketches.add(component.xYConstructionPlane)
    # Hide it so it doesn't clutter the browser
    try:
        sketch.isVisible = False
    except Exception:
        pass
    sketch_points = []
    for x, y, z in world_points:
        sp = sketch.sketchPoints.add(adsk.core.Point3D.create(x, y, z))
        sketch_points.append(sp)
    return sketch, sketch_points


def create_radial_plane(component, frame: CylinderFrame):
    """
    Create a construction plane containing the cylinder axis AND a
    perpendicular radial direction. Used for sketching slot/entry cross-
    section profiles that will be revolved around the axis.

    Strategy: setByThreePoints with sketch points at:
      P0: frame origin
      P1: origin + axis  (second point on the axis)
      P2: origin + perp  (a point off the axis in the radial direction)
    The plane containing these three points contains the whole axis line
    and the radial reference, which is exactly what we need for revolve
    profiles.
    """
    o = frame.origin
    ax = frame.axis
    pp = frame.perp

    _, sps = _make_scratch_sketch_points(component, [
        (o[0], o[1], o[2]),
        (o[0] + ax[0], o[1] + ax[1], o[2] + ax[2]),
        (o[0] + pp[0], o[1] + pp[1], o[2] + pp[2]),
    ])

    plane_input = component.constructionPlanes.createInput()
    plane_input.setByThreePoints(sps[0], sps[1], sps[2])
    return component.constructionPlanes.add(plane_input)


def create_cross_section_plane(component, frame: CylinderFrame, z_along_cm: float):
    """
    Create a construction plane perpendicular to the cylinder axis,
    intersecting the axis at `z_along_cm` measured from the frame origin.

    Used for sketching snap column circles (which are extruded along the
    axis direction into the wall material).

    Strategy: three sketch points on the perpendicular plane:
      P0: origin + z_along * axis  (on-axis center of the plane)
      P1: P0 + perp                (first radial reference)
      P2: P0 + (axis × perp)       (second radial reference, orthogonal)
    """
    ax = frame.axis
    pp = frame.perp
    o = frame.origin

    center_x = o[0] + z_along_cm * ax[0]
    center_y = o[1] + z_along_cm * ax[1]
    center_z = o[2] + z_along_cm * ax[2]

    pp2 = _normalize(_cross(ax, pp))

    _, sps = _make_scratch_sketch_points(component, [
        (center_x, center_y, center_z),
        (center_x + pp[0], center_y + pp[1], center_z + pp[2]),
        (center_x + pp2[0], center_y + pp2[1], center_z + pp2[2]),
    ])

    plane_input = component.constructionPlanes.createInput()
    plane_input.setByThreePoints(sps[0], sps[1], sps[2])
    return component.constructionPlanes.add(plane_input)


def create_frame_axis(component, frame: CylinderFrame):
    """
    Create a construction axis along the cylinder's axis direction,
    passing through the frame origin. Used as the revolve axis for slot
    and entry profile revolves.

    Strategy: setByTwoPoints with two sketch points on the axis line.
    """
    o = frame.origin
    ax = frame.axis

    _, sps = _make_scratch_sketch_points(component, [
        (o[0], o[1], o[2]),
        (o[0] + ax[0], o[1] + ax[1], o[2] + ax[2]),
    ])

    axis_input = component.constructionAxes.createInput()
    axis_input.setByTwoPoints(sps[0], sps[1])
    return component.constructionAxes.add(axis_input)


# ============================================================
# Frame-aware sketch drawing (Fusion-only)
# ============================================================

def sketch_radial_profile_in_frame(
    sketch,
    frame: CylinderFrame,
    points_rz: list,
) -> int:
    """
    Draw a closed polyline on `sketch` (which must be on a radial plane
    returned by create_radial_plane) from (R, Z_along_axis) tuples.

    Each (R, Z) is converted to world coordinates via the frame, then
    projected into the sketch's local (x, y) via the sketch's
    xDirection/yDirection/origin.

    Args:
        sketch: A sketch on a radial construction plane
        frame: The CylinderFrame that defines (R, Z) semantics
        points_rz: List of (R_cm, Z_along_cm) tuples
    """
    import adsk.core  # type: ignore

    sx = sketch.xDirection
    sy = sketch.yDirection
    so = sketch.origin

    def _rz_to_sketch(r, z_along):
        # World point at this (R, Z, theta=0 so on +perp side)
        wx, wy, wz = frame.point_at(r, z_along, 0.0)
        # Relative to sketch origin
        dx = wx - so.x
        dy = wy - so.y
        dz = wz - so.z
        # Project onto sketch axes
        lx = dx * sx.x + dy * sx.y + dz * sx.z
        ly = dx * sy.x + dy * sy.y + dz * sy.z
        return lx, ly

    lines = sketch.sketchCurves.sketchLines
    for i in range(len(points_rz)):
        r1, z1 = points_rz[i]
        r2, z2 = points_rz[(i + 1) % len(points_rz)]
        lx1, ly1 = _rz_to_sketch(r1, z1)
        lx2, ly2 = _rz_to_sketch(r2, z2)
        lines.addByTwoPoints(
            adsk.core.Point3D.create(lx1, ly1, 0),
            adsk.core.Point3D.create(lx2, ly2, 0),
        )
    return sketch.profiles.count
