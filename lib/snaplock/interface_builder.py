"""
Interface-only SnapLock builder — adds locking features to an EXISTING
user container body instead of generating a complete receiver.

This is the "SnapLock Interface" command's backend. It mirrors the
receiver_builder's slot-cut + snap-column logic but applies it to a
target body that the user already built. A matching Lid is still
generated as a separate component (reusing build_lid unchanged).

Geometry constraints for v1:
  - The user's container must have its cylindrical axis parallel to
    world +Z (the slot cuts and columns are built relative to the
    component's XZ plane and Z axis).
  - The selected face must be a cylindrical inner wall of the container
    cavity. Its radius becomes `cavity_inner_radius` in the math; its
    top edge Z becomes `slot_ceiling_z`.

Build sequence:
  1. Validate iparams + read face geometry
  2. Shift coordinate math so Z=0 corresponds to the face top
  3. Cut slot + entry cavities into the user's body at the engagement zone
  4. Verify wall consistency (pointContainment probe at slot midpoints)
  5. Add snap columns joined into the wall material
  6. Verify column presence
  7. Fillet column tips (non-fatal)
  8. If create_matching_lid: build a standalone Lid component via build_lid

All dimensions in CENTIMETERS internally.
"""
import math
from typing import Optional

import adsk.core  # type: ignore
import adsk.fusion  # type: ignore

