"""
SnapLock Interface command — add locking features to an EXISTING container.

Unlike `SnapLock` (which generates a full Lid + Receiver from parameters),
this command treats the user's own container body as the receiver. The user
selects the inner cylindrical wall of their container cavity, and the
command adds slot cuts + snap columns to that wall. A matching Lid is
generated as a separate component.

This is the SnapLock equivalent of ThreadMaker's workflow: select a
cylindrical face, add features to its surface.
"""
import os
import sys
import traceback

import adsk.core
import adsk.fusion

from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface


# --- Command identity ---
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_cmdSnaplockInterface'
CMD_NAME = 'SnapLock Interface'
CMD_DESCRIPTION = (
    'Add a twist-snap locking interface (slots + snap columns) to the '
    'inner wall of an existing container. Generates a matching lid.'
)

# UI placement — same shared "3D Print Tools" panel as the other generators
WORKSPACE_ID = 'FusionSolidEnvironment'
SOLID_TAB_ID = 'SolidTab'
SHARED_PANEL_ID = 'flight505_3DPrintTools_panel'
SHARED_PANEL_NAME = '3D Print Tools'
PANEL_POSITION_AFTER = 'SolidModifyPanel'

IS_PROMOTED = True

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# --- Input IDs ---
INPUT_GROUP_TARGET = 'group_target'
INPUT_GROUP_WALLS = 'group_walls'
INPUT_GROUP_LOCK = 'group_lock'
INPUT_GROUP_WHAT = 'group_what'

INPUT_FACE_SELECT = 'target_face'
INPUT_BODY_HEIGHT = 'body_height'
INPUT_RIM_HEIGHT = 'rim_height'

INPUT_RIM_THICKNESS = 'rim_thickness'
INPUT_LID_CLEARANCE = 'lid_clearance'
INPUT_CAP_THICKNESS = 'cap_thickness'
INPUT_WALL_THICKNESS = 'wall_thickness'

INPUT_NUM_TABS = 'num_tabs'
INPUT_TAB_ANGLE = 'tab_revolve_angle'
INPUT_ENTRY_ANGLE = 'slot_entry_angle'
INPUT_TAB_WIDTH = 'tab_width'
INPUT_TAB_DROP = 'tab_drop_height'
INPUT_COL_PROTRUSION = 'column_protrusion'

INPUT_CREATE_LID = 'create_matching_lid'
INPUT_LID_NAME = 'lid_name'

INPUT_PREVIEW = 'show_preview'
INPUT_ERROR_TEXT = 'error_text'
INPUT_INFO_TEXT = 'info_text'

local_handlers = []


def _ensure_snaplock_on_path():
    """Add the snaplock library to sys.path so `import snaplock` works."""
    here = os.path.dirname(os.path.abspath(__file__))
    snaplock_root = os.path.abspath(os.path.join(here, '..', '..'))
    lib_path = os.path.join(snaplock_root, 'lib')
    if lib_path not in sys.path and os.path.isdir(lib_path):
        sys.path.insert(0, lib_path)


# =========================================================================
# Start / stop
# =========================================================================

def start():
    old = ui.commandDefinitions.itemById(CMD_ID)
    if old:
        old.deleteMe()

    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_DESCRIPTION, ICON_FOLDER
    )
    futil.add_handler(cmd_def.commandCreated, command_created)

    # Find or create the shared 3D Print Tools panel on the Solid tab
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    solid_tab = workspace.toolbarTabs.itemById(SOLID_TAB_ID)
    panel = solid_tab.toolbarPanels.itemById(SHARED_PANEL_ID)
    if not panel:
        panel = solid_tab.toolbarPanels.add(
            SHARED_PANEL_ID,
            SHARED_PANEL_NAME,
            PANEL_POSITION_AFTER,
            False,
        )

    if panel:
        control = panel.controls.addCommand(cmd_def)
        control.isPromotedByDefault = IS_PROMOTED


