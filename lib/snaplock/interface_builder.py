"""
Interface-only SnapLock builder — adds locking features to an EXISTING
user container body instead of generating a complete receiver.

v0.10.0 (previous): used world-XZ sketches, required container axis
parallel to world +Z.

v0.11.0 (this file): uses a frame-aware approach. The CylinderFrame
abstraction (frame.py) lets us sketch on an on-the-fly radial plane
containing the cylinder's actual axis, so the interface can be applied
to a container at any orientation.

Build sequence:
  1. Read the selected face into a CylinderFrame
  2. Validate iparams (with cavity_inner_radius populated from the frame)
  3. Create an on-demand radial construction plane through the cylinder axis
  4. Sketch slot + entry tool profiles in frame-local (R, Z_along) coords
  5. Revolve around a frame-local construction axis → tool bodies
  6. Body-pattern tool bodies around the frame axis
  7. Combine-cut all tools from the user's target body
  8. Verify wall consistency via pointContainment probes in frame coords
  9. Build snap columns on a frame-perpendicular cross-section plane,
     extrude along the axis, pattern, combine-join
  10. Verify columns present; fillet tips (non-fatal)
  11. Optionally generate a matching Lid and orient it to the frame
"""
import math
from typing import Optional

import adsk.core  # type: ignore
import adsk.fusion  # type: ignore

from .parameters import SnaplockParams, SnaplockInterfaceParams
from .lid_builder import build_lid
from .frame import (
    CylinderFrame,
    frame_from_cylinder_face,
    create_radial_plane,
    create_cross_section_plane,
    create_frame_axis,
    sketch_radial_profile_in_frame,
    cylindrical_to_world,
)
from .geometry_utils import (
    combine_bodies,
    create_component_at,
)


# ============================================================
# Public API
# ============================================================

