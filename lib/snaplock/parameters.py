"""
SnapLock parameter dataclass with validation.

All values stored internally in CENTIMETERS (Fusion's native unit).
Use from_mm() constructor for user-facing mm input.
"""
from dataclasses import dataclass
from typing import List

# Sentinel: pass this for any snap column/notch field to auto-derive from geometry.
AUTO = -1.0


@dataclass
class SnaplockParams:
    """
    Parametric dimensions for a twist-snap bayonet lock mechanism.

    Internal units: CENTIMETERS. Use SnaplockParams.from_mm(...) if supplying mm.

    The mechanism consists of:
    - Lid: outer decorative wall + inner rim (drops into receiver)
    - Receiver: outer wall + slot wall + floor
    - 4 (or more) tabs on the lid rim that twist into slots on the receiver
    - Snap columns on the receiver that engage notches on the tabs
    """

    # --- Base dimensions (cm) ---
    outer_diameter: float = 6.0          # 60 mm
    outer_wall_thickness: float = 0.2     # 2 mm
    channel_width: float = 0.3            # 3 mm (slot wall + rim clearance zone)
    rim_thickness: float = 0.2            # 2 mm
    rim_height: float = 0.5               # 5 mm (how far rim drops below body)
    body_height: float = 1.0              # 10 mm
    floor_thickness: float = 0.2          # 2 mm
    cap_thickness: float = 0.2            # 2 mm (lid cap connecting outer wall + rim)

    # --- Tab / slot geometry ---
    tab_width: float = 0.3                # 3 mm (radial extent of tab)
    tab_drop_height: float = 0.1          # 1 mm (flat portion of tab)
    tab_chamfer_drop: float = 0.3         # 3 mm (45° chamfer vertical drop)
    tab_revolve_angle: float = 20.0       # degrees
    slot_entry_angle: float = 25.0        # degrees (must be > tab_revolve_angle)
    num_tabs: int = 4

    # --- Snap column/notch ---
    # Column and notch share the same radial center for engagement.
    # Pass AUTO (sentinel = -1.0) for any field to auto-derive from the tab's
    # engagement zone (between rim_outer_radius and tab_tip_radius) so the
    # mechanism scales correctly with outer_diameter.
    # Notch spans 80% of the engagement zone; column is 40% smaller than notch.
    # Column attaches to wall material ABOVE the slot cut level — the extrude
    # starts at Z=0 (wall top) and descends through the intact wall.
    notch_radial_pos: float = AUTO     # auto: midpoint of engagement zone
    notch_diameter: float = AUTO       # auto: 80% of engagement zone width
    column_radial_pos: float = AUTO    # auto: same as notch_radial_pos
    column_diameter: float = AUTO      # auto: notch_diameter - 0.04 cm (0.4 mm clearance)
    column_protrusion: float = 0.04    # 0.4 mm (how far below slot ceiling the tip extends)

    # --- Generation options ---
    create_lid: bool = True
    create_receiver: bool = True
    lid_name: str = "Lid"
    receiver_name: str = "Receiver"

    # Build-time Z offset for the lid component during modeling (cm)
    # Prevents cross-component cuts. Set to 0 to disable (only safe if no cuts cross components).
    lid_build_z_offset: float = 10.0      # 100 mm

    def __post_init__(self):
        """Auto-derive notch/column positions from geometry when fields are set to AUTO."""
        # Engagement zone is the annulus where the tab sticks OUT past the slot wall
        # = between rim_outer_radius (slot wall inner face) and tab_tip_radius
        engagement_inner = self.rim_outer_radius
        engagement_outer = self.tab_tip_radius
        engagement_width = engagement_outer - engagement_inner  # e.g., 1.0 cm for defaults

        if self.notch_radial_pos == AUTO:
            # Midpoint of engagement zone
            self.notch_radial_pos = (engagement_inner + engagement_outer) / 2

        if self.notch_diameter == AUTO:
            # Larger of: 80% of engagement zone (fits with margin) OR 1.0 mm (printable)
            self.notch_diameter = max(engagement_width * 0.8, 0.10)

        if self.column_radial_pos == AUTO:
            # Same center as notch for perfect engagement
            self.column_radial_pos = self.notch_radial_pos

        if self.column_diameter == AUTO:
            # 75% of notch diameter = 0.2 mm clearance total, scales with notch
            self.column_diameter = self.notch_diameter * 0.75

    # --- Derived helpers ---
    @property
    def outer_radius(self) -> float:
        return self.outer_diameter / 2

    @property
    def outer_wall_inner_radius(self) -> float:
        return self.outer_radius - self.outer_wall_thickness

    @property
    def rim_outer_radius(self) -> float:
        return self.outer_wall_inner_radius - self.channel_width

    @property
    def rim_inner_radius(self) -> float:
        return self.rim_outer_radius - self.rim_thickness

    @property
    def tab_tip_radius(self) -> float:
        return self.rim_inner_radius + self.tab_width

    @property
    def column_radius(self) -> float:
        return self.column_diameter / 2

    @property
    def notch_radius(self) -> float:
        return self.notch_diameter / 2

    def validate(self) -> List[str]:
        """
        Return a list of validation errors. Empty list means valid.
        Catches the invariants that caused issues during the SnapLock_v2 rebuild.
        """
        errors = []

        # Geometric sanity
        if self.outer_diameter <= 0:
            errors.append("outer_diameter must be > 0")
        if self.rim_inner_radius <= 0:
            errors.append(
                f"rim_inner_radius must be > 0 (got {self.rim_inner_radius*10:.2f} mm); "
                "outer_diameter may be too small for the wall stack"
            )
        if self.outer_wall_thickness <= 0:
            errors.append("outer_wall_thickness must be > 0")
        if self.channel_width <= 0:
            errors.append("channel_width must be > 0")
        if self.rim_thickness <= 0:
            errors.append("rim_thickness must be > 0")
        if self.rim_height <= 0:
            errors.append("rim_height must be > 0")
        if self.body_height <= self.cap_thickness:
            errors.append(
                f"body_height ({self.body_height*10:.1f} mm) must exceed "
                f"cap_thickness ({self.cap_thickness*10:.1f} mm)"
            )

        # Mechanism invariants
        if self.num_tabs < 2:
            errors.append("num_tabs must be >= 2")
        if self.num_tabs > 12:
            errors.append("num_tabs > 12 is impractical (arcs would overlap)")
        if self.slot_entry_angle <= self.tab_revolve_angle:
            errors.append(
                f"slot_entry_angle ({self.slot_entry_angle}°) must be > "
                f"tab_revolve_angle ({self.tab_revolve_angle}°) for insertion clearance"
            )
        total_arc_per_tab = self.tab_revolve_angle + self.slot_entry_angle
        arc_per_sector = 360 / self.num_tabs
        if total_arc_per_tab >= arc_per_sector:
            errors.append(
                f"total arc per tab ({total_arc_per_tab}°) must be < "
                f"360°/num_tabs ({arc_per_sector:.1f}°) for separation between pairs"
            )

        # Tab geometry
        if self.tab_width <= 0:
            errors.append("tab_width must be > 0")
        if self.tab_drop_height < 0.05:  # 0.5 mm
            errors.append(
                f"tab_drop_height ({self.tab_drop_height*10:.1f} mm) must be >= 0.5 mm "
                "for FDM printability"
            )

        # Snap column/notch alignment (the critical one from v1 → v2)
        if self.notch_diameter <= self.column_diameter:
            errors.append(
                f"notch_diameter ({self.notch_diameter*10:.2f} mm) must be > "
                f"column_diameter ({self.column_diameter*10:.2f} mm) for print clearance"
            )
        if self.column_protrusion <= 0:
            errors.append("column_protrusion must be > 0")
        if self.column_protrusion >= self.tab_drop_height:
            errors.append(
                f"column_protrusion ({self.column_protrusion*10:.2f} mm) must be < "
                f"tab_drop_height ({self.tab_drop_height*10:.2f} mm) "
                "for snap-and-release (otherwise permanent lock)"
            )

        # Tab tip must reach into slot wall for engagement
        slot_wall_inner = self.rim_outer_radius  # Where the receiver slot wall starts
        if self.tab_tip_radius <= slot_wall_inner:
            errors.append(
                f"tab_tip_radius ({self.tab_tip_radius*10:.2f} mm) must exceed "
                f"slot wall inner face ({slot_wall_inner*10:.2f} mm) for engagement"
            )

        # Notch position must be on the tab flat face
        if not (self.rim_inner_radius <= self.notch_radial_pos - self.notch_radius
                and self.notch_radial_pos + self.notch_radius <= self.tab_tip_radius):
            errors.append(
                f"notch at R={self.notch_radial_pos*10:.2f}±{self.notch_radius*10:.2f} mm "
                f"must fit within tab flat R=[{self.rim_inner_radius*10:.1f}, "
                f"{self.tab_tip_radius*10:.1f}] mm"
            )

        # Column must align with notch (same radial center ±0.5mm)
        alignment_error = abs(self.column_radial_pos - self.notch_radial_pos)
        if alignment_error > 0.1:  # 1.0 mm tolerance
            errors.append(
                f"column_radial_pos ({self.column_radial_pos*10:.2f} mm) must be "
                f"within 1.0 mm of notch_radial_pos ({self.notch_radial_pos*10:.2f} mm) "
                "for snap engagement"
            )

        return errors

    def validate_or_raise(self):
        errors = self.validate()
        if errors:
            raise ValueError("SnaplockParams validation failed:\n  - " + "\n  - ".join(errors))

    @classmethod
    def from_mm(cls, **kwargs_mm) -> "SnaplockParams":
        """
        Construct from millimeter values. Dimensional keys are converted mm→cm.
        Pass-through keys (num_tabs, booleans, names, angles in degrees): unchanged.
        """
        # Keys that are dimensional (need mm→cm conversion)
        dimensional = {
            "outer_diameter", "outer_wall_thickness", "channel_width", "rim_thickness",
            "rim_height", "body_height", "floor_thickness", "cap_thickness",
            "tab_width", "tab_drop_height", "tab_chamfer_drop",
            "notch_radial_pos", "notch_diameter",
            "column_radial_pos", "column_diameter", "column_protrusion",
            "lid_build_z_offset",
        }
        converted = {}
        for k, v in kwargs_mm.items():
            if k in dimensional and isinstance(v, (int, float)):
                converted[k] = v / 10.0  # mm → cm
            else:
                converted[k] = v
        return cls(**converted)

    def to_mm_dict(self) -> dict:
        """Export as a dict with dimensional values in mm (for logging/MCP responses)."""
        dimensional = {
            "outer_diameter", "outer_wall_thickness", "channel_width", "rim_thickness",
            "rim_height", "body_height", "floor_thickness", "cap_thickness",
            "tab_width", "tab_drop_height", "tab_chamfer_drop",
            "notch_radial_pos", "notch_diameter",
            "column_radial_pos", "column_diameter", "column_protrusion",
            "lid_build_z_offset",
        }
        result = {}
        for f in self.__dataclass_fields__:
            v = getattr(self, f)
            if f in dimensional and isinstance(v, (int, float)):
                result[f] = v * 10.0  # cm → mm
            else:
                result[f] = v
        return result