def stop():
    legacy_panel_ids = (
        SHARED_PANEL_ID,
        'SolidCreatePanel',
        'SolidScriptsAddinsPanel',
    )
    for pid in legacy_panel_ids:
        panel = ui.allToolbarPanels.itemById(pid)
        if not panel:
            continue
        ctrl = panel.controls.itemById(CMD_ID)
        if ctrl:
            ctrl.deleteMe()
        if pid == SHARED_PANEL_ID and panel.controls.count == 0:
            panel.deleteMe()

    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()


# =========================================================================
# Command created: build the dialog
# =========================================================================

def command_created(args: adsk.core.CommandCreatedEventArgs):
    inputs = args.command.commandInputs
    default_length = app.activeProduct.unitsManager.defaultLengthUnits

    # --- GROUP: Target ---
    g_target = inputs.addGroupCommandInput(INPUT_GROUP_TARGET, 'Target')
    g_target.isExpanded = True
    gt = g_target.children

    face_input = gt.addSelectionInput(
        INPUT_FACE_SELECT,
        'Cavity inner wall',
        'Select the inner cylindrical wall of your container',
    )
    face_input.addSelectionFilter('CylindricalFaces')
    face_input.setSelectionLimits(0, 1)
    face_input.tooltip = 'Inner cavity wall (cylindrical face)'
    face_input.tooltipDescription = (
        'Pick the cylindrical face that is the INSIDE wall of your container '
        'cavity. The cylinder axis must be vertical (parallel to world +Z). '
        'The slot cuts and snap columns will be added to this wall, sized '
        'to the face radius.'
    )

    # Info box — populated after a face is selected
    info_box = gt.addTextBoxCommandInput(
        INPUT_INFO_TEXT, '', '', 2, True
    )
    info_box.isFullWidth = True
    info_box.formattedText = '<i>Select a cylindrical face above.</i>'

    gt.addValueInput(
        INPUT_BODY_HEIGHT, 'Interface depth',
        default_length,
        adsk.core.ValueInput.createByString('10 mm'),
    ).tooltip = (
        'How far down from the selected face top the slot wall region extends. '
        'This is where slot cuts and snap columns are placed — must fit within '
        'the face height.'
    )

    gt.addValueInput(
        INPUT_RIM_HEIGHT, 'Lid rim drop',
        default_length,
        adsk.core.ValueInput.createByString('5 mm'),
    ).tooltip = (
        'How far the generated lid rim drops below its top cap to engage '
        'with the container. Smaller = shallower engagement; typically '
        '4–6 mm for a 60 mm container.'
    )

    # --- GROUP: Walls ---
    g_walls = inputs.addGroupCommandInput(INPUT_GROUP_WALLS, 'Walls')
    g_walls.isExpanded = False
    gw = g_walls.children

    gw.addValueInput(
        INPUT_RIM_THICKNESS, 'Slot wall thickness',
        default_length,
        adsk.core.ValueInput.createByString('2 mm'),
    ).tooltip = 'Radial thickness of the slot wall feature cut into the container.'

    gw.addValueInput(
        INPUT_LID_CLEARANCE, 'Lid rim clearance',
        default_length,
        adsk.core.ValueInput.createByString('0.15 mm'),
    ).tooltip = (
        'Slip-fit clearance between the cavity wall and the generated lid rim. '
        '0.1–0.2 mm works well for FDM printing with 0.4 mm nozzles.'
    )

    gw.addValueInput(
        INPUT_CAP_THICKNESS, 'Lid cap thickness',
        default_length,
        adsk.core.ValueInput.createByString('2 mm'),
    ).tooltip = 'Thickness of the generated lid top cap.'

    gw.addValueInput(
        INPUT_WALL_THICKNESS, 'Container wall (approx.)',
        default_length,
        adsk.core.ValueInput.createByString('2 mm'),
    ).tooltip = (
        'Approximate thickness of your container wall. Used to size the '
        "generated lid's outer wall to match — not applied to your container. "
        'Does not need to be exact; set to match the visible wall you see '
        'on your container.'
    )

    # --- GROUP: Locking mechanism ---
    g_lock = inputs.addGroupCommandInput(INPUT_GROUP_LOCK, 'Locking mechanism')
    g_lock.isExpanded = True
    gl = g_lock.children

    gl.addIntegerSpinnerCommandInput(
        INPUT_NUM_TABS, 'Number of tabs', 2, 12, 1, 4,
    )
    gl.addValueInput(
        INPUT_TAB_ANGLE, 'Tab arc angle', 'deg',
        adsk.core.ValueInput.createByString('20 deg'),
    )
    gl.addValueInput(
        INPUT_ENTRY_ANGLE, 'Entry arc angle', 'deg',
        adsk.core.ValueInput.createByString('25 deg'),
    )
    gl.addValueInput(
        INPUT_TAB_WIDTH, 'Tab radial width',
        default_length,
        adsk.core.ValueInput.createByString('3 mm'),
    )
    gl.addValueInput(
        INPUT_TAB_DROP, 'Tab drop height',
        default_length,
        adsk.core.ValueInput.createByString('1 mm'),
    )
    gl.addValueInput(
        INPUT_COL_PROTRUSION, 'Snap column protrusion',
        default_length,
        adsk.core.ValueInput.createByString('0.4 mm'),
    )

    # --- GROUP: What to create ---
    g_what = inputs.addGroupCommandInput(INPUT_GROUP_WHAT, 'What to create')
    g_what.isExpanded = True
    gwh = g_what.children

    gwh.addBoolValueInput(
        INPUT_CREATE_LID, 'Create matching lid', True, '', True,
    ).tooltip = 'Generate a separate Lid component sized to fit the cavity.'

    gwh.addStringValueInput(INPUT_LID_NAME, 'Lid component name', 'SnapLock Lid')

    preview_input = gwh.addBoolValueInput(INPUT_PREVIEW, 'Show preview', True, '', False)
    preview_input.tooltip = 'Show preview'
    preview_input.tooltipDescription = (
        'Rebuild the interface features on every parameter change. Off by '
        'default because the build takes 2–3 seconds.'
    )

    # --- Error / status display ---
    error_box = inputs.addTextBoxCommandInput(INPUT_ERROR_TEXT, '', '', 2, True)
    error_box.isFullWidth = True

    # Wire handlers
    futil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.executePreview, command_preview, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.validateInputs, command_validate_input, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.inputChanged, command_input_changed, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


