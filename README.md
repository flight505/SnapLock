# SnapLock

A parametric twist-snap bayonet lock mechanism for 3D-printed containers — implemented as a **Fusion 360 add-in** and usable as a library by the [f360mcp](https://github.com/flight505/f360mcp) MCP server.

## Overview

Two concentric cylindrical parts — a **Lid** and a **Receiver** — that lock together with a quarter-turn twist. The lid drops into the receiver, twists ~20° until four tabs slide into locking slots, and snap columns on the receiver engage notches on the tabs to create a tactile click. Reverse the twist to release.

![SnapLock mechanism diagram](AddInIcon.svg)

## What's in this repo

| File / Folder | Purpose |
|---|---|
| `tutorial.md` | Complete parametric specification — dimensions, cross-sections, build sequence, and hard-won build lessons |
| `lib/snaplock/` | **Core build library** — parameters, lid_builder, receiver_builder, geometry_utils. Pure Python with Fusion API calls. Reusable by any add-in or the f360mcp server. |
| `commands/snaplock_create/` | Fusion 360 command dialog (UI for humans) — grouped parameter inputs with live validation, calls `snaplock.build_snaplock()` |
| `SnapLock .py`, `.manifest` | Fusion 360 add-in entry point |
| `config.py`, `Resources/`, `AddInIcon.svg` | Add-in configuration and icons |

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

## Install (Fusion 360 add-in)

### macOS

```bash
# Symlink this repo into Fusion's AddIns folder
mkdir -p ~/Library/Application\ Support/Autodesk/Autodesk\ Fusion\ 360/API/AddIns
ln -s "/path/to/SnapLock " ~/Library/Application\ Support/Autodesk/Autodesk\ Fusion\ 360/API/AddIns/SnapLock
```

### Windows

```powershell
# PowerShell — create a junction from Fusion's AddIns folder
New-Item -ItemType Junction -Path "$env:APPDATA\Autodesk\Autodesk Fusion 360\API\AddIns\SnapLock" -Target "C:\path\to\SnapLock "
```

Then in Fusion 360:
1. Open **Utilities → Add-Ins → Scripts and Add-Ins** (Shift+S)
2. Switch to the **Add-Ins** tab
3. Select **SnapLock** and click **Run** (check "Run on Startup" to auto-load)

## Use (standalone, for humans)

1. Open a new or existing Fusion 360 design
2. Switch to the **Solid** workspace
3. In the **Create** panel, click **SnapLock**
4. Adjust the grouped parameters (Size, Walls, Locking mechanism, What to create)
5. Invalid combinations are caught live in the dialog
6. Click **OK** — the Lid and Receiver are generated as separate components (typically in under 3 seconds)

## Use (via Claude + MCP)

With the [f360mcp](https://github.com/flight505/f360mcp) MCP server, Claude can call the generator directly:

```
create_snaplock(outer_diameter=80.0, num_tabs=6)
```

The f360mcp add-in has a registered `create_snaplock` handler that delegates to the same `snaplock` library this add-in uses. One source of truth for the build logic; two front-ends (dialog UI or MCP).

## Status

- [x] Parametric spec in `tutorial.md`
- [x] Core build library `lib/snaplock/` (parameters, lid_builder, receiver_builder, geometry_utils)
- [x] Auto-derived notch/column positions that scale with container size
- [x] Tested across 40mm–100mm containers, 3–6 tabs, lid-only/receiver-only variants
- [x] Standalone add-in UI with grouped inputs and live validation
- [x] f360mcp generator handler + MCP server tool `create_snaplock`
- [ ] STL export and printed-part test
- [ ] Tolerance tuning based on print results

## License

See [LICENSE](../f360mcp/LICENSE) in the parent project.