def build_snaplock_interface(
    iparams: SnaplockInterfaceParams,
    design: "adsk.fusion.Design",
    target_face: "adsk.fusion.BRepFace",
) -> dict:
    """
    Add SnapLock locking features to the body that owns `target_face`.

    v0.11.0: works for arbitrary cylinder orientations. The face's axis
    direction is used to construct local sketch planes and the revolve
    axis; nothing assumes world-Z alignment anymore.

    Args:
        iparams: interface parameters (cavity_inner_radius and
            slot_ceiling_z may be zero — they're populated from the
            face's frame here).
        design: active Fusion design
        target_face: a cylindrical BRepFace — any orientation.
    """
    frame = frame_from_cylinder_face(target_face)
    if frame is None:
        raise ValueError(
            "SnapLock Interface requires a cylindrical face. "
            "Selected face is not a cylinder."
        )

    # Populate iparams from frame if the dialog/MCP call didn't already
    if iparams.cavity_inner_radius <= 0:
        iparams.cavity_inner_radius = frame.radius_cm
    # slot_ceiling_z in iparams is in frame-local Z (distance along axis
    # from frame origin), not world Z. Default to the face's top edge.
    if iparams.slot_ceiling_z == 0.0:
        iparams.slot_ceiling_z = frame.face_top_cm

    iparams.validate_or_raise()

    target_body = target_face.body
    target_component = target_body.parentComponent
    initial_volume = target_body.volume

    # Equivalent SnaplockParams for lid generation + shared derived geometry
    sp = iparams.to_equivalent_snaplock_params()
    warnings: list = []

    # --- 1: Construct a reusable frame-local revolve axis once ---
    frame_axis = create_frame_axis(target_component, frame)

    # --- 2: Cut slots + entries (frame-aware) ---
    _cut_slots_and_entries_in_frame(
        sp, target_component, target_body, frame,
        slot_ceiling_z=iparams.slot_ceiling_z,
        revolve_axis=frame_axis,
    )

    # --- 3: Verify wall consistency at slot midpoints ---
    slot_angles_deg = _slot_midpoint_angles(sp)
    probe_z_along = iparams.slot_ceiling_z - (iparams.rim_height / 2)
    scan_min_cm = iparams.cavity_inner_radius - 0.1
    scan_max_cm = iparams.cavity_inner_radius + 2.0
    scan_step_cm = 0.025  # 0.25 mm
    scan_range = [
        round(scan_min_cm + i * scan_step_cm, 4)
        for i in range(int((scan_max_cm - scan_min_cm) / scan_step_cm) + 1)
    ]
    wall_check = _verify_wall_consistency_in_frame(
        target_body, frame, slot_angles_deg, probe_z_along, scan_range,
    )
    if not wall_check["consistent"]:
        raise RuntimeError(
            f"Slot cuts produced inconsistent wall depth: {wall_check['angles']}. "
            f"Expected a single R value, got {wall_check['r_values']}. "
            "Container cavity may not be fully concentric with the selected face."
        )
    detected_wall_inner_r_cm = wall_check["r_values"][0]

    # --- 4: Snap columns (frame-aware) ---
    _build_snap_columns_in_frame(
        sp, target_component, target_body, frame,
        slot_ceiling_z=iparams.slot_ceiling_z,
        detected_wall_inner_r_cm=detected_wall_inner_r_cm,
        revolve_axis=frame_axis,
    )

    # --- 5: Verify columns present ---
    column_check = _verify_columns_in_frame(
        sp, target_body, frame,
        slot_ceiling_z=iparams.slot_ceiling_z,
    )
    if not column_check["all_present"]:
        warnings.append(
            f"Column verification: only {column_check['present_count']}/{sp.num_tabs} "
            f"columns detected. Details: {column_check['details']}"
        )

    # --- 6: Fillet column tips (non-fatal) ---
    try:
        filleted = _fillet_column_tips_in_frame(
            sp, target_component, target_body, frame,
            slot_ceiling_z=iparams.slot_ceiling_z,
        )
        if filleted < sp.num_tabs:
            warnings.append(
                f"Only {filleted}/{sp.num_tabs} column tips filleted "
                "(edge detection limitation — mechanism still works)"
            )
    except Exception as e:
        warnings.append(f"Column fillet failed (non-fatal): {e}")

    receiver_result = {
        "body": target_body,
        "component": target_component,
        "volume_mm3": target_body.volume * 1000,
        "initial_volume_mm3": initial_volume * 1000,
        "detected_wall_inner_r_mm": detected_wall_inner_r_cm * 10,
        "frame_axis": {
            "world_aligned": frame.is_world_z_aligned,
            "direction": list(frame.axis),
        },
        "column_check": column_check,
        "warnings": warnings,
    }

    # --- 7: Generate matching Lid (optional) ---
    lid_result = None
    if iparams.create_matching_lid:
        lid_result = _build_matching_lid(
            sp, iparams, design, frame, warnings,
        )

    return {
        "receiver": receiver_result,
        "lid": lid_result,
        "warnings": warnings,
        "params_mm": iparams.to_mm_dict(),
    }


# ============================================================
# Lid generation + orientation
# ============================================================

def _build_matching_lid(
    sp: SnaplockParams,
    iparams: SnaplockInterfaceParams,
    design: "adsk.fusion.Design",
    frame: CylinderFrame,
    warnings: list,
) -> Optional[dict]:
    """
    Generate the Lid as a standalone component, then orient and position
    it to mate with the user's container.

    The lid_builder produces a Lid whose cap sits at world Z=0 looking
    +Z (that's the convention — see lid_builder.py). For a world-Z-aligned
    container, we just translate the Lid up to the slot ceiling (+ the
    build offset during construction). For a tilted container, we need
    to rotate the Lid to match the frame's axis and then translate.
    """
    root_comp = design.rootComponent
    # Build at +offset along the lid's own Z so the fresh geometry
    # is far from any target body during construction.
    lid_occ = create_component_at(
        root_comp,
        iparams.lid_name,
        z_offset_cm=sp.lid_build_z_offset,
    )
    try:
        lid_result = build_lid(sp, lid_occ)
    except Exception as e:
        warnings.append(f"Lid generation failed: {e}")
        try:
            lid_occ.deleteMe()
        except Exception:
            pass
        return None

    warnings.extend(lid_result.get("warnings", []))

    # Compute the assembly transform: rotate Lid's +Z to match frame axis,
    # then translate so the lid's cap sits at the frame's slot_ceiling_z.
    transform = _lid_assembly_transform(frame, iparams.slot_ceiling_z)
    lid_occ.transform = transform

    lid_result["oriented"] = not frame.is_world_z_aligned
    return lid_result


