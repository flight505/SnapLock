"""
snaplock — Parametric twist-snap container generator for Fusion 360.

Usage:
    from snaplock import SnaplockParams, build_snaplock

    # From mm input (user/MCP-facing):
    params = SnaplockParams.from_mm(outer_diameter=60, num_tabs=4)

    # Or directly (cm, internal):
    params = SnaplockParams()

    result = build_snaplock(params, design)
    # result['lid'] = {...}
    # result['receiver'] = {...}
    # result['warnings'] = [...]
"""
from .parameters import SnaplockParams, SnaplockInterfaceParams
from .frame import CylinderFrame, frame_from_cylinder_face, world_z_aligned_frame
from .lid_builder import build_lid
from .receiver_builder import build_receiver
from .interface_builder import build_snaplock_interface
from .geometry_utils import create_component_at, move_occurrence_z

import adsk.fusion  # type: ignore

__all__ = [
    "SnaplockParams",
    "SnaplockInterfaceParams",
    "CylinderFrame",
    "frame_from_cylinder_face",
    "world_z_aligned_frame",
    "build_lid",
    "build_receiver",
    "build_snaplock",
    "build_snaplock_interface",
]


def build_snaplock(params: SnaplockParams, design: "adsk.fusion.Design") -> dict:
    """
    Top-level orchestrator. Builds Lid and/or Receiver as sub-components
    under the design root component, with proper separation during modeling
    to avoid cross-component cuts.

    Args:
        params: SnaplockParams instance (validated internally)
        design: The active Fusion Design

    Returns:
        {
            'lid': {body, component, volume_mm3, ...} or None,
            'receiver': {body, component, volume_mm3, ...} or None,
            'warnings': [...],
            'params': <dict of mm values used>,
        }
    """
    # Validate up front — fail fast on bad input
    params.validate_or_raise()

    warnings = []
    root_comp = design.rootComponent

    lid_result = None
    receiver_result = None
    lid_occ = None

    # Build the Receiver FIRST at origin.
    # Rationale: the receiver has the wall-consistency verification,
    # and building it first means any failure surfaces before the lid work.
    if params.create_receiver:
        receiver_occ = create_component_at(
            root_comp,
            params.receiver_name,
            z_offset_cm=0.0,
        )
        receiver_result = build_receiver(params, receiver_occ)
        warnings.extend(receiver_result.get("warnings", []))

    # Build the Lid at +lid_build_z_offset (default +100mm) to prevent
    # cross-component cuts. Move to assembly position after build.
    if params.create_lid:
        lid_occ = create_component_at(
            root_comp,
            params.lid_name,
            z_offset_cm=params.lid_build_z_offset,
        )
        lid_result = build_lid(params, lid_occ)
        warnings.extend(lid_result.get("warnings", []))

        # Move Lid to assembly position (Z=0)
        if params.lid_build_z_offset != 0:
            move_occurrence_z(lid_occ, 0.0)

    return {
        "lid": lid_result,
        "receiver": receiver_result,
        "warnings": warnings,
        "params_mm": params.to_mm_dict(),
    }
