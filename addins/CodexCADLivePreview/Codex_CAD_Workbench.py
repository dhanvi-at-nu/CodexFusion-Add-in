import datetime
import importlib.util
import json
import math
import os
import sys
import traceback

import adsk.core
import adsk.fusion

ADDIN_DIR = os.path.dirname(os.path.abspath(__file__))
if ADDIN_DIR not in sys.path:
    sys.path.insert(0, ADDIN_DIR)

from fusion_runtime import runner as preview_runner


ADDIN_NAME = 'Codex CAD Workbench'
CMD_ID = 'Codex_CAD_Workbench_RunCommand'
CMD_NAME = 'Codex CAD Workbench'
CMD_DESCRIPTION = 'Run a Codex-authored Fusion CAD preview.'
WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidScriptsAddinsPanel'
GENERATED_COMPONENT_NAME = 'Codex_Preview'
PALETTE_ID = 'CodexCADLivePreviewPalette'
PALETTE_NAME = 'Codex CAD Workbench'
ATTR_GROUP = 'CodexCADWorkbench'
ATTR_NAME = 'generated'
ATTR_PART_NAME = 'partName'

_app = None
_ui = None
_handlers = []
_command_control = None
_command_definition = None
_palette = None
_cached_project = None
_cached_enabled_parts = []
_cached_project_folder = None


def _addin_folder():
    return os.path.dirname(os.path.abspath(__file__))


def _default_project_folder():
    return os.path.join(_addin_folder(), 'example_project')


def _icon_folder():
    return ''


def _palette_url():
    return os.path.join(_addin_folder(), 'workbench_palette', 'index.html').replace('\\', '/')


def _message(text):
    if _ui:
        _ui.messageBox(text, ADDIN_NAME)


class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            command = args.command
            command.isExecutedWhenPreEmpted = False
            command.cancelButtonText = 'Close'
            try:
                command.isOKButtonVisible = False
            except Exception:
                command.okButtonText = 'Done'
            inputs = command.commandInputs

            inputs.addStringValueInput(
                'project_folder',
                'Project folder',
                _default_project_folder()
            )
            inputs.addBoolValueInput('load_project', 'Load project.json', False, '')
            inputs.addTextBoxCommandInput('project_status', 'Project status', 'Project not loaded.', 2, True)

            inputs.addBoolValueInput('generate_all', 'Generate all enabled parts', True, '')
            parts_dropdown = inputs.addDropDownCommandInput(
                'part_select',
                'Enabled part',
                adsk.core.DropDownStyles.TextListDropDownStyle
            )
            _populate_parts_dropdown(parts_dropdown, _cached_enabled_parts)
            parts_dropdown.isEnabled = False

            inputs.addBoolValueInput('apply_assembly', 'Run assembly.py / main_assembly.json', True, '')

            inputs.addBoolValueInput('run_now', 'Run preview', False, '')
            inputs.addTextBoxCommandInput('run_output', 'Output', 'Ready. Click "Run preview" to rebuild tagged preview geometry.', 10, True)
            inputs.addTextBoxCommandInput(
                'instructions',
                'Action',
                'Click "Load project.json" to list enabled parts. Click "Run preview" after Codex edits part or assembly scripts.',
                3,
                True
            )

            execute_handler = CommandExecuteHandler()
            validate_handler = ValidateInputsHandler()
            changed_handler = CommandInputChangedHandler()
            destroy_handler = CommandDestroyHandler()
            command.execute.add(execute_handler)
            command.validateInputs.add(validate_handler)
            command.inputChanged.add(changed_handler)
            command.destroy.add(destroy_handler)
            _handlers.extend([execute_handler, validate_handler, changed_handler, destroy_handler])
        except Exception:
            _message('Failed to create command dialog:\n{}'.format(traceback.format_exc()))