# ============================================================
# Interface-only mode — add SnapLock features to a user's
# existing container body instead of generating a full receiver.
# ============================================================

@dataclass
class SnaplockInterfaceParams:
    """
    Parametric dimensions for adding SnapLock locking features to an EXISTING
    container body. Used by the "SnapLock Interface" command and the
    interface_builder module.

    Mental model: the user has built their own vessel (any shape, any
    decorative exterior) and selected its inner cavity's cylindrical wall.
    The interface builder reads the cavity radius + top Z from the selection
    and adds slot cuts + snap columns to that existing wall. A matching Lid
    is generated as a separate component.

    Internal units: CENTIMETERS.

    Primary dimension: `cavity_inner_radius` (read from the selected face).
    All lid / tab / column geometry is derived from this, with user-controlled
    clearances and wall-feature thicknesses.
    """

    # --- Target geometry (set from the selected face at execute time) ---
    cavity_inner_radius: float       # cm, from selected cylindrical face radius
    slot_ceiling_z: float            # cm, world Z of the slot ceiling (face top)

    # --- Wall feature extents (user-settable in dialog) ---
    body_height: float = 1.0         # cm — how far down the slot wall extends (10 mm)
    rim_height: float = 0.5          # cm — lid rim drop below body top (5 mm)
    rim_thickness: float = 0.2       # cm — slot wall thickness (2 mm)
    lid_clearance: float = 0.015     # cm — slip-fit gap between cavity and lid rim (0.15 mm)
    ceiling_cap_thickness: float = 0.2  # cm — lid cap thickness (2 mm)

    # --- Assumed receiver wall thickness (the user's container's wall) ---
    # Used for computing the equivalent SnaplockParams for lid generation.
    # Not applied to the user's actual container — their wall is whatever
    # they built. This just controls the generated Lid's outer wall.
    receiver_wall_thickness: float = 0.2  # cm (2 mm default)

    # --- Lock mechanism (identical meaning to SnaplockParams) ---
    tab_width: float = 0.3           # 3 mm radial tab extent
    tab_drop_height: float = 0.1     # 1 mm tab flat
    tab_chamfer_drop: float = 0.3    # 3 mm 45° chamfer drop
    tab_revolve_angle: float = 20.0  # degrees
    slot_entry_angle: float = 25.0   # degrees
    num_tabs: int = 4
    column_protrusion: float = 0.04  # 0.4 mm snap column protrusion

    # --- Output options ---
    create_matching_lid: bool = True
    lid_name: str = "SnapLock Lid"

    def validate(self) -> List[str]:
        """Return a list of validation errors. Empty list means valid."""
        errors = []

        if self.cavity_inner_radius <= 0:
            errors.append("cavity_inner_radius must be > 0 (read from face selection)")

        if self.body_height <= 0:
            errors.append("body_height must be > 0")
        if self.rim_height <= 0:
            errors.append("rim_height must be > 0")
        if self.rim_thickness <= 0:
            errors.append("rim_thickness must be > 0")
        if self.lid_clearance < 0:
            errors.append("lid_clearance must be >= 0")
        if self.ceiling_cap_thickness < 0:
            errors.append("ceiling_cap_thickness must be >= 0 (use 0 for no cap)")

        # Cavity must accommodate lid rim (with clearance) + tab width inside it.
        #   rim_outer_radius = cavity_inner_radius - lid_clearance
        #   rim_inner_radius = rim_outer_radius - rim_thickness
        #   Must be > 0 and leave room for tabs to extend outward to cavity wall.
        rim_outer = self.cavity_inner_radius - self.lid_clearance
        rim_inner = rim_outer - self.rim_thickness
        if rim_inner <= 0:
            errors.append(
                f"Cavity too small: rim_inner would be {rim_inner*10:.2f} mm. "
                f"Need cavity_inner_radius > lid_clearance + rim_thickness "
                f"(currently {(self.lid_clearance + self.rim_thickness)*10:.1f} mm)."
            )

        # Tab must reach past the rim outer face to engage the user's wall.
        # tab_tip_radius = rim_inner + tab_width > rim_outer = cavity_inner_radius - lid_clearance
        tab_tip = rim_inner + self.tab_width
        if tab_tip <= rim_outer:
            errors.append(
                f"Tab width {self.tab_width*10:.1f} mm too small — tab tip at "
                f"R={tab_tip*10:.2f} mm doesn't reach cavity wall at "
                f"R={rim_outer*10:.2f} mm. Increase tab_width or reduce rim_thickness."
            )

        # Tab count sanity (same as SnaplockParams)
        if self.num_tabs < 2:
            errors.append("num_tabs must be >= 2")
        if self.num_tabs > 12:
            errors.append("num_tabs > 12 is impractical (arcs would overlap)")

        # Slot/entry angle invariants (same as SnaplockParams)
        if self.slot_entry_angle <= self.tab_revolve_angle:
            errors.append(
                f"slot_entry_angle ({self.slot_entry_angle}°) must be > "
                f"tab_revolve_angle ({self.tab_revolve_angle}°) for insertion clearance"
            )
        total_arc_per_tab = self.tab_revolve_angle + self.slot_entry_angle
        arc_per_sector = 360 / self.num_tabs
        if total_arc_per_tab >= arc_per_sector:
            errors.append(
                f"total arc per tab ({total_arc_per_tab}°) must be < "
                f"360°/num_tabs ({arc_per_sector:.1f}°) for separation between pairs"
            )

        # Tab printability
        if self.tab_drop_height < 0.05:
            errors.append(
                f"tab_drop_height ({self.tab_drop_height*10:.1f} mm) must be >= 0.5 mm "
                "for FDM printability"
            )

        # Column protrusion invariants
        if self.column_protrusion <= 0:
            errors.append("column_protrusion must be > 0")
        if self.column_protrusion >= self.tab_drop_height:
            errors.append(
                f"column_protrusion ({self.column_protrusion*10:.2f} mm) must be < "
                f"tab_drop_height ({self.tab_drop_height*10:.2f} mm) "
                "for snap-and-release (otherwise permanent lock)"
            )

        return errors

    def validate_or_raise(self):
        errors = self.validate()
        if errors:
            raise ValueError("SnaplockInterfaceParams validation failed:\n  - " + "\n  - ".join(errors))

    def to_equivalent_snaplock_params(self) -> "SnaplockParams":
        """
        Build a SnaplockParams that mirrors this interface configuration,
        for reuse with the existing build_lid() logic.

        The derivation:
          rim_outer_radius  = cavity_inner_radius - lid_clearance    (lid slips into cavity)
          outer_radius      = cavity_inner_radius + receiver_wall_thickness
          outer_wall_thickness + channel_width = outer_radius - rim_outer_radius
            (we allocate channel_width = outer_radius - rim_outer_radius - outer_wall_thickness
             with outer_wall_thickness chosen = receiver_wall_thickness so the generated
             lid's outer wall matches the container's wall thickness, and channel_width
             = receiver_wall_thickness + lid_clearance.)
        """
        # Lid rim must fit inside the cavity with clearance
        target_rim_outer_radius = self.cavity_inner_radius - self.lid_clearance

        # Lid outer wall matches the user's assumed receiver wall thickness
        outer_wall_thickness = self.receiver_wall_thickness

        # Lid outer radius = rim_outer + channel + outer_wall_thickness, and
        # we want the lid to fit snugly over the container's outer wall
        # (outer wall at cavity_r + receiver_wall_thickness). So:
        #   lid_outer_radius = cavity_inner_radius + receiver_wall_thickness
        lid_outer_radius = self.cavity_inner_radius + self.receiver_wall_thickness
        lid_outer_diameter = lid_outer_radius * 2

        # Back-compute channel_width so rim_outer_radius ends up correct:
        #   rim_outer_radius = (lid_outer_radius - outer_wall_thickness) - channel_width
        # ⇒ channel_width = lid_outer_radius - outer_wall_thickness - target_rim_outer_radius
        channel_width = (
            lid_outer_radius - outer_wall_thickness - target_rim_outer_radius
        )

        return SnaplockParams(
            outer_diameter=lid_outer_diameter,
            outer_wall_thickness=outer_wall_thickness,
            channel_width=channel_width,
            rim_thickness=self.rim_thickness,
            rim_height=self.rim_height,
            body_height=self.body_height,
            floor_thickness=0.2,  # unused in interface mode
            cap_thickness=self.ceiling_cap_thickness,
            tab_width=self.tab_width,
            tab_drop_height=self.tab_drop_height,
            tab_chamfer_drop=self.tab_chamfer_drop,
            tab_revolve_angle=self.tab_revolve_angle,
            slot_entry_angle=self.slot_entry_angle,
            num_tabs=self.num_tabs,
            column_protrusion=self.column_protrusion,
            create_lid=self.create_matching_lid,
            create_receiver=False,  # interface mode never builds a new receiver
            lid_name=self.lid_name,
            receiver_name="unused",
            lid_build_z_offset=10.0,  # default 100mm during build
        )

    def to_mm_dict(self) -> dict:
        """Export as a dict with dimensional values in mm (for logging/MCP responses)."""
        dimensional = {
            "cavity_inner_radius", "slot_ceiling_z",
            "body_height", "rim_height", "rim_thickness",
            "lid_clearance", "ceiling_cap_thickness",
            "receiver_wall_thickness",
            "tab_width", "tab_drop_height", "tab_chamfer_drop",
            "column_protrusion",
        }
        result = {}
        for f in self.__dataclass_fields__:
            v = getattr(self, f)
            if f in dimensional and isinstance(v, (int, float)):
                result[f] = v * 10.0
            else:
                result[f] = v
        return result
