"""
Reusable geometry helpers for SnapLock build.

All coordinate values in CENTIMETERS (Fusion's native unit).
The XZ-plane sketching helpers handle the Z-negation automatically
(on XZ sketch, sketch_y = -world_z).
"""
import math
from typing import Optional, List

# adsk modules are only available inside Fusion 360's Python environment.
# These imports will be resolved at runtime when the add-in loads.
import adsk.core  # type: ignore
import adsk.fusion  # type: ignore


# ============================================================
# Sketch profile construction
# ============================================================

def sketch_xz_closed_profile(sketch: adsk.fusion.Sketch, points_rz: list) -> int:
    """
    Draw a closed polyline on an XZ-plane sketch from (R, Z) tuples in cm.
    Handles the XZ sketch Y-axis negation.

    Args:
        sketch: An XZ-plane sketch
        points_rz: List of (R, Z) tuples in centimeters

    Returns:
        Number of profiles in the sketch after drawing (should be 1 for simple cases)
    """
    lines = sketch.sketchCurves.sketchLines
    for i in range(len(points_rz)):
        r1, z1 = points_rz[i]
        r2, z2 = points_rz[(i + 1) % len(points_rz)]
        # XZ sketch: sketch_x = R (world X), sketch_y = -world_Z
        p1 = adsk.core.Point3D.create(r1, -z1, 0)
        p2 = adsk.core.Point3D.create(r2, -z2, 0)
        lines.addByTwoPoints(p1, p2)
    return sketch.profiles.count


# ============================================================
# Revolve helpers
# ============================================================

def revolve_profile(
    component: adsk.fusion.Component,
    profile: adsk.fusion.Profile,
    angle_expr: str,
    operation: int,
) -> adsk.fusion.RevolveFeature:
    """
    Revolve a profile around the component's Z axis.

    Args:
        component: Target component (determines Z axis reference)
        profile: The sketch profile to revolve
        angle_expr: Angle expression string, e.g., "360 deg" or "-25 deg"
        operation: adsk.fusion.FeatureOperations.* constant

    Returns:
        The created RevolveFeature
    """
    revolves = component.features.revolveFeatures
    z_axis = component.zConstructionAxis
    rev_input = revolves.createInput(profile, z_axis, operation)
    rev_input.setAngleExtent(False, adsk.core.ValueInput.createByString(angle_expr))
    return revolves.add(rev_input)


# ============================================================
# Body pattern + combine (proven strategy from SnapLock_v2)
# ============================================================

def pattern_bodies_around_z(
    component: adsk.fusion.Component,
    bodies: list,
    count: int,
    total_angle_expr: str = "360 deg",
) -> adsk.fusion.CircularPatternFeature:
    """
    Body-level circular pattern around the component's Z axis.
    This is the PROVEN approach from SnapLock_v2 — feature patterns fail
    unpredictably in multi-component designs; body patterns are consistent.

    Args:
        component: Target component
        bodies: List of BRepBody instances to pattern
        count: Total number of instances (including originals)
        total_angle_expr: Angular span, default "360 deg" for full circle
    """
    patterns = component.features.circularPatternFeatures
    z_axis = component.zConstructionAxis

    body_coll = adsk.core.ObjectCollection.create()
    for b in bodies:
        body_coll.add(b)

    pat_input = patterns.createInput(body_coll, z_axis)
    pat_input.quantity = adsk.core.ValueInput.createByReal(count)
    pat_input.totalAngle = adsk.core.ValueInput.createByString(total_angle_expr)
    pat_input.isSymmetric = False
    return patterns.add(pat_input)