class ValidateInputsHandler(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        try:
            folder_input = args.inputs.itemById('project_folder')
            folder = folder_input.value.strip() if folder_input else ''
            args.areInputsValid = bool(folder)
        except Exception:
            args.areInputsValid = False


class CommandExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            # Intentionally do nothing on OK/Close. Running is triggered by the in-dialog
            # "Run preview" button so the dialog can stay open for iteration.
            pass
        except Exception:
            pass


class CommandInputChangedHandler(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        try:
            changed = args.input
            inputs = args.inputs

            if changed.id == 'generate_all':
                dd = inputs.itemById('part_select')
                if dd:
                    dd.isEnabled = not bool(changed.value)
                return

            if changed.id == 'load_project' and bool(changed.value):
                changed.value = False
                folder = inputs.itemById('project_folder').value.strip()
                project, enabled_parts = _load_project(folder)
                _cache_project(folder, project, enabled_parts)

                status = inputs.itemById('project_status')
                if status:
                    status.text = 'Loaded {} enabled part(s) from project.json.'.format(len(enabled_parts))

                dd = inputs.itemById('part_select')
                if dd:
                    _populate_parts_dropdown(dd, enabled_parts)
                    dd.isEnabled = not bool(inputs.itemById('generate_all').value)
                return

            if changed.id == 'run_now' and bool(changed.value):
                changed.value = False
                output = inputs.itemById('run_output')
                try:
                    folder = inputs.itemById('project_folder').value.strip()
                    generate_all = inputs.itemById('generate_all').value
                    dd = inputs.itemById('part_select')
                    selected_part = dd.selectedItem.name if dd and dd.selectedItem else None
                    apply_assembly = inputs.itemById('apply_assembly').value

                    result = run_project(
                        folder,
                        generate_all=generate_all,
                        selected_part_name=selected_part,
                        apply_assembly=apply_assembly
                    )
                    if output:
                        output.text = result
                except Exception:
                    if output:
                        output.text = 'Generation failed:\n{}'.format(traceback.format_exc())
                return
        except Exception:
            status = args.inputs.itemById('project_status') if args and args.inputs else None
            if status:
                status.text = 'Load failed:\n{}'.format(traceback.format_exc())


class CommandDestroyHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        # Keep global handlers for the add-in lifetime; Fusion releases local handler
        # objects unless Python keeps a reference to them.
        pass


class PaletteCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            execute_handler = PaletteCommandExecuteHandler()
            destroy_handler = CommandDestroyHandler()
            args.command.execute.add(execute_handler)
            args.command.destroy.add(destroy_handler)
            _handlers.extend([execute_handler, destroy_handler])
        except Exception:
            _message('Failed to create palette command:\n{}'.format(traceback.format_exc()))


class PaletteCommandExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            _show_palette()
        except Exception:
            _message('Failed to open Codex CAD palette:\n{}'.format(traceback.format_exc()))


class PaletteClosedHandler(adsk.core.UserInterfaceGeneralEventHandler):
    def notify(self, args):
        global _palette
        _palette = None


class PaletteIncomingHandler(adsk.core.HTMLEventHandler):
    def notify(self, args):
        try:
            payload = json.loads(args.data or '{}')
            if args.action == 'getState':
                project_folder = _cached_project_folder or _default_project_folder()
                project = None
                enabled_parts = []
                status = 'Project not loaded.'
                try:
                    project, enabled_parts = _load_project(project_folder)
                    _cache_project(project_folder, project, enabled_parts)
                    status = 'Loaded {} enabled part(s) from project.json.'.format(len(enabled_parts))
                except Exception as ex:
                    status = str(ex)
                args.returnData = json.dumps({
                    'ok': True,
                    'projectFolder': project_folder,
                    'status': status,
                    'parts': [part.get('name', 'Unnamed') for part in enabled_parts],
                })
                return

            if args.action == 'loadProject':
                project_folder = payload.get('projectFolder') or _default_project_folder()
                project, enabled_parts = _load_project(project_folder)
                _cache_project(project_folder, project, enabled_parts)
                args.returnData = json.dumps({
                    'ok': True,
                    'status': 'Loaded {} enabled part(s) from project.json.'.format(len(enabled_parts)),
                    'parts': [part.get('name', 'Unnamed') for part in enabled_parts],
                })
                return

            if args.action == 'runPreview':
                project_folder = payload.get('projectFolder') or _default_project_folder()
                result = run_project(
                    project_folder,
                    generate_all=bool(payload.get('generateAll', True)),
                    selected_part_name=payload.get('selectedPart'),
                    apply_assembly=bool(payload.get('applyAssembly', True)),
                )
                args.returnData = json.dumps({'ok': True, 'output': result})
                return

            if args.action == 'exportSTL':
                project_folder = payload.get('projectFolder') or _default_project_folder()
                result = export_stl(
                    project_folder,
                    selected_part_name=payload.get('selectedPart') or None,
                )
                args.returnData = json.dumps({'ok': True, 'output': result})
                return

            args.returnData = json.dumps({'ok': False, 'error': 'Unknown action: {}'.format(args.action)})
        except Exception:
            args.returnData = json.dumps({'ok': False, 'error': traceback.format_exc()})


def _show_palette():
    global _palette
    palettes = _ui.palettes
    palette = palettes.itemById(PALETTE_ID)
    if not palette:
        palette = palettes.add(
            id=PALETTE_ID,
            name=PALETTE_NAME,
            htmlFileURL=_palette_url(),
            isVisible=True,
            showCloseButton=True,
            isResizable=True,
            width=620,
            height=640,
            useNewWebBrowser=True,
        )
        closed_handler = PaletteClosedHandler()
        incoming_handler = PaletteIncomingHandler()
        palette.closed.add(closed_handler)
        palette.incomingFromHTML.add(incoming_handler)
        _handlers.extend([closed_handler, incoming_handler])

    try:
        palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
    except Exception:
        pass
    palette.isVisible = True
    _palette = palette


def run(context):
    global _app, _ui, _command_control, _command_definition
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface

        existing = _ui.commandDefinitions.itemById(CMD_ID)
        if existing:
            existing.deleteMe()

        _command_definition = _ui.commandDefinitions.addButtonDefinition(
            CMD_ID,
            CMD_NAME,
            CMD_DESCRIPTION,
            _icon_folder()
        )

        created_handler = PaletteCommandCreatedHandler()
        _command_definition.commandCreated.add(created_handler)
        _handlers.append(created_handler)

        workspace = _ui.workspaces.itemById(WORKSPACE_ID)
        if not workspace:
            raise RuntimeError('Could not find Fusion design workspace: {}'.format(WORKSPACE_ID))

        panel = workspace.toolbarPanels.itemById(PANEL_ID)
        if not panel:
            raise RuntimeError('Could not find toolbar panel: {}'.format(PANEL_ID))

        old_control = panel.controls.itemById(CMD_ID)
        if old_control:
            old_control.deleteMe()

        _command_control = panel.controls.addCommand(_command_definition)
        _command_control.isPromoted = True
        _command_control.isPromotedByDefault = True
    except Exception:
        if _ui:
            _ui.messageBox('Add-in start failed:\n{}'.format(traceback.format_exc()), ADDIN_NAME)


def stop(context):
    global _command_control, _command_definition, _palette
    try:
        if _command_control:
            _command_control.deleteMe()
            _command_control = None

        if _command_definition:
            _command_definition.deleteMe()
            _command_definition = None

        palette = _ui.palettes.itemById(PALETTE_ID) if _ui else None
        if palette:
            palette.deleteMe()
        _palette = None

        _handlers.clear()
    except Exception:
        if _ui:
            _ui.messageBox('Add-in stop failed:\n{}'.format(traceback.format_exc()), ADDIN_NAME)


def run_project(project_folder, generate_all=True, selected_part_name=None, custom_part_script='', apply_assembly=True):
    if custom_part_script:
        raise RuntimeError('Custom script mode has been replaced by the project preview loop. Add the script to project.json instead.')
    return preview_runner.run_preview(
        _app,
        _ui,
        project_folder,
        generate_all=generate_all,
        selected_part_name=selected_part_name,
        apply_assembly=apply_assembly
    )


def export_stl(project_folder, selected_part_name=None):
    return preview_runner.export_stl(
        _app,
        _ui,
        project_folder,
        selected_part_name=selected_part_name,
    )


def _reset_generated_component(root, log_lines):
    for index in range(root.occurrences.count - 1, -1, -1):
        occurrence = root.occurrences.item(index)
        if occurrence.name == GENERATED_COMPONENT_NAME or occurrence.component.name == GENERATED_COMPONENT_NAME:
            occurrence.deleteMe()

    try:
        occurrence = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        occurrence.component.name = GENERATED_COMPONENT_NAME
        mark_generated(occurrence.component)
        mark_generated(occurrence)
        return occurrence.component
    except Exception as ex:
        # Newer Fusion workflows can create "Part design" documents which only support
        # a single component. In that case we generate directly into the root component.
        log_lines.append('- Note: generating into the root component (single-component mode).')
        log_lines.append('- Note: could not create generated component: {}'.format(str(ex)))
        _clear_generated_contents(root)
        return root


def mark_generated(entity):
    # Tag bodies/sketches we create so we can delete them safely in Part design docs.
    try:
        entity.attributes.add(ATTR_GROUP, ATTR_NAME, '1')
    except Exception:
        pass


def mark_generated_for_part(entity, part_name):
    mark_generated(entity)
    try:
        entity.attributes.add(ATTR_GROUP, ATTR_PART_NAME, str(part_name))
    except Exception:
        pass


def _body_count(component):
    try:
        count = component.bRepBodies.count
        for index in range(component.occurrences.count):
            occ = component.occurrences.item(index)
            if occ and occ.component:
                count += _body_count(occ.component)
        return count
    except Exception:
        return 0


def _refresh_viewport(log_lines):
    try:
        viewport = _app.activeViewport if _app else None
        if not viewport:
            log_lines.append('- Warning: no active viewport was available to fit.')
            return
        viewport.refresh()
        viewport.fit()
        log_lines.append('- Viewport refreshed and fit to generated geometry.')
    except Exception:
        log_lines.append('- Warning: viewport fit failed:\n  {}'.format(traceback.format_exc().strip()))


def _is_generated(entity):
    try:
        attr = entity.attributes.itemByName(ATTR_GROUP, ATTR_NAME)
        return attr is not None
    except Exception:
        return False


def _clear_generated_contents(component):
    # Best-effort cleanup: remove only Codex-tagged geometry. This is important in
    # Part design docs where we can't isolate generation under a separate component.
    for index in range(component.occurrences.count - 1, -1, -1):
        occ = component.occurrences.item(index)
        if _is_generated(occ) or _is_generated(occ.component):
            try:
                occ.deleteMe()
            except Exception:
                pass

    for index in range(component.bRepBodies.count - 1, -1, -1):
        body = component.bRepBodies.item(index)
        if _is_generated(body) or (hasattr(body, 'name') and body.name.startswith('codex_')):
            try:
                body.deleteMe()
            except Exception:
                pass

    for index in range(component.sketches.count - 1, -1, -1):
        sketch = component.sketches.item(index)
        if _is_generated(sketch) or (hasattr(sketch, 'name') and sketch.name.startswith('codex_')):
            try:
                sketch.deleteMe()
            except Exception:
                pass


def _ensure_part_component(generated_component, part_name, log_lines):
    """
    Returns (component, occurrence_or_none) to generate this part into.

    Legacy helper retained for compatibility with older scripts.
    """
    # If we're in Part design fallback mode, we can't create additional components.
    # Detect this by checking whether generating_component is the root component.
    try:
        design = adsk.fusion.Design.cast(_app.activeProduct)
        if design and design.rootComponent == generated_component:
            log_lines.append('- Note: Part design mode; `{}` will be generated into the root component.'.format(part_name))
            return generated_component, None
    except Exception:
        pass

    # Assembly-capable: create a fresh component for this part, deleting any old one with same name.
    occs = generated_component.occurrences
    for index in range(occs.count - 1, -1, -1):
        occ = occs.item(index)
        if occ and (occ.name == part_name or occ.component.name == part_name):
            try:
                occ.deleteMe()
            except Exception:
                pass

    occ = occs.addNewComponent(adsk.core.Matrix3D.create())
    occ.component.name = part_name
    mark_generated_for_part(occ, part_name)
    mark_generated_for_part(occ.component, part_name)
    return occ.component, occ


def _run_part_script(script_path, project_folder, generated_component, project, part, log_lines):
    if not os.path.isfile(script_path):
        raise RuntimeError('Part script was not found: {}'.format(script_path))

    module_name = 'codex_part_{}'.format(abs(hash(script_path)))
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if not spec or not spec.loader:
        raise RuntimeError('Could not load part script: {}'.format(script_path))

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, 'generate'):
        raise RuntimeError('Part script must define generate(context).')

    context = {
        'app': _app,
        'ui': _ui,
        'project': project,
        'project_name': project.get('project_name') or project.get('name') or project.get('project') or 'Unnamed Project',
        'global_parameters': project.get('global_parameters', {}),
        'part': part,
        'generated_component': generated_component,
        'project_folder': project_folder,
        'units': 'mm',
        'log': log_lines,
        'mark_generated': mark_generated,
        'mark_generated_for_part': mark_generated_for_part,
    }
    module.generate(context)
    log_lines.append('- Generated `{}` from `{}`.'.format(
        part.get('name', os.path.basename(script_path)),
        os.path.relpath(script_path, context['project_folder']).replace('\\', '/')
    ))


def _new_log(project_folder, project):
    return [
        '# Codex CAD Workbench Run Log',
        '',
        '- Status: running',
        '- Timestamp: {}'.format(datetime.datetime.now().isoformat(timespec='seconds')),
        '- Project folder: `{}`'.format(project_folder),
        '- Project name: `{}`'.format(project.get('project_name') or project.get('name') or 'Unnamed Project'),
        '- Units: `mm`',
        '',
        '## Generated Parts',
    ]


def _load_project(project_folder):
    project = preview_runner.load_project(project_folder)
    return project, preview_runner.enabled_parts(project)


def _cache_project(project_folder, project, enabled_parts):
    global _cached_project, _cached_enabled_parts, _cached_project_folder
    _cached_project_folder = project_folder
    _cached_project = project
    _cached_enabled_parts = enabled_parts


def _populate_parts_dropdown(dropdown, enabled_parts):
    try:
        items = dropdown.listItems
        for idx in range(items.count - 1, -1, -1):
            try:
                items.item(idx).deleteMe()
            except Exception:
                pass
        if not enabled_parts:
            items.add('(none)', True, '')
            return
        first = True
        for part in enabled_parts:
            name = part.get('name', 'Unnamed')
            items.add(name, first, '')
            first = False
    except Exception:
        pass


def _auto_set_project_from_script(inputs, script_path):
    # If the user selects/pastes a part script path, auto-detect the project folder
    # so logs and assemblies resolve as expected.
    try:
        script_path = os.path.abspath(os.path.expanduser(str(script_path).strip()))
        if not os.path.isfile(script_path):
            return

        script_dir = os.path.dirname(script_path)
        project_root = _find_project_root(script_dir) or script_dir

        folder_input = inputs.itemById('project_folder')
        if folder_input:
            folder_input.value = project_root

        status = inputs.itemById('project_status')
        dd = inputs.itemById('part_select')

        project_path = os.path.join(project_root, 'project.json')
        if os.path.isfile(project_path):
            project, enabled_parts = _load_project(project_root)
            _cache_project(project_root, project, enabled_parts)
            if status:
                status.text = 'Auto-loaded {} enabled part(s) from project.json.'.format(len(enabled_parts))
            if dd:
                _populate_parts_dropdown(dd, enabled_parts)
        else:
            _cache_project(project_root, None, [])
            if status:
                status.text = 'No project.json found; will run custom script only.'
            if dd:
                _populate_parts_dropdown(dd, [])
    except Exception:
        status = inputs.itemById('project_status')
        if status:
            status.text = 'Auto-detect failed:\n{}'.format(traceback.format_exc())


def _find_project_root(start_dir):
    # Walk up until we find a folder containing project.json.
    try:
        current = os.path.abspath(start_dir)
        while True:
            if os.path.isfile(os.path.join(current, 'project.json')):
                return current
            parent = os.path.dirname(current)
            if not parent or parent == current:
                return None
            current = parent
    except Exception:
        return None


def _mm_to_cm(value_mm):
    # Fusion model-space distances are centimeters.
    return float(value_mm) / 10.0


def _deg_to_rad(value_deg):
    return float(value_deg) * math.pi / 180.0


def _is_identity_placement(translation, rotation_deg):
    return all(abs(float(value)) < 1e-12 for value in list(translation) + list(rotation_deg))


def _placement_transform(translation, rotation_deg):
    """
    Build a Fusion Matrix3D without Matrix3D.multiplyBy, which is unavailable in
    some bundled Fusion Python APIs. Translation is mm; rotation is X->Y->Z Euler.
    """
    tx, ty, tz = [float(value) for value in translation]
    rx, ry, rz = [_deg_to_rad(value) for value in rotation_deg]

    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

    # R = Rz * Ry * Rx, matching X then Y then Z application order.
    matrix_values = [
        [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
        [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
        [-sy, cy * sx, cy * cx],
    ]

    transform = adsk.core.Matrix3D.create()
    transform.setToIdentity()
    for row in range(3):
        for column in range(3):
            transform.setCell(row, column, matrix_values[row][column])
    transform.translation = adsk.core.Vector3D.create(
        _mm_to_cm(tx), _mm_to_cm(ty), _mm_to_cm(tz)
    )
    return transform


def _apply_main_assembly(project_folder, part_occurrences, log_lines):
    """
    Optional: reads assemblies/main_assembly.json and places part occurrences.
    Translation is in mm, rotation is Euler degrees [x, y, z] about the origin.
    """
    assembly_path = os.path.join(project_folder, 'assemblies', 'main_assembly.json')
    if not os.path.isfile(assembly_path):
        log_lines.append('')
        log_lines.append('## Assembly Placement')
        log_lines.append('- No `assemblies/main_assembly.json` found; skipping placement.')
        return

    log_lines.append('')
    log_lines.append('## Assembly Placement')
    with open(assembly_path, 'r', encoding='utf-8') as assembly_file:
        assembly = json.load(assembly_file)

    components = assembly.get('components') or []
    if not isinstance(components, list) or not components:
        log_lines.append('- `assemblies/main_assembly.json` has no components; skipping placement.')
        return

    placed = 0
    for comp_spec in components:
        if not isinstance(comp_spec, dict):
            continue
        name = comp_spec.get('name')
        if not name:
            continue

        translation = comp_spec.get('translation') or [0, 0, 0]
        rotation_deg = comp_spec.get('rotation_deg') or [0, 0, 0]
        if len(translation) != 3 or len(rotation_deg) != 3:
            log_lines.append('- Warning: `{}` has invalid translation/rotation; skipping.'.format(name))
            continue

        tx, ty, tz = translation
        rx, ry, rz = rotation_deg

        transform = _placement_transform(translation, rotation_deg)

        occ = part_occurrences.get(name) if part_occurrences else None
        if occ:
            try:
                occ.transform = transform
                placed += 1
                log_lines.append('- Placed `{}` (occurrence) at mm {} with rotation_deg {}.'.format(name, translation, rotation_deg))
                continue
            except Exception:
                log_lines.append('- Warning: failed to place `{}` occurrence:\n  {}'.format(name, traceback.format_exc().strip()))

        # Fallback for single-component docs: move bodies tagged for this part.
        moved = _move_part_bodies_by_name(name, transform, log_lines, _is_identity_placement(translation, rotation_deg))
        if moved:
            placed += 1
            log_lines.append('- Placed `{}` (bodies) at mm {} with rotation_deg {}.'.format(name, translation, rotation_deg))
        else:
            log_lines.append('- Warning: assembly references `{}` but no matching occurrence/bodies were found.'.format(name))

    if placed == 0:
        log_lines.append('- No components were placed.')


def _move_part_bodies_by_name(part_name, transform, log_lines, is_identity=False):
    try:
        design = adsk.fusion.Design.cast(_app.activeProduct)
        if not design:
            return False
        root = design.rootComponent
        bodies = adsk.core.ObjectCollection.create()

        for index in range(root.bRepBodies.count):
            body = root.bRepBodies.item(index)
            if _entity_part_name(body) == part_name:
                bodies.add(body)

        # As a secondary heuristic, match the codex_ prefix naming convention.
        if bodies.count == 0:
            prefix = 'codex_{}_'.format(part_name)
            for index in range(root.bRepBodies.count):
                body = root.bRepBodies.item(index)
                if hasattr(body, 'name') and body.name.startswith(prefix):
                    bodies.add(body)

        if bodies.count == 0:
            return False

        if is_identity:
            return True

        move_features = root.features.moveFeatures
        move_input = move_features.createInput(bodies, transform)
        move_features.add(move_input)
        return True
    except Exception:
        log_lines.append('- Warning: failed to move bodies for `{}`:\n  {}'.format(part_name, traceback.format_exc().strip()))
        return False


def _entity_part_name(entity):
    try:
        attr = entity.attributes.itemByName(ATTR_GROUP, ATTR_PART_NAME)
        return attr.value if attr else None
    except Exception:
        return None


def _write_log(project_folder, log_lines, status):
    reviews_folder = os.path.join(project_folder, 'reviews')
    os.makedirs(reviews_folder, exist_ok=True)
    log_path = os.path.join(reviews_folder, 'run_log.md')

    lines = list(log_lines)
    for index, line in enumerate(lines):
        if line.startswith('- Status:'):
            lines[index] = '- Status: {}'.format(status)
            break

    with open(log_path, 'w', encoding='utf-8') as log_file:
        log_file.write('\n'.join(lines))
        log_file.write('\n')