from .parameters import SnaplockParams, SnaplockInterfaceParams
from .lid_builder import build_lid
from .geometry_utils import (
    sketch_xz_closed_profile,
    revolve_profile,
    pattern_bodies_around_z,
    combine_bodies,
    verify_wall_consistency,
    verify_point_in_body,
    create_component_at,
    move_occurrence_z,
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

    Args:
        iparams: interface parameters (cavity_inner_radius and slot_ceiling_z
            may be set either before the call, or will be read from the face
            here if they're zero/unset).
        design: active Fusion design
        target_face: a cylindrical BRepFace that the user selected. This
            must belong to the receiver-side body. Its radius defines the
            cavity_inner_radius; the top edge of the face defines the
            slot_ceiling_z.

    Returns:
        {
            'receiver': { body, component, volume_mm3, column_check, ... },
            'lid': { ... } or None,
            'warnings': [...],
            'params_mm': {...},
        }
    """
    # --- Read face geometry and populate iparams ---
    frame = _read_face_frame(target_face)
    if frame is None:
        raise ValueError(
            "Selected face must be a cylindrical face whose axis is parallel to world +Z. "
            "SnapLock Interface requires a vertically-aligned container cavity wall."
        )

    # Populate cavity_inner_radius and slot_ceiling_z from the face if not set
    if iparams.cavity_inner_radius <= 0:
        iparams.cavity_inner_radius = frame["radius_cm"]
    if iparams.slot_ceiling_z == 0.0:
        iparams.slot_ceiling_z = frame["top_z_cm"]

    iparams.validate_or_raise()

    target_body = target_face.body
    target_component = target_body.parentComponent
    initial_volume = target_body.volume

    # Build an equivalent SnaplockParams for reusing the existing lid builder
    # and for sharing derived geometry helpers (tab radii, column position).
    sp = iparams.to_equivalent_snaplock_params()

    warnings: list = []

    # === Step 1: Cut slots + entries into the user's body ===
    _cut_slots_and_entries_on_body(
        sp, target_component, target_body,
        slot_ceiling_z_cm=iparams.slot_ceiling_z,
    )

    # === Step 2: Verify wall consistency ===
    slot_angles = _slot_midpoint_angles(sp)
    # Probe mid-height of the rim drop region (above any slot/entry cuts)
    probe_z_cm = iparams.slot_ceiling_z - (iparams.rim_height / 2)
    scan_min_mm = (iparams.cavity_inner_radius * 10) - 1.0
    # Extend scan generously outward — we don't know the container's actual
    # outer wall, so probe up to cavity + a generous wall allowance.
    scan_max_mm = (iparams.cavity_inner_radius * 10) + 20.0
    scan_step = 0.25
    scan_range = [
        round(scan_min_mm + i * scan_step, 2)
        for i in range(int((scan_max_mm - scan_min_mm) / scan_step) + 1)
    ]
    wall_check = verify_wall_consistency(
        target_body, slot_angles, probe_z_cm, r_scan_mm=scan_range
    )
    if not wall_check["consistent"]:
        raise RuntimeError(
            f"Slot cuts produced inconsistent wall depth across slot midpoints: "
            f"{wall_check['angles']}. Expected a single R value (the container's "
            f"cavity inner face), got {wall_check['r_values']}. This usually means "
            "the selected face isn't fully concentric, or the container has "
            "internal features that interfere with the slot cut region."
        )

    detected_wall_inner_r_mm = wall_check["r_values"][0]

    # === Step 3: Snap columns ===
    _build_snap_columns_on_body(
        sp, target_component, target_body,
        slot_ceiling_z_cm=iparams.slot_ceiling_z,
        detected_wall_inner_r_mm=detected_wall_inner_r_mm,
    )

    # === Step 4: Verify column presence ===
    column_check = _verify_columns_exist(
        sp, target_body,
        slot_ceiling_z_cm=iparams.slot_ceiling_z,
    )
    if not column_check["all_present"]:
        warnings.append(
            f"Column verification: only {column_check['present_count']}/{sp.num_tabs} "
            f"columns detected by pointContainment. Details: {column_check['details']}"
        )

    # === Step 5: Fillet column tips (non-fatal) ===
    try:
        filleted = _fillet_column_tips(
            sp, target_component, target_body,
            slot_ceiling_z_cm=iparams.slot_ceiling_z,
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
        "detected_wall_inner_r_mm": detected_wall_inner_r_mm,
        "column_check": column_check,
        "warnings": warnings,
    }

    # === Step 6: Generate matching Lid (optional) ===
    lid_result = None
    if iparams.create_matching_lid:
        root_comp = design.rootComponent
        lid_occ = create_component_at(
            root_comp,
            iparams.lid_name,
            z_offset_cm=sp.lid_build_z_offset,
        )
        try:
            lid_result = build_lid(sp, lid_occ)
            warnings.extend(lid_result.get("warnings", []))
            # Move Lid to assembly position (Z = slot_ceiling_z, i.e. sitting
            # at the top of the user's container)
            move_occurrence_z(lid_occ, iparams.slot_ceiling_z)
        except Exception as e:
            # Lid failure is non-fatal — the interface is already applied
            warnings.append(f"Lid generation failed: {e}")
            try:
                lid_occ.deleteMe()
            except Exception:
                pass
            lid_result = None

    return {
        "receiver": receiver_result,
        "lid": lid_result,
        "warnings": warnings,
        "params_mm": iparams.to_mm_dict(),
    }


# ============================================================
# Face geometry reading
# ============================================================

def _read_face_frame(face: "adsk.fusion.BRepFace") -> Optional[dict]:
    """
    Read a cylindrical face's geometry into a frame dict. Returns None
    if the face isn't a vertically-aligned cylinder.

    Frame fields (all cm):
        radius_cm: cylinder radius
        top_z_cm:  world Z of the face's top edge
        bot_z_cm:  world Z of the face's bottom edge
        height_cm: top_z - bot_z
    """
    geom = face.geometry
    if not isinstance(geom, adsk.core.Cylinder):
        return None

    # Axis must be ±Z for v1 (XZ-plane sketching assumption)
    axis = adsk.core.Vector3D.create(geom.axis.x, geom.axis.y, geom.axis.z)
    axis.normalize()
    if abs(axis.z) < 0.99:
        return None

    # Scan the face's vertices to find Z extent
    min_z = float('inf')
    max_z = float('-inf')
    for ei in range(face.edges.count):
        edge = face.edges.item(ei)
        for vertex in (edge.startVertex, edge.endVertex):
            if vertex is None:
                continue
            z = vertex.geometry.z
            if z < min_z:
                min_z = z
            if z > max_z:
                max_z = z

    if min_z == float('inf'):
        # Fall back to bounding box
        bb = face.boundingBox
        min_z = bb.minPoint.z
        max_z = bb.maxPoint.z

    return {
        "radius_cm": geom.radius,
        "top_z_cm": max_z,
        "bot_z_cm": min_z,
        "height_cm": max_z - min_z,
    }


# ============================================================
# Slot + entry cuts (on existing body, at arbitrary Z reference)
# ============================================================

def _slot_midpoint_angles(params: SnaplockParams) -> list:
    """Angular midpoints of each slot in degrees. Copy of receiver_builder's helper."""
    half_tab = params.tab_revolve_angle / 2
    sector = 360.0 / params.num_tabs
    return [half_tab + i * sector for i in range(params.num_tabs)]


def _snapshot_bodies(component: "adsk.fusion.Component") -> set:
    """Snapshot the set of body indices currently in the component."""
    return {component.bRepBodies.item(i) for i in range(component.bRepBodies.count)}


def _bodies_added_since(
    component: "adsk.fusion.Component",
    before: set,
) -> list:
    """Return bodies present in `component` that weren't in `before`."""
    return [
        component.bRepBodies.item(i)
        for i in range(component.bRepBodies.count)
        if component.bRepBodies.item(i) not in before
    ]


def _cut_slots_and_entries_on_body(
    params: SnaplockParams,
    component: "adsk.fusion.Component",
    target_body: "adsk.fusion.BRepBody",
    slot_ceiling_z_cm: float,
):
    """
    Build slot + entry tool bodies, pattern them, and Cut from target_body.

    The target body belongs to `component`. Tool bodies are built on
    `component`'s XZ plane (requires the target to be axis-aligned with
    world Z — enforced by _read_face_frame).

    Z math is shifted so that `slot_ceiling_z_cm` plays the role the
    receiver_builder calls "Z_wall_top" (= 0 in its hardcoded version).
    """
    Z_wall_top = slot_ceiling_z_cm
    Z_tab_top = Z_wall_top - params.rim_height
    Z_tab_drop = Z_tab_top - params.tab_drop_height
    Z_tab_bottom = Z_tab_top - params.tab_drop_height - params.tab_chamfer_drop

    R_inner = params.rim_inner_radius
    R_outer = params.tab_tip_radius

    before = _snapshot_bodies(component)

    # --- Slot profile (tab shape) ---
    slot_points = [
        (R_inner, Z_tab_top),
        (R_outer, Z_tab_top),
        (R_outer, Z_tab_drop),
        (R_inner, Z_tab_bottom),
    ]
    slot_sketch = component.sketches.add(component.xZConstructionPlane)
    sketch_xz_closed_profile(slot_sketch, slot_points)
    slot_profile = slot_sketch.profiles.item(0)
    slot_rev = revolve_profile(
        component, slot_profile,
        f"{params.tab_revolve_angle} deg",
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    slot_body = slot_rev.bodies.item(0)

    # --- Entry profile (tab shape extended up to wall top) ---
    entry_points = [
        (R_inner, Z_tab_bottom),
        (R_outer, Z_tab_drop),
        (R_outer, Z_wall_top),
        (R_inner, Z_wall_top),
    ]
    entry_sketch = component.sketches.add(component.xZConstructionPlane)
    sketch_xz_closed_profile(entry_sketch, entry_points)
    entry_profile = entry_sketch.profiles.item(0)
    entry_rev = revolve_profile(
        component, entry_profile,
        f"-{params.slot_entry_angle} deg",
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    entry_body = entry_rev.bodies.item(0)

    # --- Pattern both tool bodies around Z ---
    pattern_bodies_around_z(
        component,
        [slot_body, entry_body],
        count=params.num_tabs,
        total_angle_expr="360 deg",
    )

    # All new bodies are tools
    tool_bodies = _bodies_added_since(component, before)

    # Combine-cut from the user's existing target body
    combine_bodies(
        component,
        target=target_body,
        tools=tool_bodies,
        operation=adsk.fusion.FeatureOperations.CutFeatureOperation,
        keep_tools=False,
    )


# ============================================================
# Snap columns (on existing body, at arbitrary Z reference)
# ============================================================

def _build_snap_columns_on_body(
    params: SnaplockParams,
    component: "adsk.fusion.Component",
    target_body: "adsk.fusion.BRepBody",
    slot_ceiling_z_cm: float,
    detected_wall_inner_r_mm: float,
):
    """
    Build snap columns and Join them into the user's target body.
    Z-reference-aware version of receiver_builder._build_snap_columns.
    """
    wall_inner_cm = detected_wall_inner_r_mm / 10.0
    col_r_cm = params.column_radial_pos
    col_radius = params.column_radius

    # Safety: column's inner edge must straddle the wall inner face so
    # the protrusion is visible on the slot side but the column body
    # still overlaps solid material for the Join to work.
    inner_edge = col_r_cm - col_radius
    outer_edge = col_r_cm + col_radius
    if not (inner_edge < wall_inner_cm < outer_edge):
        col_r_cm = wall_inner_cm + col_radius * 0.5

    before = _snapshot_bodies(component)

    # Sketch plane at the slot ceiling Z (the wall top of the interface feature)
    planes = component.constructionPlanes
    plane_in = planes.createInput()
    plane_in.setByOffset(
        component.xYConstructionPlane,
        adsk.core.ValueInput.createByReal(slot_ceiling_z_cm),
    )
    col_plane = planes.add(plane_in)

    sketch = component.sketches.add(col_plane)
    first_angle_deg = params.tab_revolve_angle / 2
    rad = math.radians(first_angle_deg)
    cx = col_r_cm * math.cos(rad)
    cy = col_r_cm * math.sin(rad)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(cx, cy, 0),
        col_radius,
    )

    # Extrude downward from the slot ceiling into the wall + protrusion
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

    # Pattern around Z
    col_bodies_created = _bodies_added_since(component, before)
    pattern_bodies_around_z(
        component,
        col_bodies_created,
        count=params.num_tabs,
        total_angle_expr="360 deg",
    )

    # Every new body since snapshot is a column body to join
    all_column_bodies = _bodies_added_since(component, before)

    combine_bodies(
        component,
        target=target_body,
        tools=all_column_bodies,
        operation=adsk.fusion.FeatureOperations.JoinFeatureOperation,
        keep_tools=False,
    )


# ============================================================
# Verification (copies of receiver_builder logic, Z-reference aware)
# ============================================================

def _verify_columns_exist(
    params: SnaplockParams,
    target_body: "adsk.fusion.BRepBody",
    slot_ceiling_z_cm: float,
) -> dict:
    """Probe each slot midpoint to verify a column is present."""
    angles = _slot_midpoint_angles(params)

    # Probe point: below slot ceiling by (rim_height + column_protrusion/2) cm
    z_probe_cm = slot_ceiling_z_cm - (params.rim_height + params.column_protrusion / 2)
    z_probe_mm = z_probe_cm * 10
    r_probe_mm = params.column_radial_pos * 10

    details = {}
    present_count = 0
    for ang in angles:
        status = verify_point_in_body(target_body, r_probe_mm, ang, z_probe_mm)
        details[ang] = status
        if status in ("IN", "FACE"):
            present_count += 1

    return {
        "all_present": present_count == params.num_tabs,
        "present_count": present_count,
        "total": params.num_tabs,
        "details": details,
        "probe_point": {"r_mm": r_probe_mm, "z_mm": z_probe_mm},
    }


def _fillet_column_tips(
    params: SnaplockParams,
    component: "adsk.fusion.Component",
    target_body: "adsk.fusion.BRepBody",
    slot_ceiling_z_cm: float,
) -> int:
    """Find circular edges at the column tip Z position and fillet them."""
    tip_z_cm = slot_ceiling_z_cm - (params.rim_height + params.column_protrusion)
    tip_circumference_mm = math.pi * params.column_diameter * 10
    tolerance_mm = 0.5

    edges_coll = adsk.core.ObjectCollection.create()
    for ei in range(target_body.edges.count):
        edge = target_body.edges.item(ei)
        length_mm = edge.length * 10
        if abs(length_mm - tip_circumference_mm) > tolerance_mm:
            continue
        try:
            evaluator = edge.evaluator
            _, pt = evaluator.getPointAtParameter(0)
            z_mm = pt.z * 10
            if abs(z_mm - tip_z_cm * 10) < 0.2:
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