def combine_bodies(
    component: adsk.fusion.Component,
    target: adsk.fusion.BRepBody,
    tools: list,
    operation: int,
    keep_tools: bool = False,
) -> adsk.fusion.CombineFeature:
    """
    Boolean combine with explicit target and tool bodies.

    Args:
        component: Target component
        target: The body that receives the operation
        tools: List of tool bodies
        operation: adsk.fusion.FeatureOperations.{Join,Cut,Intersect}FeatureOperation
        keep_tools: If False (default), tool bodies are consumed
    """
    combines = component.features.combineFeatures
    tool_coll = adsk.core.ObjectCollection.create()
    for t in tools:
        tool_coll.add(t)
    comb_input = combines.createInput(target, tool_coll)
    comb_input.operation = operation
    comb_input.isKeepToolBodies = keep_tools
    return combines.add(comb_input)


# ============================================================
# Point containment verification (the key debugging technique)
# ============================================================

def wall_radius_at(
    body: "adsk.fusion.BRepBody",
    angle_deg: float,
    z_cm: float,
    r_scan_mm: Optional[List[float]] = None,
) -> Optional[float]:
    """
    Find the smallest R (in mm) where the body contains a point at the given
    angle and Z. Returns None if no point inside the scan range.

    Used to verify wall depth consistency after slot cuts.
    """
    if r_scan_mm is None:
        r_scan_mm = [24.0, 24.5, 25.0, 25.25, 25.5, 25.75, 26.0, 26.5, 27.0, 28.0]

    rad = math.radians(angle_deg)
    for r_mm in r_scan_mm:
        r_cm = r_mm / 10
        pt = adsk.core.Point3D.create(
            r_cm * math.cos(rad),
            r_cm * math.sin(rad),
            z_cm,
        )
        if body.pointContainment(pt) == 0:  # PointInside
            return r_mm
    return None


def verify_wall_consistency(
    body: "adsk.fusion.BRepBody",
    angles_deg: list,
    z_cm: float,
    r_scan_mm: Optional[List[float]] = None,
) -> dict:
    """
    Check that the body's inner wall face is at the same R for all given angles.

    Args:
        body: Body to probe
        angles_deg: Angular positions to check (degrees)
        z_cm: Z level in cm
        r_scan_mm: Optional radial scan range (mm). If None, uses default range
                   suitable for ~60mm containers.

    Returns {
        'consistent': bool,
        'angles': {angle: r_mm, ...},
        'r_values': sorted list of distinct R values found,
    }
    """
    angles = {}
    for ang in angles_deg:
        angles[ang] = wall_radius_at(body, ang, z_cm, r_scan_mm=r_scan_mm)
    r_values = set(v for v in angles.values() if v is not None)
    return {
        "consistent": len(r_values) == 1,
        "angles": angles,
        "r_values": sorted(r_values),
    }


def verify_point_in_body(
    body: adsk.fusion.BRepBody,
    r_mm: float,
    angle_deg: float,
    z_mm: float,
) -> str:
    """Return 'IN', 'FACE', or 'OUT' for a cylindrical coordinate probe."""
    rad = math.radians(angle_deg)
    pt = adsk.core.Point3D.create(
        (r_mm / 10) * math.cos(rad),
        (r_mm / 10) * math.sin(rad),
        z_mm / 10,
    )
    c = body.pointContainment(pt)
    return {0: "IN", 1: "FACE", 2: "OUT"}.get(c, "?")


# ============================================================
# Component management
# ============================================================

def create_component_at(
    root_comp: adsk.fusion.Component,
    name: str,
    z_offset_cm: float = 0.0,
) -> adsk.fusion.Occurrence:
    """
    Create a new sub-component under root with an optional Z translation.
    Used to separate Lid and Receiver during modeling to avoid cross-component cuts.
    """
    transform = adsk.core.Matrix3D.create()
    if z_offset_cm != 0.0:
        transform.translation = adsk.core.Vector3D.create(0, 0, z_offset_cm)
    occ = root_comp.occurrences.addNewComponent(transform)
    occ.component.name = name
    return occ


def move_occurrence_z(occ: adsk.fusion.Occurrence, z_cm: float):
    """Set an occurrence's Z translation (cm). Used to place lid in assembly position."""
    t = adsk.core.Matrix3D.create()
    t.translation = adsk.core.Vector3D.create(0, 0, z_cm)
    occ.transform = t
