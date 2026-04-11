"""
Receiver (bottom half) builder — the cup that catches the lid.

Build sequence (proven in SnapLock_v2 rebuild):
  1. Revolve cross-section on XZ plane → receiver base body (single body)
  2. Create ONE slot tool body at 0° on XZ plane (NewBody revolve 20°)
  3. Create ONE entry tool body at 0° on XZ plane (NewBody revolve -25°)
  4. Body-pattern BOTH tool bodies around Z × num_tabs
  5. Combine-Cut all 2N tool bodies from the receiver body at once
  6. VERIFY wall consistency with pointContainment at all slot midpoints
  7. Create ONE snap column body at 0° (extrude on XY plane, through the wall)
  8. Body-pattern the column × num_tabs
  9. Combine-Join all columns to the receiver body
  10. Verify columns exist at all positions
  11. (Optional) Fillet column tips — non-fatal if it fails
"""
import math
import adsk.core  # type: ignore
import adsk.fusion  # type: ignore

from .parameters import SnaplockParams
from .geometry_utils import (
    sketch_xz_closed_profile,
    revolve_profile,
    pattern_bodies_around_z,
    combine_bodies,
    verify_wall_consistency,
    verify_point_in_body,
)


def build_receiver(
    params: SnaplockParams,
    occurrence: "adsk.fusion.Occurrence",
) -> dict:
    """
    Build the receiver into the given occurrence's component.
    Returns a dict with body reference, volume, warnings, and diagnostics.
    Raises RuntimeError if critical verification fails.
    """
    warnings = []
    component = occurrence.component

    # === Step 1: Base body (cross-section revolve) ===
    base_body = _build_base_body(params, component)
    initial_volume = base_body.volume

    # === Steps 2-5: Slot + entry cuts via body pattern ===
    _cut_slots_and_entries(params, component, base_body)

    # === Step 6: VERIFY wall consistency ===
    slot_angles = _slot_midpoint_angles(params)
    # Probe at Z = -(rim_height/2), which is inside the wall but above any slot cut depth
    # For defaults: rim_height=0.5cm, so Z=-0.25cm (-2.5mm)
    probe_z_cm = -(params.rim_height / 2)
    # Scan range must cover the wall region for THIS container's size.
    # Wall inner face is at R=rim_outer_radius, outer face at R=outer_radius.
    # Use a dense sweep of that zone with small extensions on each side.
    scan_min_mm = (params.rim_outer_radius * 10) - 1.0
    scan_max_mm = (params.outer_radius * 10) + 1.0
    scan_step = 0.25  # 0.25 mm steps
    scan_range = [round(scan_min_mm + i * scan_step, 2)
                  for i in range(int((scan_max_mm - scan_min_mm) / scan_step) + 1)]
    wall_check = verify_wall_consistency(
        base_body, slot_angles, probe_z_cm, r_scan_mm=scan_range
    )
    if not wall_check["consistent"]:
        raise RuntimeError(
            f"Slot cuts produced inconsistent wall depth: {wall_check['angles']}. "
            f"Expected single R value, got {wall_check['r_values']}. "
            "This is the SnapLock_v2 bug we explicitly designed against — "
            "check that slot/entry tool bodies were created on XZ plane only."
        )

    detected_wall_inner_r_mm = wall_check["r_values"][0]

    # === Steps 7-9: Snap columns ===
    _build_snap_columns(params, component, base_body, detected_wall_inner_r_mm)

    # === Step 10: Verify columns exist ===
    column_check = _verify_columns_exist(params, base_body)
    if not column_check["all_present"]:
        warnings.append(
            f"Column verification: only {column_check['present_count']}/{params.num_tabs} "
            f"columns detected by pointContainment. Details: {column_check['details']}"
        )

    # === Step 11: Fillet column tips (non-fatal) ===
    try:
        filleted = _fillet_column_tips(params, component, base_body)
        if filleted < params.num_tabs:
            warnings.append(
                f"Only {filleted}/{params.num_tabs} column tips filleted "
                "(edge detection limitation — mechanism still works)"
            )
    except Exception as e:
        warnings.append(f"Column fillet failed (non-fatal): {e}")

    return {
        "body": base_body,
        "component": component,
        "volume_mm3": base_body.volume * 1000,
        "initial_volume_mm3": initial_volume * 1000,
        "detected_wall_inner_r_mm": detected_wall_inner_r_mm,
        "column_check": column_check,
        "warnings": warnings,
    }


# ============================================================
# Step 1: Cross-section revolve
# ============================================================

