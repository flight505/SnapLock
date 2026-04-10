# Twist-Snap Mechanism — Fusion 360 Add-in Specification

Based on the video analysis (transcript + visual extraction), here is the complete step-by-step specification for a Twist-Snap lock mechanism. All dimensions, operations, and relationships are documented so an add-in can reproduce this design programmatically.

---

## Overview

The mechanism consists of two concentric cylindrical parts — a **Top (Lid)** and a **Bottom (Receiver)**. The lid sits on top of the receiver with their outer walls aligned. The lid's inner rim drops down into the receiver's interior. Tabs on the rim engage with locking slots in the receiver's inner wall. Twisting the lid a fixed angular distance causes each tab to slide into a slot, where a small snap column on the receiver pops into a semicircular notch in the tab, locking the parts together.

---

## Parameters (User-Configurable)

| Parameter | Default | Description |
|---|---|---|
| `outerDiameter` | 60 mm | Outer diameter of both parts |
| `outerWallThickness` | 2 mm | Radial thickness of the outer decorative wall |
| `channelWidth` | 3 mm | Radial gap between outer wall and rim (receiver's slot wall occupies this space) |
| `rimThickness` | 2 mm | Radial thickness of the inner rim wall |
| `rimHeight` | 5 mm | How far the rim extends downward below the lid body |
| `bodyHeight` | 10 mm | Height of the main cylindrical wall (both lid and receiver) |
| `floorThickness` | 2 mm | Thickness of the receiver's floor |
| `tabWidth` | 3 mm | Radial extent of each locking tab (measured outward from rim inner face) |
| `tabDropHeight` | 1 mm | Vertical flat on the tab before the chamfer begins |
| `tabChamferAngle` | 45° | Angle of the tab's chamfer (self-supporting for 3D printing) |
| `tabRevolveAngle` | 20° | Arc-span of each tab / slot |
| `notchDiameter` | 1.2 mm | Diameter of the snap-notch on the tab (slightly larger than column for clearance) |
| `columnDiameter` | 0.8 mm | Diameter of the snap column on the receiver |
| `columnHeight` | 0.4 mm | How far the column protrudes below the slot ceiling (snap-and-release, NOT full engagement) |
| `notchRadialPos` | 25.5 mm | Radial position of notch center on tab (near outer edge, aligned with column) |
| `columnRadialPos` | 25.9 mm | Radial position of column center (embedded 0.4mm into wall, protrudes 0.4mm into slot) |
| `filletRadius` | 1 mm | Fillet on all tab, slot, and column edges |
| `slotEntryAngle` | 25° | Arc-span of the entry opening (must be > `tabRevolveAngle`) |
| `toleranceOffset` | 0.15 mm | Clearance applied to receiver walls (NOT to snap column) |
| `numTabs` | 4 | Number of tab/slot pairs (circular pattern count) |
| `decorativeDiameter` | 5 mm | Diameter of decorative bumps on outer wall |
| `decorativeCount` | 16 | Number of decorative bumps |

---

## Derived Dimensions

Computed from parameters — do not set independently:

| Value | Formula | Default |
|---|---|---|
| `outerRadius` | `outerDiameter / 2` | 30 mm |
| `outerWallInnerRadius` | `outerRadius - outerWallThickness` | 28 mm |
| `rimOuterRadius` | `outerWallInnerRadius - channelWidth` | 25 mm |
| `rimInnerRadius` | `rimOuterRadius - rimThickness` | 23 mm |
| `tabTipRadius` | `rimInnerRadius + tabWidth` | 26 mm |
| `tabChamferDrop` | `tabWidth / tan(tabChamferAngle)` | 3 mm (at 45°) |
| `tabTotalDepth` | `tabDropHeight + tabChamferDrop` | 4 mm |

The tab profile extends from `rimInnerRadius` (23 mm) outward to `tabTipRadius` (26 mm). Since the rim outer face is at 25 mm and the receiver slot wall inner face is at ~25 mm, the tab protrudes **1 mm** into the slot wall — this is the engagement depth.

---

## Concentric Circle Reference

Both parts use four concentric circles on the XY plane. Different regions are extruded for each part:

```
        R30 ┈┈┈ Circle 1 (outermost)
  ┌─────────────────────┐
  │   OUTER WALL        │  2 mm thick
  │   (both parts)      │
  ├─────────────────────┤
        R28 ┈┈┈ Circle 2
  │   CHANNEL / SLOT    │  3 mm wide
  │   Lid: empty gap    │
  │   Receiver: wall    │
  ├─────────────────────┤
        R25 ┈┈┈ Circle 3
  │   RIM / INTERIOR    │  2 mm thick
  │   Lid: rim wall     │
  │   Receiver: open    │
  ├─────────────────────┤
        R23 ┈┈┈ Circle 4 (innermost)
  │   OPEN CENTER       │
  └─────────────────────┘
```

**Lid** extrudes: Circle 1–2 (outer wall, upward) and Circle 3–4 (rim, downward).
**Receiver** extrudes: Circle 1–2 (outer wall, upward) and Circle 2–3 (slot wall, upward), plus floor.

---

## Component Structure

Create two components under the root before modeling:

1. **"Lid"** — the top piece with rim and tabs
2. **"Receiver"** — the bottom piece with slots, entry openings, and snap columns

Both share the root origin. The center Z-axis is the shared rotational axis.

---

## PART A: LID

### Step A1 — Create Component

1. Create a new component named **"Lid"** under the root.
2. Activate the Lid component.

### Step A2 — Base Sketch (XY Origin Plane)

Create a sketch on the XY origin plane. Draw four concentric circles from center:

| Circle | Diameter | Radius | Purpose |
|---|---|---|---|
| 1 | 60 mm | 30 mm | Outer wall, outer edge |
| 2 | 56 mm | 28 mm | Outer wall, inner edge |
| 3 | 50 mm | 25 mm | Rim, outer edge |
| 4 | 46 mm | 23 mm | Rim, inner edge |

Optionally place a Ø5 mm circle on Circle 1 at top dead center (0°) for decorative bumps.

Finish the sketch.

### Step A3 — Extrude Outer Wall

- **Profile**: Ring between Circle 1 and Circle 2 (R28–R30).
- **Direction**: Positive Z (upward).
- **Distance**: 10 mm (`bodyHeight`).
- **Operation**: New Body, joined to Lid component.

### Step A4 — Extrude Rim

- **Profile**: Ring between Circle 3 and Circle 4 (R23–R25).
- **Direction**: Negative Z (downward).
- **Distance**: 5 mm (`rimHeight`).
- **Operation**: Join.

The rim extends below the XY plane. It drops into the receiver when assembled.

### Step A5 — Lid Cap (optional)

If the lid has a solid top:
- **Profile**: Disc from Circle 4 to Circle 1 (R0–R30, excluding the channel ring R25–R28 if you want the channel open from above; or the full disc for a sealed lid).
- **Direction**: Positive Z.
- **Distance**: One layer height at Z = `bodyHeight` (flush with outer wall top).
- **Operation**: Join.

Skip this for an open-top lid (as shown in the video).

### Step A6 — Decorative Bumps

1. Extrude the Ø5 mm circle on Circle 1 as a **Join**, distance = `bodyHeight` (10 mm), upward.
2. **Circular Pattern** the extrusion: axis = Z, quantity = `decorativeCount` (16), full 360°.

### Step A7 — Tab Profile Sketch (XZ Origin Plane)

This defines the cross-section of the locking tab that hangs below the rim.

1. Create a sketch on the **XZ origin plane**.
2. **Project** the bottom edge of the rim's inner face into this sketch. This is the circular edge at (R = 23 mm, Z = −5 mm). In the XZ plane it appears as a point at (X = 23, Z = −5).
3. Draw the tab profile with the **Line tool**, starting from the projected point:

```
                  tabWidth (3 mm)
    Start ──────────────────── P1
    (23, -5)                  (26, -5)
    │                          │
    │                          │ tabDropHeight (1 mm)
    │                          │
    │                         P2 (26, -6)
    │                        ╱
    │                      ╱  45° chamfer
    │                    ╱
    │                  ╱
    │                ╱
    P3 ─────────────
    (23, -9)
```

   - **Line 1**: From (23, −5) → (26, −5). Horizontal, 3 mm **outward** (away from center, +X). This is the flat top of the tab.
   - **Line 2**: From (26, −5) → (26, −6). Vertical downward, 1 mm. The flat landing for clean 3D printing.
   - **Line 3**: From (26, −6) → (23, −9). Diagonal at 45° back toward the rim wall. Length = 3√2 mm.
   - **Line 4**: From (23, −9) → (23, −5). Vertical upward, 4 mm. Closes the profile along the rim inner face.

4. Add constraints: Line 1 horizontal, Line 2 vertical, Line 4 vertical, Line 3 at 45°.
5. Add dimensions: Line 1 = 3 mm, Line 2 = 1 mm, chamfer angle = 45°.
6. Finish the sketch.

**Why outward?** The tab projects radially outward from the rim inner face (R23) toward and past the rim outer face (R25), reaching R26. The 1 mm that extends past the rim (R25–R26) is what engages with the receiver's slot wall.

### Step A8 — Revolve the Tab

- **Feature**: Create > Revolve.
- **Profile**: The closed tab profile from Step A7.
- **Axis**: Z-axis.
- **Type**: One Side.
- **Angle**: 20° (`tabRevolveAngle`).
- **Operation**: Join.

Result: A single arc-shaped tab spanning 20° on the rim.

### Step A9 — Cut Snap Notch

1. Create a sketch on the **flat bottom face** of the tab (the 1 mm flat at Z = −6 mm).
2. Draw a **Ø1 mm circle** (`notchDiameter`) at the **angular midpoint** of the tab (10° into the 20° arc), centered radially on the flat face.
3. Finish the sketch.
4. **Extrude** as a **Cut**, direction = upward (into the tab), extent = Through All.

The notch is the detent that the receiver's snap column locks into.

### Step A10 — Fillet Tab Edges

- **Feature**: Modify > Fillet.
- **Edges**: Leading edge, trailing edge of the tab, and edges around the notch.
- **Radius**: 1 mm (`filletRadius`).

Fillets are essential for smooth insertion and release.

### Step A11 — Circular Pattern

- **Feature**: Create > Pattern > Circular Pattern.
- **Objects**: The Revolve (A8), Extrude-Cut (A9), and Fillet (A10) features.
- **Axis**: Z-axis.
- **Quantity**: 4 (`numTabs`), full 360°.

Result: 4 evenly-spaced tabs at 0°, 90°, 180°, 270°.

---

## PART B: RECEIVER

### Step B1 — Create Component

1. Create a new component named **"Receiver"** under the root.
2. Activate the Receiver component.

### Step B2 — Base Sketch (XY Origin Plane)

Create a sketch on the XY origin plane with the same four concentric circles:

| Circle | Diameter | Radius | Purpose (Receiver) |
|---|---|---|---|
| 1 | 60 mm | 30 mm | Outer wall, outer edge |
| 2 | 56 mm | 28 mm | Outer wall, inner edge / Slot wall, outer edge |
| 3 | 50 mm | 25 mm | Slot wall, inner edge |
| 4 | 46 mm | 23 mm | (Reference only — no geometry extruded here) |

Optionally add the Ø5 mm decorative circle on Circle 1.

Finish the sketch.

### Step B3 — Extrude Outer Wall

- **Profile**: Ring between Circle 1 and Circle 2 (R28–R30).
- **Direction**: Positive Z (upward).
- **Distance**: 10 mm (`bodyHeight`).
- **Operation**: New Body, joined to Receiver component.

### Step B4 — Extrude Slot Wall

This is the critical wall where slots and snap columns will be created.

- **Profile**: Ring between Circle 2 and Circle 3 (R25–R28).
- **Direction**: Positive Z (upward).
- **Distance**: 10 mm (`bodyHeight`).
- **Operation**: Join.

The slot wall fills the radial space that corresponds to the lid's channel. When assembled, the slot wall sits directly beneath (and engages with) the lid's channel.

### Step B5 — Extrude Floor

- **Profile**: Disc from center to Circle 2 (R0–R28). This covers the interior and the slot wall base.
- **Direction**: Negative Z (downward).
- **Distance**: 2 mm (`floorThickness`).
- **Operation**: Join.

The floor seals the bottom. Interior space (R0–R25) above the floor is where the lid's rim drops into.

### Step B6 — Decorative Bumps

Same as lid Step A6: extrude the Ø5 mm circle on the outer wall + circular pattern × 16.

### Step B7 — Slot Profile Sketch (XZ Origin Plane)

Recreate the tab profile parametrically (do NOT project from the lid component — parametric reconstruction is more robust in the API).

1. Create a sketch on the **XZ origin plane**.
2. Draw the **same tab profile** as Step A7:
   - (23, −5) → (26, −5) → (26, −6) → (23, −9) → close.
   - **Important**: Position this profile at the correct Z height relative to the receiver. When assembled, the lid's rim bottom is at Z = 5 mm in receiver coordinates (it drops from Z = 10 to Z = 5). The tab profile relative to the receiver should be:
     - Top of tab at Z = 5 mm (matching rim bottom in receiver space)
     - Adjust all Z values: shift by +10 mm from the lid-relative values.
     - So: (23, 5) → (26, 5) → (26, 4) → (23, 1) → close.

3. Additionally, draw a **rectangle** extending from the top of the tab profile up to the top of the slot wall:
   - Left edge at X = 23, from Z = 5 up to Z = 10 (top of wall).
   - Right edge at X = 26, from Z = 5 up to Z = 10.
   - This rectangle + tab profile together form the **entry opening profile**.

4. Fully constrain and dimension.
5. Finish the sketch.

### Step B8 — Cut Tab Slot (20° Revolve Cut)

- **Feature**: Create > Revolve.
- **Profile**: Select ONLY the tab-shaped portion (the trapezoidal profile, NOT the entry rectangle).
- **Axis**: Z-axis.
- **Type**: One Side, revolving in the **twist direction** (e.g., clockwise when viewed from +Z).
- **Angle**: 20° (`tabRevolveAngle`).
- **Operation**: Cut.

This cuts the horizontal channel where the tab sits when locked. Only the portion intersecting the slot wall (R25–R26) actually removes material — the rest of the profile is in empty space.

### Step B9 — Cut Entry Opening (25° Revolve Cut)

- **Feature**: Create > Revolve.
- **Profile**: Select the **full combined profile** (tab shape + entry rectangle).
- **Axis**: Z-axis.
- **Type**: One Side, revolving in the **opposite direction** from B8.
- **Angle**: 25° (`slotEntryAngle`).
- **Operation**: Cut.

This cuts the full-height opening where the tab drops into the receiver.

### Angular Layout (Critical)

The slot and entry revolve in **opposite directions** from the sketch plane, creating adjacent cuts:

```
  Viewed from above (+Z), one tab/slot pair:

         ◄── twist direction (e.g., clockwise)

  ┌──────────────────────┬───────────────────┐
  │      ENTRY (25°)     │     SLOT (20°)    │
  │   full-height cut    │  tab-depth cut    │  ← slot wall
  │   (tab drops here)   │  (tab locks here) │
  └──────────────────────┴───────────────────┘
       ◄── entry ──►  0°  ◄── slot ──►

  Total angular span per pair: 45°
  With 4 pairs at 90° spacing: 45° solid wall between each pair
```

**How it works:**
1. Align tab over the 25° entry opening
2. Drop lid — tab falls through the full-height entry
3. Twist lid 20° (toward the slot)
4. Tab slides into the 20° slot — wall above the slot prevents lifting
5. Snap column clicks into tab notch → locked

**Why opposite directions?** If both revolves went the same direction, they'd overlap and create one continuous full-height cut with no shelf to retain the tab. Opposite directions place the slot and entry side-by-side with the sketch plane as the shared edge.

### Step B10 — Create Snap Column

1. Create a sketch on the **top face of the slot wall** (Z = 10 mm), looking down.
2. Locate the **angular midpoint** of the 20° slot (10° into the slot, measured in the twist direction from the sketch plane).
3. Draw a **Ø1 mm circle** (`notchDiameter`) at the midpoint, positioned at the radial center of the slot wall inner face.
4. Finish the sketch.
5. **Extrude** the circle:
   - **Direction**: Negative Z (downward, into the slot).
   - **Distance**: To Object — select the floor of the slot (the bottom surface of the tab-depth cut). Alternatively, use a fixed distance equal to `tabDropHeight` (1 mm) so the column fills the flat portion of the tab.
   - **Operation**: Join.

The column, when the tab twists into position, pops into the tab's notch to create the audible/tactile snap.

### Step B11 — Tolerance Offset (Press/Pull)

- **Feature**: Modify > Press Pull (Q) or Offset Face.
- **Select faces**:
  - The **inner face** of the slot wall (at R25) — this creates clearance for the lid's rim
  - The **outer face** of the slot wall (at R28) — this creates clearance within the lid's channel
  - Do **NOT** select the snap column faces — the column must remain tight for friction
- **Distance**: −0.15 mm (`toleranceOffset`). The faces move inward (wall gets thinner), creating a gap.

After offset:
- Slot wall inner face: R25 → R25.15 (0.15 mm gap to rim outer at R25)
- Slot wall outer face: R28 → R27.85 (0.15 mm gap to lid's outer wall inner at R28)

**Tuning**: Start with −0.15 mm. If parts are too tight after printing, increase to −0.2 mm. If too loose, decrease to −0.1 mm.

### Step B12 — Fillet Slot and Column Edges

- **Feature**: Modify > Fillet.
- **Edges**: Slot entrance edges, slot channel edges, snap column top and bottom edges.
- **Radius**: 1 mm (`filletRadius`), matching the lid's tab fillets.

Fillets on the column are essential — without them, the tab cannot slide over the column to snap in and release.

### Step B13 — Circular Pattern

- **Feature**: Create > Pattern > Circular Pattern.
- **Objects**: All slot features — B8 (slot cut), B9 (entry cut), B10 (snap column), B11 (offset faces), B12 (fillets).
- **Axis**: Z-axis.
- **Quantity**: 4 (`numTabs`), full 360°.

Result: 4 evenly-spaced slot/entry/column sets at 0°, 90°, 180°, 270°.

---

## Assembly Behavior

1. **Align**: Hold lid above receiver with tabs aligned to entry openings (the 25° full-height cuts).
2. **Insert**: Drop the lid straight down. The rim (R23–R25) enters the receiver interior (inside R25). The tabs (extending to R26) pass through the entry openings in the slot wall.
3. **Twist**: Rotate the lid ~20° in the twist direction. The tabs slide along the slot channels, guided by chamfers and fillets.
4. **Snap**: At 20° of rotation, each tab's notch aligns with its snap column. The column pops into the notch — audible/tactile click. The wall above the slot prevents the lid from lifting.
5. **Release**: Twist in reverse. The fillets allow the column to pop out of the notch. Continue to the entry opening, then lift the lid out.

---

## Timeline Summary

Expected feature tree order for each component:

### Lid Timeline
| # | Feature | Step |
|---|---|---|
| 1 | Create Component "Lid" | A1 |
| 2 | Sketch: base circles (XY plane) | A2 |
| 3 | Extrude: outer wall (upward 10 mm) | A3 |
| 4 | Extrude: rim (downward 5 mm) | A4 |
| 5 | Extrude: cap (optional) | A5 |
| 6 | Extrude: decorative bump | A6 |
| 7 | Circular Pattern: decorative bumps | A6 |
| 8 | Sketch: tab profile (XZ plane) | A7 |
| 9 | Revolve: tab (20°, Join) | A8 |
| 10 | Sketch: notch circle (tab bottom face) | A9 |
| 11 | Extrude: notch (Cut, Through All) | A9 |
| 12 | Fillet: tab edges | A10 |
| 13 | Circular Pattern: tab + notch + fillet × 4 | A11 |

### Receiver Timeline
| # | Feature | Step |
|---|---|---|
| 1 | Create Component "Receiver" | B1 |
| 2 | Sketch: base circles (XY plane) | B2 |
| 3 | Extrude: outer wall (upward 10 mm) | B3 |
| 4 | Extrude: slot wall (upward 10 mm) | B4 |
| 5 | Extrude: floor (downward 2 mm) | B5 |
| 6 | Extrude: decorative bump | B6 |
| 7 | Circular Pattern: decorative bumps | B6 |
| 8 | Sketch: slot profile + entry rectangle (XZ plane) | B7 |
| 9 | Revolve: tab slot (20° Cut, twist direction) | B8 |
| 10 | Revolve: entry opening (25° Cut, opposite direction) | B9 |
| 11 | Sketch: snap column circle (slot wall top face) | B10 |
| 12 | Extrude: snap column (Join, downward) | B10 |
| 13 | Press/Pull: tolerance offset (−0.15 mm) | B11 |
| 14 | Fillet: slot + column edges | B12 |
| 15 | Circular Pattern: all slot features × 4 | B13 |

---

## Parametric Relationships to Enforce

These invariants must hold for the mechanism to function:

| Relationship | Constraint |
|---|---|
| `slotEntryAngle` > `tabRevolveAngle` | Entry must be wider than the tab (default: 25° > 20°) |
| `notchDiameter` = column diameter | Both Ø1 mm — must match for snap engagement |
| `filletRadius` same on both parts | Both 1 mm — mismatched fillets cause binding |
| Tab profile = Slot profile | Identical geometry ensures clean fit |
| `numTabs` same for both patterns | Both 4 — mismatched counts = no assembly |
| `toleranceOffset` NOT on snap column | Column stays tight; walls get clearance |
| `tabTipRadius` > `rimOuterRadius` | Tab must protrude past rim into slot wall (26 > 25 mm) |
| Angular span per pair < 360° / numTabs | Total 45° < 90° spacing — leaves solid wall between pairs |

---

## Fusion 360 API Operations Required

| Operation | API Method |
|---|---|
| Component creation | `Occurrences.addNewComponent()` |
| Sketch on plane | `Sketches.add(plane)` |
| Concentric circles | `SketchCircles.addByCenterRadius()` |
| Lines | `SketchLines.addByTwoPoints()` |
| Constraints | `GeometricConstraints` (horizontal, vertical, coincident) |
| Dimensions | `SketchDimensions` |
| Extrude (New/Join/Cut) | `ExtrudeFeatures.addSimple()` or `.createInput()` + `.add()` |
| Revolve (angle, Join/Cut) | `RevolveFeatures.createInput()` + `.add()` |
| Fillet | `FilletFeatures.createInput()` + `.add()` |
| Circular Pattern | `CircularPatternFeatures.createInput()` + `.add()` |
| Press/Pull (Offset Face) | `OffsetFacesFeatures` or manual face offset |
| Project geometry | `Sketch.project()` |

---

## Print Orientation

- **Lid**: Print **upside-down** (tabs facing up). The 45° chamfer is self-supporting — no supports needed for the tab overhang.
- **Receiver**: Print **right-side-up** (floor on build plate). Slot wall and snap columns print cleanly in this orientation.

---

## Build Lessons (from SnapLock_v2 rebuild)

These insights come from a hard-won rebuild after an initial attempt failed. Apply these when implementing the add-in or rebuilding the model:

### 1. Build both components at DIFFERENT Z positions during modeling
Components sharing the origin cause cross-component feature interference — a revolve-cut targeting one body can cut both. Build the Lid with a **+100 mm Z offset** during modeling, then move to assembly position at the end. This prevents Fusion from applying cuts across components.

### 2. Use NewBody + Body Pattern + Combine, NOT feature patterns
Feature patterns (circular pattern of a revolve/extrude feature) fail unpredictably in multi-component designs. The reliable approach:
1. Create ONE tool body at position 0° using a revolve with `NewBody` operation
2. Use `CircularPatternFeature` on the **BRepBody** (not the feature) — this creates rotated body copies consistently
3. Use `CombineFeature` to cut/join all tool bodies against the target body at once

### 3. Use only the XZ plane for revolve sketches
Rotated construction planes have unpredictable sketch-to-world coordinate mapping. The YZ plane has a different mapping than XZ (axis swap). Stick to **XZ plane for all revolves**, and use body patterns to place copies at 90°/180°/270°.

### 4. Verify wall consistency with `pointContainment` before placing columns
Different build approaches can cut the wall to different depths at different angular positions. Before placing snap columns, scan radially at each slot midpoint using `body.pointContainment()` to find where the wall actually starts. **All 4 positions must have the wall starting at the same radius** — if not, rebuild the cuts.

### 5. Columns must overlap SOLID wall material to join
A column cylinder that merely touches a wall face won't Join — it must overlap interior volume. Place column center AT the wall (e.g., R=25.9 when wall inner face is at R=25.5), so half the cylinder is embedded. Extrude from the wall top (Z=0) down THROUGH the wall into the slot channel to guarantee overlap.

### 6. Column and notch must share the same radial position
The snap column and its mating tab notch must be at the same radius. If the column can only attach at R=25.9 (due to wall geometry), the notch must be at R=25.9 too — not at R=24.5 (tab radial midpoint). Adjust the notch position outward if needed; it just needs to be on the tab's flat bottom face.

### 7. Column must protrude minimally for snap-and-release
A column that protrudes 1 mm into a 1 mm deep notch creates a permanent lock — the tab cannot cam over it. Use a small protrusion (0.3–0.5 mm) with a fillet on the tip. This allows the tab to flex over the column during both locking and release.

### 8. Tolerance clearances
- **Notch vs column diameter**: Notch Ø1.2 mm, Column Ø0.8 mm → 0.2 mm radial clearance
- **Receiver slot wall face offset**: -0.15 mm (inward) to create sliding fit with lid rim
- **Print orientation matters more than printed tolerance** for the 45° chamfer