def _lid_assembly_transform(
    frame: CylinderFrame,
    slot_ceiling_z_along: float,
) -> "adsk.core.Matrix3D":
    """
    Build a Fusion Matrix3D that orients + positions a Lid occurrence so
    its locally-up axis aligns with the frame's axis and its cap sits at
    the frame's slot ceiling point.

    For a world-Z-aligned frame, this reduces to a pure translation along
    +Z (which is what the original receiver_builder's move_occurrence_z
    achieves). For a tilted frame, we construct a rotation that maps
    world +Z → frame.axis and compose it with the translation.
    """
    # Target point = frame.origin + slot_ceiling_z_along * frame.axis
    target_point = cylindrical_to_world(
        frame.origin, frame.axis, frame.perp,
        r=0.0, z_along=slot_ceiling_z_along, theta_rad=0.0,
    )

    m = adsk.core.Matrix3D.create()

    if frame.is_world_z_aligned:
        # Pure translation — the lid's native +Z already matches the frame
        m.translation = adsk.core.Vector3D.create(*target_point)
        return m

    # Build a rotation matrix that sends world +Z to frame.axis.
    # Use axis-angle: rotation axis = (world_z × frame.axis), normalized;
    # angle = acos(world_z · frame.axis).
    fz = (0.0, 0.0, 1.0)
    fa = frame.axis
    dot = fz[0] * fa[0] + fz[1] * fa[1] + fz[2] * fa[2]
    # Guard: if frame axis is (anti)parallel to world Z, no rotation (or 180°)
    if dot > 0.9999:
        m.translation = adsk.core.Vector3D.create(*target_point)
        return m
    if dot < -0.9999:
        # 180° flip around any perpendicular — use frame.perp
        rot_axis = adsk.core.Vector3D.create(*frame.perp)
        m.setToRotation(
            math.pi,
            rot_axis,
            adsk.core.Point3D.create(0, 0, 0),
        )
        m.translation = adsk.core.Vector3D.create(*target_point)
        return m

    # General case: cross product gives the rotation axis
    rx = fz[1] * fa[2] - fz[2] * fa[1]
    ry = fz[2] * fa[0] - fz[0] * fa[2]
    rz = fz[0] * fa[1] - fz[1] * fa[0]
    rot_axis_vec = adsk.core.Vector3D.create(rx, ry, rz)
    rot_axis_vec.normalize()
    angle = math.acos(max(-1.0, min(1.0, dot)))

    m.setToRotation(
        angle,
        rot_axis_vec,
        adsk.core.Point3D.create(0, 0, 0),
    )
    m.translation = adsk.core.Vector3D.create(*target_point)
    return m


# ============================================================
# Frame-aware slot + entry cut
# ============================================================

def _slot_midpoint_angles(params: SnaplockParams) -> list:
    half_tab = params.tab_revolve_angle / 2
    sector = 360.0 / params.num_tabs
    return [half_tab + i * sector for i in range(params.num_tabs)]


def _snapshot_bodies(component: "adsk.fusion.Component") -> int:
    """
    Snapshot the body count so we can identify new bodies after an op.

    BRepBody is not hashable, so we use the COUNT as a snapshot marker.
    This assumes Fusion appends new bodies to the end of the collection
    (which is its documented behavior).
    """
    return component.bRepBodies.count


def _bodies_added_since(component, before: int) -> list:
    """Return all bodies added after the snapshot count."""
    return [
        component.bRepBodies.item(i)
        for i in range(before, component.bRepBodies.count)
    ]


