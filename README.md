# SnapLock

A twist-snap bayonet lock mechanism for 3D-printed containers, with a Fusion 360 add-in template and a full parametric specification.

## Overview

Two concentric cylindrical parts — a **Lid** and a **Receiver** — that lock together with a quarter-turn twist. The lid drops into the receiver, twists ~20° until four tabs slide into locking slots, and snap columns on the receiver engage notches on the tabs to create a tactile click. Reverse the twist to release.

![SnapLock mechanism diagram](AddInIcon.svg)

## What's in this repo

| File / Folder | Purpose |
|---|---|
| `tutorial.md` | Complete parametric specification — dimensions, cross-sections, build sequence, and hard-won build lessons |
| `SnapLock .py`, `.manifest` | Fusion 360 add-in entry point (template) |
| `commands/`, `lib/` | Add-in command/palette scaffolding |
| `config.py`, `Resources/` | Add-in configuration and icons |

## The mechanism

- **Outer diameter**: 60 mm
- **Total height**: 15 mm (10 mm body + 5 mm rim)
- **4 tabs** at 90° spacing with Ø1.2 mm snap notches
- **4 slot/entry pairs** with Ø0.8 mm snap columns
- **Twist angle**: 20°
- **Entry clearance**: 5° (25° entry − 20° slot)

See [`tutorial.md`](tutorial.md) for the full parameter table, cross-section diagrams, and step-by-step build sequence.

## Build notes (what we learned the hard way)

The tutorial includes a **Build Lessons** appendix covering the non-obvious gotchas discovered while building this mechanism via the Fusion 360 API:

1. **Separate components by ≥100 mm in Z during modeling** — cross-component cuts are otherwise unavoidable when both parts share the origin.
2. **Use NewBody + Body Pattern + Combine, not feature patterns** — feature patterns fail unpredictably in multi-component designs.
3. **Stick to the XZ plane for revolve sketches** — rotated construction planes have inconsistent sketch-to-world coordinate mapping.
4. **Verify wall depth consistency with `pointContainment()`** before placing snap columns — different build approaches can leave the wall at different radii at different angular positions.
5. **Snap columns must overlap solid wall material to Join** — place the column center inside the wall, not touching its face.
6. **Column and notch share the same radius** — the notch on the tab must be positioned outward (R=25.5 mm) to reach a column that can physically attach to the wall (R=25.9 mm).
7. **Minimal column protrusion (0.3–0.5 mm) + tip fillet** — enables snap-and-release. Deeper protrusion creates a permanent lock.

## Print orientation

- **Lid**: print upside-down (tabs face up). The 45° tab chamfer is self-supporting.
- **Receiver**: print right-side-up (floor on build plate). Slot walls and columns print cleanly.

## Status

- [x] Parametric spec in `tutorial.md`
- [x] Fusion 360 model built via MCP (SnapLock_v2)
- [x] Column/notch alignment verified at all 4 positions
- [ ] STL export and print test
- [ ] Fusion 360 add-in: convert procedural build to interactive UI
- [ ] Tolerance tuning based on print results

## License

See [LICENSE](../f360mcp/LICENSE) in the parent project.