def _build_base_body(params: SnaplockParams, component: "adsk.fusion.Component") -> "adsk.fusion.BRepBody":
    """
    Build the receiver base: outer wall (R=28-30) + slot wall (R=25-28) + floor.

    Cross-section (R, Z in cm) — closed polygon for full revolve:
      - Floor bottom center to outer
      - Outer wall goes up
      - Inner top corner
      - Slot wall inner goes down
      - Back to floor via interior
    """
    R_outer = params.outer_radius
    R_slot_inner = params.rim_outer_radius  # Slot wall inner face
    Z_wall_top = 0.0
    Z_wall_bottom = -params.body_height
    Z_floor_bottom = Z_wall_bottom - params.floor_thickness

    cross_section = [
        (0.0,         Z_floor_bottom),    # center, floor bottom
        (R_outer,     Z_floor_bottom),    # outer edge, floor bottom
        (R_outer,     Z_wall_top),        # outer edge, wall top
        (R_slot_inner, Z_wall_top),       # slot wall inner, wall top
        (R_slot_inner, Z_wall_bottom),    # slot wall inner, wall bottom
        (0.0,         Z_wall_bottom),     # center, floor top
    ]

    sketch = component.sketches.add(component.xZConstructionPlane)
    sketch_xz_closed_profile(sketch, cross_section)

    prof = sketch.profiles.item(0)
    rev = revolve_profile(
        component, prof, "360 deg",
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    return rev.bodies.item(0)


# ============================================================
# Steps 2-5: Slot + entry cuts
# ============================================================

def _slot_midpoint_angles(params: SnaplockParams) -> list:
    """
    Return the angular midpoints of each slot in degrees.
    Default: [10, 100, 190, 280] for num_tabs=4 with tab_revolve_angle=20°.
    """
    half_tab = params.tab_revolve_angle / 2
    sector = 360.0 / params.num_tabs
    return [half_tab + i * sector for i in range(params.num_tabs)]


def _cut_slots_and_entries(
    params: SnaplockParams,
    component: "adsk.fusion.Component",
    base_body: "adsk.fusion.BRepBody",
):
    """
    Build slot + entry tool bodies at 0°, body-pattern × num_tabs, combine-cut all.

    Slot profile: tab shape (R=23-26 at tab depth Z=-5 to Z=-9 for default params)
    Entry profile: tab shape + rectangle extending to wall top
    """
    # Tab profile Z extent: below wall top by rim_height, extending down by tab depth
    Z_tab_top = -params.rim_height                              # rim bottom
    Z_tab_drop = Z_tab_top - params.tab_drop_height             # after 1mm flat
    Z_tab_bottom = Z_tab_top - params.tab_drop_height - params.tab_chamfer_drop  # after chamfer

    R_inner = params.rim_inner_radius   # 23 mm = 2.3 cm for defaults
    R_outer = params.tab_tip_radius     # 26 mm = 2.6 cm for defaults

    # --- Slot profile (just the tab shape) ---
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

    # --- Entry profile (tab shape + rectangle to wall top) ---
    entry_points = [
        (R_inner, Z_tab_bottom),
        (R_outer, Z_tab_drop),
        (R_outer, 0.0),   # wall top
        (R_inner, 0.0),
    ]
    entry_sketch = component.sketches.add(component.xZConstructionPlane)
    sketch_xz_closed_profile(entry_sketch, entry_points)
    entry_profile = entry_sketch.profiles.item(0)
    # Entry goes in OPPOSITE direction from slot (negative)
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

    # After pattern, component has base_body + 2*num_tabs tool bodies
    # Collect all tool bodies (everything except base_body)
    tool_bodies = []
    for i in range(component.bRepBodies.count):
        b = component.bRepBodies.item(i)
        if b != base_body:
            tool_bodies.append(b)

    # --- Combine-Cut all tool bodies from base body ---
    combine_bodies(
        component,
        target=base_body,
        tools=tool_bodies,
        operation=adsk.fusion.FeatureOperations.CutFeatureOperation,
        keep_tools=False,
    )


# ============================================================
# Steps 7-9: Snap columns
# ============================================================

def _build_snap_columns(
    params: SnaplockParams,
    component: "adsk.fusion.Component",
    base_body: "adsk.fusion.BRepBody",
    detected_wall_inner_r_mm: float,
):
    """
    Build snap columns at the slot midpoints. Each column is a cylinder
    that extends from the wall top (Z=0) down through the wall into the slot.
    Only the bottom `column_protrusion` mm protrudes into the slot channel.

    Strategy (proven in SnapLock_v2):
    - Create ONE column at 0°'s slot midpoint angle as a NewBody extrude
    - The column circle is centered at R=column_radial_pos (embedded in wall)
    - Extrude from Z=0 downward through the wall + into the slot
    - Body-pattern × num_tabs
    - Combine-Join all columns into the base body
    """
    # Column center R must be inside the wall (> detected wall inner R)
    # detected_wall_inner_r_mm is in mm; column_radial_pos is in cm
    wall_inner_cm = detected_wall_inner_r_mm / 10.0
    col_r_cm = params.column_radial_pos

    # Safety: if user's column_radial_pos isn't inside the wall, adjust it
    # The column's inner edge (col_r_cm - col_radius) must be <= wall_inner_cm
    # Otherwise the column protrusion is entirely inside the wall, invisible.
    # We want: col_r_cm - column_radius < wall_inner_cm < col_r_cm + column_radius
    col_radius = params.column_radius
    inner_edge = col_r_cm - col_radius
    outer_edge = col_r_cm + col_radius
    if not (inner_edge < wall_inner_cm < outer_edge):
        # Auto-adjust: place column center slightly outside wall inner face
        adjusted_r_cm = wall_inner_cm + col_radius * 0.5  # Half the radius inside the wall
        # Use the adjusted value for this build
        col_r_cm = adjusted_r_cm

    # Sketch plane at Z=0 (wall top)
    sketch = component.sketches.add(component.xYConstructionPlane)

    # Place ONE circle at the first slot midpoint angle
    first_angle_deg = params.tab_revolve_angle / 2  # e.g., 10° for defaults
    rad = math.radians(first_angle_deg)
    cx = col_r_cm * math.cos(rad)
    cy = col_r_cm * math.sin(rad)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(cx, cy, 0),
        col_radius,
    )

    # Extrude from Z=0 (wall top) DOWN through the rim_height region
    # of solid wall material, then protrude into the slot cavity by
    # column_protrusion. The column ends at Z = -(rim_height +
    # column_protrusion), which is `column_protrusion` mm below the
    # slot ceiling at Z = -rim_height.
    #
    # IMPORTANT: extrude_distance must be `rim_height + column_protrusion`,
    # NOT `body_height + column_protrusion`. The body_height value over-
    # extrudes the column past the slot floor and embeds its bottom face
    # inside solid wall material below the slot, which destroys the
    # tip's clean circular edge — there is no terminal disc to fillet
    # because the column never actually terminates inside empty space.
    #
    # With the correct distance, the column tip is a flat disc at
    # Z = -(rim_height + column_protrusion) inside the slot cavity, with
    # a complete circular perimeter that _fillet_column_tips can find.
    # This is what produces the rounded "snap-and-release" feel that
    # the mechanism is designed for.
    extrude_distance = params.rim_height + params.column_protrusion
    prof = sketch.profiles.item(0)
    extrudes = component.features.extrudeFeatures
    ext_input = extrudes.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    ext_input.setOneSideExtent(
        adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByReal(extrude_distance)),
        adsk.fusion.ExtentDirections.NegativeExtentDirection,
    )
    col_ext = extrudes.add(ext_input)
    col_body = col_ext.bodies.item(0)

    # Pattern the column around Z × num_tabs
    pattern_bodies_around_z(
        component,
        [col_body],
        count=params.num_tabs,
        total_angle_expr="360 deg",
    )

    # Collect all column bodies (everything except base_body)
    column_bodies = []
    for i in range(component.bRepBodies.count):
        b = component.bRepBodies.item(i)
        if b != base_body:
            column_bodies.append(b)

    # Combine-Join all columns to base body
    combine_bodies(
        component,
        target=base_body,
        tools=column_bodies,
        operation=adsk.fusion.FeatureOperations.JoinFeatureOperation,
        keep_tools=False,
    )