# =========================================================================
# Input → SnaplockInterfaceParams
# =========================================================================

def _read_selected_face(inputs) -> adsk.fusion.BRepFace:
    """Return the selected BRepFace or None."""
    sel = adsk.core.SelectionCommandInput.cast(inputs.itemById(INPUT_FACE_SELECT))
    if not sel or sel.selectionCount == 0:
        return None
    entity = sel.selection(0).entity
    return adsk.fusion.BRepFace.cast(entity)


def _params_from_inputs(inputs: adsk.core.CommandInputs):
    """Read the dialog inputs and construct a SnaplockInterfaceParams instance."""
    _ensure_snaplock_on_path()
    import snaplock  # type: ignore

    def get_cm(inp_id):
        return inputs.itemById(inp_id).value

    def get_deg(inp_id):
        import math as _math
        return _math.degrees(inputs.itemById(inp_id).value)

    def get_int(inp_id):
        return int(inputs.itemById(inp_id).value)

    def get_bool(inp_id):
        return bool(inputs.itemById(inp_id).value)

    def get_str(inp_id):
        return inputs.itemById(inp_id).value

    # Read face to get cavity_inner_radius + slot_ceiling_z
    face = _read_selected_face(inputs)
    cavity_r = 0.0
    ceiling_z = 0.0
    if face is not None:
        from snaplock.interface_builder import _read_face_frame
        frame = _read_face_frame(face)
        if frame is not None:
            cavity_r = frame["radius_cm"]
            ceiling_z = frame["top_z_cm"]

    iparams = snaplock.SnaplockInterfaceParams(
        cavity_inner_radius=cavity_r,
        slot_ceiling_z=ceiling_z,
        body_height=get_cm(INPUT_BODY_HEIGHT),
        rim_height=get_cm(INPUT_RIM_HEIGHT),
        rim_thickness=get_cm(INPUT_RIM_THICKNESS),
        lid_clearance=get_cm(INPUT_LID_CLEARANCE),
        ceiling_cap_thickness=get_cm(INPUT_CAP_THICKNESS),
        receiver_wall_thickness=get_cm(INPUT_WALL_THICKNESS),
        tab_width=get_cm(INPUT_TAB_WIDTH),
        tab_drop_height=get_cm(INPUT_TAB_DROP),
        tab_revolve_angle=get_deg(INPUT_TAB_ANGLE),
        slot_entry_angle=get_deg(INPUT_ENTRY_ANGLE),
        num_tabs=get_int(INPUT_NUM_TABS),
        column_protrusion=get_cm(INPUT_COL_PROTRUSION),
        create_matching_lid=get_bool(INPUT_CREATE_LID),
        lid_name=get_str(INPUT_LID_NAME),
    )
    return iparams, snaplock, face


