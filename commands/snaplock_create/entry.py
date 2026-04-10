"""
SnapLock Create command — UI dialog for generating a parametric twist-snap container.

This is the human-facing entry point. It wraps the same `snaplock` library
that the f360mcp add-in uses, so there's a single source of truth for the build
logic.
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
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_cmdSnaplockCreate'
CMD_NAME = 'SnapLock'
CMD_Description = 'Create a parametric twist-snap bayonet container (Lid + Receiver)'

# UI placement: shared "3D Print Tools" panel on the Solid tab.
# This panel ID is a convention shared across the flight505 3D-printing add-ins
# (Tongue & Groove, ThreadMaker, Knurling, Hexagon Generator, SnapLock).
# The FIRST add-in to start creates the panel; subsequent add-ins just add to it.
WORKSPACE_ID = 'FusionSolidEnvironment'
SOLID_TAB_ID = 'SolidTab'
SHARED_PANEL_ID = 'flight505_3DPrintTools_panel'
SHARED_PANEL_NAME = '3D Print Tools'
PANEL_POSITION_AFTER = 'SolidModifyPanel'  # Place panel after "Modify" on the Solid tab

IS_PROMOTED = True

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Input IDs
INPUT_GROUP_SIZE = 'group_size'
INPUT_GROUP_WALLS = 'group_walls'
INPUT_GROUP_LOCK = 'group_lock'
INPUT_GROUP_WHAT = 'group_what'

INPUT_OUTER_DIAMETER = 'outer_diameter'
INPUT_BODY_HEIGHT = 'body_height'
INPUT_RIM_HEIGHT = 'rim_height'

INPUT_OUTER_WALL = 'outer_wall_thickness'
INPUT_CHANNEL_WIDTH = 'channel_width'
INPUT_RIM_THICKNESS = 'rim_thickness'
INPUT_FLOOR_THICKNESS = 'floor_thickness'
INPUT_CAP_THICKNESS = 'cap_thickness'

INPUT_NUM_TABS = 'num_tabs'
INPUT_TAB_ANGLE = 'tab_revolve_angle'
INPUT_ENTRY_ANGLE = 'slot_entry_angle'
INPUT_TAB_WIDTH = 'tab_width'
INPUT_TAB_DROP = 'tab_drop_height'
INPUT_COL_PROTRUSION = 'column_protrusion'

INPUT_CREATE_LID = 'create_lid'
INPUT_CREATE_RECEIVER = 'create_receiver'

INPUT_ERROR_TEXT = 'error_text'

local_handlers = []


def _ensure_snaplock_on_path():
    """Add the snaplock library to sys.path so `import snaplock` works."""
    here = os.path.dirname(os.path.abspath(__file__))
    # This file: SnapLock/commands/snaplock_create/entry.py → up 2 = SnapLock/
    snaplock_root = os.path.abspath(os.path.join(here, '..', '..'))
    lib_path = os.path.join(snaplock_root, 'lib')
    if lib_path not in sys.path and os.path.isdir(lib_path):
        sys.path.insert(0, lib_path)


# =========================================================================
# Start / stop
# =========================================================================

def start():
    # Clean up any stale command definition left over from a previous run
    old = ui.commandDefinitions.itemById(CMD_ID)
    if old:
        old.deleteMe()

    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    futil.add_handler(cmd_def.commandCreated, command_created)

    # Find or create the shared "3D Print Tools" panel on the Solid tab
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
    # Scan all panels that might hold our button (shared panel + any legacy
    # placements) and remove from each.
    legacy_panel_ids = (
        SHARED_PANEL_ID,
        'SolidCreatePanel',  # legacy from earlier version of this add-in
        'SolidScriptsAddinsPanel',
    )
    for pid in legacy_panel_ids:
        panel = ui.allToolbarPanels.itemById(pid)
        if not panel:
            continue
        ctrl = panel.controls.itemById(CMD_ID)
        if ctrl:
            ctrl.deleteMe()
        # If the shared panel is now empty (no other 3D print tools running),
        # remove it so Fusion's UI doesn't show an empty panel.
        if pid == SHARED_PANEL_ID and panel.controls.count == 0:
            panel.deleteMe()

    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()


# =========================================================================
# Command created: build the dialog
# =========================================================================

def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f'{CMD_NAME} Command Created Event')
    inputs = args.command.commandInputs

    default_length = app.activeProduct.unitsManager.defaultLengthUnits

    # --- GROUP: Size ---
    g_size = inputs.addGroupCommandInput(INPUT_GROUP_SIZE, 'Size')
    g_size.isExpanded = True
    gs = g_size.children
    gs.addValueInput(
        INPUT_OUTER_DIAMETER, 'Outer diameter',
        default_length,
        adsk.core.ValueInput.createByString('60 mm'),
    )
    gs.addValueInput(
        INPUT_BODY_HEIGHT, 'Body height',
        default_length,
        adsk.core.ValueInput.createByString('10 mm'),
    )
    gs.addValueInput(
        INPUT_RIM_HEIGHT, 'Rim drop height',
        default_length,
        adsk.core.ValueInput.createByString('5 mm'),
    )

    # --- GROUP: Walls ---
    g_walls = inputs.addGroupCommandInput(INPUT_GROUP_WALLS, 'Walls')
    g_walls.isExpanded = False
    gw = g_walls.children
    gw.addValueInput(
        INPUT_OUTER_WALL, 'Outer wall thickness',
        default_length,
        adsk.core.ValueInput.createByString('2 mm'),
    )
    gw.addValueInput(
        INPUT_CHANNEL_WIDTH, 'Channel width',
        default_length,
        adsk.core.ValueInput.createByString('3 mm'),
    )
    gw.addValueInput(
        INPUT_RIM_THICKNESS, 'Rim thickness',
        default_length,
        adsk.core.ValueInput.createByString('2 mm'),
    )
    gw.addValueInput(
        INPUT_FLOOR_THICKNESS, 'Floor thickness',
        default_length,
        adsk.core.ValueInput.createByString('2 mm'),
    )
    gw.addValueInput(
        INPUT_CAP_THICKNESS, 'Lid cap thickness',
        default_length,
        adsk.core.ValueInput.createByString('2 mm'),
    )

    # --- GROUP: Locking mechanism ---
    g_lock = inputs.addGroupCommandInput(INPUT_GROUP_LOCK, 'Locking mechanism')
    g_lock.isExpanded = True
    gl = g_lock.children
    gl.addIntegerSpinnerCommandInput(
        INPUT_NUM_TABS, 'Number of tabs', 2, 12, 1, 4,
    )
    gl.addValueInput(
        INPUT_TAB_ANGLE, 'Tab arc angle',
        'deg',
        adsk.core.ValueInput.createByString('20 deg'),
    )
    gl.addValueInput(
        INPUT_ENTRY_ANGLE, 'Entry arc angle',
        'deg',
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
    gwh.addBoolValueInput(INPUT_CREATE_LID, 'Create Lid', True, '', True)
    gwh.addBoolValueInput(INPUT_CREATE_RECEIVER, 'Create Receiver', True, '', True)

    # Error display, updated by command_validate_input
    error_box = inputs.addTextBoxCommandInput(
        INPUT_ERROR_TEXT, '', '', 2, True
    )
    error_box.isFullWidth = True

    # Wire event handlers
    futil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.validateInputs, command_validate_input, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


# =========================================================================
# Input → SnaplockParams
# =========================================================================

def _params_from_inputs(inputs: adsk.core.CommandInputs):
    """Read the dialog inputs and construct a SnaplockParams instance."""
    _ensure_snaplock_on_path()
    import snaplock  # type: ignore

    # ValueInput.value returns Fusion native units (cm for length, rad for angle)
    def get_cm(inp_id):
        return inputs.itemById(inp_id).value

    def get_deg(inp_id):
        import math as _math
        return _math.degrees(inputs.itemById(inp_id).value)

    def get_int(inp_id):
        return int(inputs.itemById(inp_id).value)

    def get_bool(inp_id):
        return bool(inputs.itemById(inp_id).value)

    params = snaplock.SnaplockParams(
        outer_diameter=get_cm(INPUT_OUTER_DIAMETER),
        body_height=get_cm(INPUT_BODY_HEIGHT),
        rim_height=get_cm(INPUT_RIM_HEIGHT),
        outer_wall_thickness=get_cm(INPUT_OUTER_WALL),
        channel_width=get_cm(INPUT_CHANNEL_WIDTH),
        rim_thickness=get_cm(INPUT_RIM_THICKNESS),
        floor_thickness=get_cm(INPUT_FLOOR_THICKNESS),
        cap_thickness=get_cm(INPUT_CAP_THICKNESS),
        tab_width=get_cm(INPUT_TAB_WIDTH),
        tab_drop_height=get_cm(INPUT_TAB_DROP),
        tab_revolve_angle=get_deg(INPUT_TAB_ANGLE),
        slot_entry_angle=get_deg(INPUT_ENTRY_ANGLE),
        num_tabs=get_int(INPUT_NUM_TABS),
        column_protrusion=get_cm(INPUT_COL_PROTRUSION),
        create_lid=get_bool(INPUT_CREATE_LID),
        create_receiver=get_bool(INPUT_CREATE_RECEIVER),
    )
    return params, snaplock


# =========================================================================
# Validation (live)
# =========================================================================

def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    inputs = args.inputs
    try:
        params, _ = _params_from_inputs(inputs)
        errors = params.validate()

        if not params.create_lid and not params.create_receiver:
            errors.append('Must enable at least one of Lid / Receiver.')

        error_box = inputs.itemById(INPUT_ERROR_TEXT)
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
# Execute the build
# =========================================================================

def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Execute Event')
    inputs = args.command.commandInputs

    try:
        params, snaplock = _params_from_inputs(inputs)

        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox('Active document is not a Fusion design.')
            return

        # Remember the timeline position to allow rollback on failure
        tm_start = design.timeline.markerPosition

        try:
            result = snaplock.build_snaplock(params, design)
        except ValueError as e:
            ui.messageBox(f'Invalid parameters:\n{e}', 'SnapLock')
            _rollback_to(design, tm_start)
            return
        except RuntimeError as e:
            ui.messageBox(f'SnapLock build failed:\n{e}', 'SnapLock')
            _rollback_to(design, tm_start)
            return
        except Exception as e:
            ui.messageBox(
                f'SnapLock build crashed:\n{e}\n\n{traceback.format_exc()}',
                'SnapLock',
            )
            _rollback_to(design, tm_start)
            return

        try:
            app.activeViewport.fit()
        except Exception:
            pass

        summary_lines = ['SnapLock created successfully.']
        if result.get('lid'):
            summary_lines.append(
                f"Lid:      {result['lid']['volume_mm3']:.0f} mm³"
            )
        if result.get('receiver'):
            rec = result['receiver']
            summary_lines.append(
                f"Receiver: {rec['volume_mm3']:.0f} mm³"
            )
            cc = rec.get('column_check', {})
            if cc:
                summary_lines.append(
                    f"Snap columns: {cc.get('present_count', 0)}/{cc.get('total', 0)} verified"
                )
        if result.get('warnings'):
            summary_lines.append('')
            summary_lines.append('Warnings:')
            for w in result['warnings']:
                summary_lines.append(f'  • {w}')

        ui.messageBox('\n'.join(summary_lines), 'SnapLock')

    except Exception:
        futil.handle_error('command_execute')


def _rollback_to(design: adsk.fusion.Design, marker_position: int):
    """Roll the timeline back to a marker, suppressing errors."""
    try:
        design.timeline.markerPosition = marker_position
    except Exception:
        pass


def command_destroy(_args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Destroy Event')
    global local_handlers
    local_handlers = []