# ============================================================
# Step 10: Column verification
# ============================================================

def _verify_columns_exist(
    params: SnaplockParams,
    base_body: "adsk.fusion.BRepBody",
) -> dict:
    """
    Probe each slot midpoint with pointContainment to verify a column is present.
    The column should extend below the slot ceiling by column_protrusion.
    """
    angles = _slot_midpoint_angles(params)

    # Probe point: just below the slot ceiling (below Z=-rim_height) by half the protrusion
    # At the column radial position
    z_probe_mm = -(params.rim_height + params.column_protrusion / 2) * 10
    r_probe_mm = params.column_radial_pos * 10

    details = {}
    present_count = 0
    for ang in angles:
        status = verify_point_in_body(base_body, r_probe_mm, ang, z_probe_mm)
        details[ang] = status
        # "IN" or "FACE" both indicate column material present
        if status in ("IN", "FACE"):
            present_count += 1

    return {
        "all_present": present_count == params.num_tabs,
        "present_count": present_count,
        "total": params.num_tabs,
        "details": details,
        "probe_point": {"r_mm": r_probe_mm, "z_mm": z_probe_mm},
    }


# ============================================================
# Step 11: Fillet column tips
# ============================================================

def _fillet_column_tips(
    params: SnaplockParams,
    component: "adsk.fusion.Component",
    base_body: "adsk.fusion.BRepBody",
) -> int:
    """
    Find circular edges at the column tip Z position and fillet them.
    Non-fatal: returns the count actually filleted.
    """
    # Expected column tip Z = -(rim_height + column_protrusion) cm
    tip_z_cm = -(params.rim_height + params.column_protrusion)
    tip_circumference_mm = math.pi * params.column_diameter * 10  # π × Ø (mm)
    tolerance_mm = 0.5

    edges_coll = adsk.core.ObjectCollection.create()
    for ei in range(base_body.edges.count):
        edge = base_body.edges.item(ei)
        length_mm = edge.length * 10
        if abs(length_mm - tip_circumference_mm) > tolerance_mm:
            continue
        try:
            evaluator = edge.evaluator
            _, pt = evaluator.getPointAtParameter(0)
            z_mm = pt.z * 10
            if abs(z_mm - tip_z_cm * 10) < 0.2:  # within 0.2mm of expected Z
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