# =========================================================================
# Input change — update info box when face changes
# =========================================================================

def command_input_changed(args: adsk.core.InputChangedEventArgs):
    """Update the info box with face details when the selection changes."""
    try:
        if args.input.id != INPUT_FACE_SELECT:
            return
        inputs = args.inputs
        info_box = inputs.itemById(INPUT_INFO_TEXT)
        face = _read_selected_face(inputs)
        if face is None:
            info_box.formattedText = '<i>Select a cylindrical face above.</i>'
            return
        _ensure_snaplock_on_path()
        from snaplock.interface_builder import _read_face_frame  # type: ignore
        frame = _read_face_frame(face)
        if frame is None:
            info_box.formattedText = (
                '<font color="red">Face must be a cylinder with its axis '
                'parallel to world +Z.</font>'
            )
            return
        info_box.formattedText = (
            f'<b>Cavity ⌀{frame["radius_cm"]*20:.1f} mm</b> '
            f'(R={frame["radius_cm"]*10:.2f} mm), '
            f'face top Z={frame["top_z_cm"]*10:.1f} mm, '
            f'height {frame["height_cm"]*10:.1f} mm'
        )
    except Exception:
        pass


# =========================================================================
# Validation (live)
# =========================================================================

def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    inputs = args.inputs
    try:
        iparams, _snaplock, face = _params_from_inputs(inputs)
        error_box = inputs.itemById(INPUT_ERROR_TEXT)

        if face is None:
            error_box.formattedText = (
                '<font color="orange">Select a cylindrical face to begin.</font>'
            )
            args.areInputsValid = False
            return

        if iparams.cavity_inner_radius <= 0:
            error_box.formattedText = (
                '<font color="red">Could not read cavity radius from face. '
                'Make sure the face is a cylinder with vertical axis.</font>'
            )
            args.areInputsValid = False
            return

        errors = iparams.validate()

        # Additional check: interface depth must fit within the face's height
        _ensure_snaplock_on_path()
        from snaplock.interface_builder import _read_face_frame  # type: ignore
        frame = _read_face_frame(face)
        if frame is not None:
            min_depth = iparams.rim_height + iparams.tab_drop_height + iparams.tab_chamfer_drop
            if frame["height_cm"] < min_depth:
                errors.append(
                    f'Interface requires {min_depth*10:.1f} mm of face height; '
                    f'selected face is only {frame["height_cm"]*10:.1f} mm tall.'
                )

        if errors:
            msg = '<b>Please fix:</b><br>' + '<br>'.join(f'• {e}' for e in errors)
            error_box.formattedText = msg
            args.areInputsValid = False
        else:
            error_box.formattedText = '<font color="green">✓ Ready to build.</font>'
            args.areInputsValid = True
    except Exception as e:
        args.areInputsValid = False
        try:
            err_box = inputs.itemById(INPUT_ERROR_TEXT)
            err_box.formattedText = f'<font color="red">Input error: {e}</font>'
        except Exception:
            pass