def _cut_slots_and_entries_in_frame(
    params: SnaplockParams,
    component: "adsk.fusion.Component",
    target_body: "adsk.fusion.BRepBody",
    frame: CylinderFrame,
    slot_ceiling_z: float,
    revolve_axis,
):
    """
    Build slot + entry tool bodies in the frame's radial plane, pattern
    around the frame axis, and Combine-Cut from the target body.
    """
    Z_wall_top = slot_ceiling_z
    Z_tab_top = Z_wall_top - params.rim_height
    Z_tab_drop = Z_tab_top - params.tab_drop_height
    Z_tab_bottom = Z_tab_top - params.tab_drop_height - params.tab_chamfer_drop

    R_inner = params.rim_inner_radius
    R_outer = params.tab_tip_radius

    before = _snapshot_bodies(component)

    # Build the reusable radial sketch plane once (both slot and entry
    # profiles sit on the same plane — they're on different angular
    # offsets from the revolve axis, not different planes).
    radial_plane = create_radial_plane(component, frame)

    # --- Slot profile (tab shape, revolved by +tab_revolve_angle) ---
    slot_sketch = component.sketches.add(radial_plane)
    slot_points = [
        (R_inner, Z_tab_top),
        (R_outer, Z_tab_top),
        (R_outer, Z_tab_drop),
        (R_inner, Z_tab_bottom),
    ]
    sketch_radial_profile_in_frame(slot_sketch, frame, slot_points)
    slot_profile = slot_sketch.profiles.item(0)
    slot_rev = _revolve_around_axis(
        component, slot_profile, revolve_axis,
        f"{params.tab_revolve_angle} deg",
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    slot_body = slot_rev.bodies.item(0)

    # --- Entry profile (tab + rectangle to wall top, revolved the other way) ---
    entry_sketch = component.sketches.add(radial_plane)
    entry_points = [
        (R_inner, Z_tab_bottom),
        (R_outer, Z_tab_drop),
        (R_outer, Z_wall_top),
        (R_inner, Z_wall_top),
    ]
    sketch_radial_profile_in_frame(entry_sketch, frame, entry_points)
    entry_profile = entry_sketch.profiles.item(0)
    entry_rev = _revolve_around_axis(
        component, entry_profile, revolve_axis,
        f"-{params.slot_entry_angle} deg",
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    entry_body = entry_rev.bodies.item(0)

    # Pattern both tool bodies around the frame axis
    _pattern_bodies_around_axis(
        component, [slot_body, entry_body], revolve_axis,
        count=params.num_tabs,
        total_angle_expr="360 deg",
    )

    tool_bodies = _bodies_added_since(component, before)
    combine_bodies(
        component,
        target=target_body,
        tools=tool_bodies,
        operation=adsk.fusion.FeatureOperations.CutFeatureOperation,
        keep_tools=False,
    )


def _revolve_around_axis(
    component: "adsk.fusion.Component",
    profile: "adsk.fusion.Profile",
    axis,
    angle_expr: str,
    operation: int,
):
    """Revolve a profile around an explicit construction axis."""
    revolves = component.features.revolveFeatures
    rev_input = revolves.createInput(profile, axis, operation)
    rev_input.setAngleExtent(False, adsk.core.ValueInput.createByString(angle_expr))
    return revolves.add(rev_input)


def _pattern_bodies_around_axis(
    component: "adsk.fusion.Component",
    bodies: list,
    axis,
    count: int,
    total_angle_expr: str,
):
    """Circular-pattern bodies around an explicit construction axis."""
    patterns = component.features.circularPatternFeatures
    body_coll = adsk.core.ObjectCollection.create()
    for b in bodies:
        body_coll.add(b)
    pat_input = patterns.createInput(body_coll, axis)
    pat_input.quantity = adsk.core.ValueInput.createByReal(count)
    pat_input.totalAngle = adsk.core.ValueInput.createByString(total_angle_expr)
    pat_input.isSymmetric = False
    return patterns.add(pat_input)


# ============================================================
# Frame-aware snap columns
# ============================================================

def _build_snap_columns_in_frame(
    params: SnaplockParams,
    component: "adsk.fusion.Component",
    target_body: "adsk.fusion.BRepBody",
    frame: CylinderFrame,
    slot_ceiling_z: float,
    detected_wall_inner_r_cm: float,
    revolve_axis,
):
    """
    Build snap columns on a frame-perpendicular cross-section plane and
    Join them into the target body.

    The sketch plane is perpendicular to the frame axis at Z=slot_ceiling_z.
    Each column is a circle on that plane, extruded along the axis
    direction down through the wall.
    """
    wall_inner_cm = detected_wall_inner_r_cm
    col_r_cm = params.column_radial_pos
    col_radius = params.column_radius

    inner_edge = col_r_cm - col_radius
    outer_edge = col_r_cm + col_radius
    if not (inner_edge < wall_inner_cm < outer_edge):
        col_r_cm = wall_inner_cm + col_radius * 0.5

    before = _snapshot_bodies(component)

    # Cross-section plane at the slot ceiling
    cross_plane = create_cross_section_plane(
        component, frame, z_along_cm=slot_ceiling_z,
    )

    sketch = component.sketches.add(cross_plane)

    # Project the column circle's CENTER into sketch-local coordinates.
    # On a cross-section plane, the sketch's origin is at the cylinder axis
    # (where the plane intersects it), and sketch-X / sketch-Y span the
    # radial directions. We compute the column's world position first, then
    # project into sketch local.
    first_angle_deg = params.tab_revolve_angle / 2
    first_angle_rad = math.radians(first_angle_deg)

    col_world = frame.point_at(
        r=col_r_cm,
        z_along=slot_ceiling_z,
        theta_rad=first_angle_rad,
    )

    so = sketch.origin
    sx_dir = sketch.xDirection
    sy_dir = sketch.yDirection
    dx = col_world[0] - so.x
    dy = col_world[1] - so.y
    dz = col_world[2] - so.z
    sxy_x = dx * sx_dir.x + dy * sx_dir.y + dz * sx_dir.z
    sxy_y = dx * sy_dir.x + dy * sy_dir.y + dz * sy_dir.z

    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(sxy_x, sxy_y, 0),
        col_radius,
    )

    # Extrude along the negative axis direction (into the wall).
    extrude_distance = params.body_height + params.column_protrusion
    prof = sketch.profiles.item(0)
    extrudes = component.features.extrudeFeatures
    ext_input = extrudes.createInput(
        prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    ext_input.setOneSideExtent(
        adsk.fusion.DistanceExtentDefinition.create(
            adsk.core.ValueInput.createByReal(extrude_distance)
        ),
        adsk.fusion.ExtentDirections.NegativeExtentDirection,
    )
    extrudes.add(ext_input)

    col_bodies_created = _bodies_added_since(component, before)
    _pattern_bodies_around_axis(
        component, col_bodies_created, revolve_axis,
        count=params.num_tabs,
        total_angle_expr="360 deg",
    )

    all_column_bodies = _bodies_added_since(component, before)
    combine_bodies(
        component,
        target=target_body,
        tools=all_column_bodies,
        operation=adsk.fusion.FeatureOperations.JoinFeatureOperation,
        keep_tools=False,
    )


# ============================================================
# Frame-aware verification
# ============================================================

def _verify_wall_consistency_in_frame(
    body: "adsk.fusion.BRepBody",
    frame: CylinderFrame,
    angles_deg: list,
    z_along_cm: float,
    r_scan_cm: list,
) -> dict:
    """
    Probe pointContainment at frame-local cylindrical coordinates to find
    the R where each angular slice's wall starts.
    """
    angles = {}
    for ang_deg in angles_deg:
        found_r = None
        theta_rad = math.radians(ang_deg)
        for r in r_scan_cm:
            world = frame.point_at(r=r, z_along=z_along_cm, theta_rad=theta_rad)
            pt = adsk.core.Point3D.create(*world)
            if body.pointContainment(pt) == 0:  # PointInside
                found_r = round(r * 10, 3)  # return in mm for reporting
                break
        angles[ang_deg] = found_r

    r_values = sorted({v for v in angles.values() if v is not None})
    return {
        "consistent": len(r_values) == 1,
        "angles": angles,
        "r_values": [v / 10.0 for v in r_values],  # back to cm for the caller
    }


def _verify_columns_in_frame(
    params: SnaplockParams,
    target_body: "adsk.fusion.BRepBody",
    frame: CylinderFrame,
    slot_ceiling_z: float,
) -> dict:
    """Probe each slot midpoint (in frame coords) to verify a column is present."""
    angles_deg = _slot_midpoint_angles(params)
    z_probe_along = slot_ceiling_z - (params.rim_height + params.column_protrusion / 2)
    r_probe_cm = params.column_radial_pos

    details = {}
    present_count = 0
    status_map = {0: "IN", 1: "FACE", 2: "OUT"}
    for ang_deg in angles_deg:
        theta_rad = math.radians(ang_deg)
        world = frame.point_at(r=r_probe_cm, z_along=z_probe_along, theta_rad=theta_rad)
        pt = adsk.core.Point3D.create(*world)
        status = status_map.get(target_body.pointContainment(pt), "?")
        details[ang_deg] = status
        if status in ("IN", "FACE"):
            present_count += 1

    return {
        "all_present": present_count == params.num_tabs,
        "present_count": present_count,
        "total": params.num_tabs,
        "details": details,
        "probe_point": {"r_cm": r_probe_cm, "z_along_cm": z_probe_along},
    }


def _fillet_column_tips_in_frame(
    params: SnaplockParams,
    component: "adsk.fusion.Component",
    target_body: "adsk.fusion.BRepBody",
    frame: CylinderFrame,
    slot_ceiling_z: float,
) -> int:
    """
    Find circular edges at the column tip Z and fillet them.

    Tip Z in frame-local coords = slot_ceiling_z - rim_height - column_protrusion.
    We can't easily compare edge Z directly in world coords for a tilted frame,
    so we project each edge's midpoint into frame-local coords and check the
    Z_along component.
    """
    tip_z_along = slot_ceiling_z - (params.rim_height + params.column_protrusion)
    tip_circumference_cm = math.pi * params.column_diameter
    tolerance_cm = 0.05

    edges_coll = adsk.core.ObjectCollection.create()
    axis = frame.axis
    origin = frame.origin
    for ei in range(target_body.edges.count):
        edge = target_body.edges.item(ei)
        if abs(edge.length - tip_circumference_cm) > tolerance_cm:
            continue
        try:
            evaluator = edge.evaluator
            _, pt = evaluator.getPointAtParameter(0)
            # Project onto frame axis to get z_along in frame coords
            rel_x = pt.x - origin[0]
            rel_y = pt.y - origin[1]
            rel_z = pt.z - origin[2]
            z_along = rel_x * axis[0] + rel_y * axis[1] + rel_z * axis[2]
            if abs(z_along - tip_z_along) < 0.02:  # 0.2 mm tolerance
                edges_coll.add(edge)
        except Exception:
            continue

    if edges_coll.count == 0:
        return 0

    fillets = component.features.filletFeatures
    fillet_input = fillets.createInput()
    fillet_radius = min(params.column_radius * 0.3, params.column_protrusion * 0.4)
    fillet_input.addConstantRadiusEdgeSet(
        edges_coll,
        adsk.core.ValueInput.createByReal(fillet_radius),
        True,
    )
    try:
        fillets.add(fillet_input)
        return edges_coll.count
    except Exception:
        return 0


# ============================================================
# Backward compatibility shim
# ============================================================
# The v0.10.0 command dialog imports `_read_face_frame` from this module.
# Keep a compatibility shim that returns the old dict shape from a
# CylinderFrame. New callers should use frame_from_cylinder_face directly.

def _read_face_frame(face) -> dict:
    """Deprecated — retained for v0.10.0 dialog compatibility."""
    cf = frame_from_cylinder_face(face)
    if cf is None:
        return None
    return {
        "radius_cm": cf.radius_cm,
        "top_z_cm": cf.face_top_cm,
        "bot_z_cm": cf.face_bot_cm,
        "height_cm": cf.face_height_cm,
    }
