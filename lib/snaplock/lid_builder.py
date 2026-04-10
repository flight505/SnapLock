"""
Lid (top half) builder — has the rim that drops into the receiver and
the tabs that engage the slots.

Build sequence (proven in SnapLock_v2 rebuild):
  1. Revolve cross-section on XZ plane → lid base body (outer wall + rim + cap)
  2. Create ONE tab at 0° (NewBody revolve 20°)
  3. Body-pattern the tab × num_tabs
  4. Combine-Join all tab bodies into the lid base body
  5. Create ONE notch cut body at tab midpoint (NewBody extrude through tab)
  6. Body-pattern the notch × num_tabs
  7. Combine-Cut all notch bodies from lid body

IMPORTANT: The lid is built at a Z offset (default +100mm) to keep it far
from the receiver during modeling. The caller moves the occurrence to the
assembly position (Z=0) after the build completes.
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
)


def build_lid(
    params: SnaplockParams,
    occurrence: "adsk.fusion.Occurrence",
) -> dict:
    """
    Build the lid into the given occurrence's component.
    Returns a dict with body reference, volume, and warnings.
    """
    warnings = []
    component = occurrence.component

    # Step 1: Base body (cross-section revolve)
    base_body = _build_base_body(params, component)
    initial_volume = base_body.volume

    # Steps 2-4: Tabs
    _build_tabs(params, component, base_body)
    volume_after_tabs = base_body.volume

    # Steps 5-7: Notches
    _cut_notches(params, component, base_body)
    volume_after_notches = base_body.volume

    return {
        "body": base_body,
        "component": component,
        "volume_mm3": base_body.volume * 1000,
        "initial_volume_mm3": initial_volume * 1000,
        "volume_after_tabs_mm3": volume_after_tabs * 1000,
        "volume_after_notches_mm3": volume_after_notches * 1000,
        "warnings": warnings,
    }


# ============================================================
# Step 1: Base body cross-section
# ============================================================

def _build_base_body(params: SnaplockParams, component: "adsk.fusion.Component") -> "adsk.fusion.BRepBody":
    """
    Lid cross-section (closed polygon revolved 360°):
      - Outer wall: R=outer_wall_inner_radius to outer_radius, Z=0 to body_height
      - Cap: Z=cap_bot to body_height, connecting outer wall and rim
      - Rim: R=rim_inner_radius to rim_outer_radius, Z=-rim_height to body_height
      - Channel: empty (between outer wall and rim, closed by cap at top)

    All (R, Z) in cm.
    """
    R_outer = params.outer_radius
    R_wall_in = params.outer_wall_inner_radius
    R_rim_out = params.rim_outer_radius
    R_rim_in = params.rim_inner_radius
    Z_top = params.body_height
    Z_cap_bot = Z_top - params.cap_thickness
    Z_base = 0.0
    Z_rim_bot = -params.rim_height

    # Closed polygon traced clockwise from rim inner bottom, around the outline:
    #   P0: rim inner, rim bottom
    #   P1: rim inner, top (cap top level)
    #   P2: outer, top (cap top)
    #   P3: outer, base (outer wall bottom)
    #   P4: outer wall inner, base (outer wall bottom inside)
    #   P5: outer wall inner, cap bottom
    #   P6: rim outer, cap bottom
    #   P7: rim outer, rim bottom
    cross_section = [
        (R_rim_in,  Z_rim_bot),
        (R_rim_in,  Z_top),
        (R_outer,   Z_top),
        (R_outer,   Z_base),
        (R_wall_in, Z_base),
        (R_wall_in, Z_cap_bot),
        (R_rim_out, Z_cap_bot),
        (R_rim_out, Z_rim_bot),
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
# Steps 2-4: Tabs (body pattern + combine-join)
# ============================================================

def _build_tabs(
    params: SnaplockParams,
    component: "adsk.fusion.Component",
    base_body: "adsk.fusion.BRepBody",
):
    """
    Build tabs hanging from the rim bottom, projecting outward from R=rim_inner
    to R=tab_tip, with a flat drop + 45° chamfer.
    """
    Z_tab_top = -params.rim_height
    Z_tab_drop = Z_tab_top - params.tab_drop_height
    Z_tab_bottom = Z_tab_top - params.tab_drop_height - params.tab_chamfer_drop

    R_inner = params.rim_inner_radius
    R_outer = params.tab_tip_radius

    tab_profile_points = [
        (R_inner, Z_tab_top),
        (R_outer, Z_tab_top),
        (R_outer, Z_tab_drop),
        (R_inner, Z_tab_bottom),
    ]

    sketch = component.sketches.add(component.xZConstructionPlane)
    sketch_xz_closed_profile(sketch, tab_profile_points)
    profile = sketch.profiles.item(0)

    tab_rev = revolve_profile(
        component, profile,
        f"{params.tab_revolve_angle} deg",
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    tab_body = tab_rev.bodies.item(0)

    # Pattern tab body × num_tabs
    pattern_bodies_around_z(
        component,
        [tab_body],
        count=params.num_tabs,
        total_angle_expr="360 deg",
    )

    # Collect all tab bodies (everything except base)
    tab_bodies = []
    for i in range(component.bRepBodies.count):
        b = component.bRepBodies.item(i)
        if b != base_body:
            tab_bodies.append(b)

    # Combine-Join all tabs into the base body
    combine_bodies(
        component,
        target=base_body,
        tools=tab_bodies,
        operation=adsk.fusion.FeatureOperations.JoinFeatureOperation,
        keep_tools=False,
    )


# ============================================================
# Steps 5-7: Notches
# ============================================================

def _cut_notches(
    params: SnaplockParams,
    component: "adsk.fusion.Component",
    base_body: "adsk.fusion.BRepBody",
):
    """
    Cut Ø notch_diameter holes through the tab flat face at tab midpoint angles.
    Notches are at R=notch_radial_pos (not the tab radial midpoint — they need
    to align with the snap columns on the receiver, which sit at R=column_radial_pos).
    """
    # Notch sits on tab flat face (between Z=-rim_height and Z=-rim_height-tab_drop_height)
    # Cut upward through the tab flat. Extrude from plane at Z=-rim_height-tab_drop_height
    # upward by the full tab thickness + some slack.
    Z_notch_sketch_cm = -params.rim_height - params.tab_drop_height  # tab bottom flat level
    notch_depth_cm = params.tab_drop_height + 0.1  # through tab + 1mm slack

    # Create construction plane at the sketch Z
    planes = component.constructionPlanes
    plane_input = planes.createInput()
    plane_input.setByOffset(
        component.xYConstructionPlane,
        adsk.core.ValueInput.createByReal(Z_notch_sketch_cm),
    )
    notch_plane = planes.add(plane_input)

    # Sketch notch circle at the first tab midpoint angle
    sketch = component.sketches.add(notch_plane)
    first_tab_angle_deg = params.tab_revolve_angle / 2  # e.g., 10° for defaults
    rad = math.radians(first_tab_angle_deg)
    cx = params.notch_radial_pos * math.cos(rad)
    cy = params.notch_radial_pos * math.sin(rad)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(cx, cy, 0),
        params.notch_radius,
    )

    # Extrude upward (positive direction) as NewBody
    profile = sketch.profiles.item(0)
    extrudes = component.features.extrudeFeatures
    ext_input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    ext_input.setOneSideExtent(
        adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByReal(notch_depth_cm)),
        adsk.fusion.ExtentDirections.PositiveExtentDirection,
    )
    notch_ext = extrudes.add(ext_input)
    notch_body = notch_ext.bodies.item(0)

    # Pattern × num_tabs
    pattern_bodies_around_z(
        component,
        [notch_body],
        count=params.num_tabs,
        total_angle_expr="360 deg",
    )

    # Collect all notch bodies (everything except base)
    notch_bodies = []
    for i in range(component.bRepBodies.count):
        b = component.bRepBodies.item(i)
        if b != base_body:
            notch_bodies.append(b)

    # Combine-Cut all notches from base body
    combine_bodies(
        component,
        target=base_body,
        tools=notch_bodies,
        operation=adsk.fusion.FeatureOperations.CutFeatureOperation,
        keep_tools=False,
    )