# =========================================================================
# Preview (live rebuild on input change, opt-in via checkbox)
# =========================================================================

def command_preview(args: adsk.core.CommandEventArgs):
    inputs = args.command.commandInputs

    try:
        preview_on = bool(inputs.itemById(INPUT_PREVIEW).value)
    except Exception:
        preview_on = False
    if not preview_on:
        return

    try:
        iparams, snaplock, face = _params_from_inputs(inputs)
    except Exception:
        return

    if face is None or iparams.validate():
        return

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        return

    try:
        snaplock.build_snaplock_interface(iparams, design, face)
        args.isValidResult = True
    except Exception:
        pass


# =========================================================================
# Execute the build
# =========================================================================

def command_execute(args: adsk.core.CommandEventArgs):
    inputs = args.command.commandInputs

    try:
        iparams, snaplock, face = _params_from_inputs(inputs)

        if face is None:
            ui.messageBox('Please select a cylindrical face first.', 'SnapLock Interface')
            return

        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox('Active document is not a Fusion design.', 'SnapLock Interface')
            return

        tm_start = design.timeline.markerPosition

        try:
            result = snaplock.build_snaplock_interface(iparams, design, face)
        except ValueError as e:
            ui.messageBox(f'Invalid parameters:\n{e}', 'SnapLock Interface')
            _rollback_to(design, tm_start)
            return
        except RuntimeError as e:
            ui.messageBox(f'SnapLock Interface build failed:\n{e}', 'SnapLock Interface')
            _rollback_to(design, tm_start)
            return
        except Exception as e:
            ui.messageBox(
                f'SnapLock Interface crashed:\n{e}\n\n{traceback.format_exc()}',
                'SnapLock Interface',
            )
            _rollback_to(design, tm_start)
            return

        try:
            app.activeViewport.fit()
        except Exception:
            pass

        # Log committed params for reproducibility
        cavity_mm = iparams.cavity_inner_radius * 20  # diameter
        parts = [
            f"cavity⌀{cavity_mm:.1f}mm",
            f"depth={iparams.body_height*10:g}mm",
            f"rim_h={iparams.rim_height*10:g}mm",
            f"wall={iparams.rim_thickness*10:g}mm",
            f"clearance={iparams.lid_clearance*10:g}mm",
            f"tabs={iparams.num_tabs}",
            f"tab_angle={iparams.tab_revolve_angle:g}deg",
            f"entry={iparams.slot_entry_angle:g}deg",
        ]
        what = []
        rec = result.get('receiver') or {}
        if rec.get('volume_mm3') is not None:
            delta = rec['volume_mm3'] - rec.get('initial_volume_mm3', 0)
            what.append(f"interface(Δ{delta:+.0f}mm³)")
        if result.get('lid'):
            what.append(f"lid({result['lid']['volume_mm3']:.0f}mm³)")
        app.log(
            f'[SnapLock Interface] {"+".join(what) or "nothing"} ' + ' '.join(parts)
        )

        if result.get('warnings'):
            warning_text = '\n'.join(f'• {w}' for w in result['warnings'])
            ui.messageBox(
                f'SnapLock Interface created with warnings:\n\n{warning_text}',
                'SnapLock Interface',
            )

    except Exception:
        ui.messageBox(
            f'SnapLock Interface execute failed:\n{traceback.format_exc()}',
            'SnapLock Interface',
        )


def _rollback_to(design: adsk.fusion.Design, marker_position: int):
    try:
        design.timeline.markerPosition = marker_position
    except Exception:
        pass


def command_destroy(_args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
