import datetime
import importlib.util
import json
import os
import traceback

import adsk.core
import adsk.fusion

from . import helpers


PREVIEW_COMPONENT_NAME = 'Codex_Preview'
ATTR_GROUP = 'CodexCADWorkbench'
ATTR_GENERATED = 'generated'
ATTR_PART_NAME = 'partName'


def run_preview(app, ui, project_folder, generate_all=True, selected_part_name=None, apply_assembly=True):
    project_folder = os.path.abspath(os.path.expanduser(project_folder))
    project = load_project(project_folder)

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise RuntimeError('Open or create a Fusion Design before running Codex CAD Workbench.')

    log_lines = _new_log(project_folder, project)
    _ensure_direct_modeling(design, log_lines)
    root = design.rootComponent

    try:
        preview_component, preview_occurrence = _reset_preview_workspace(root, log_lines)
        parts_to_generate = _parts_to_generate(project, generate_all, selected_part_name)
        if not parts_to_generate:
            raise RuntimeError('No enabled parts found in project.json.')

        generated_parts = {}
        for part in parts_to_generate:
            part_name = part.get('name') or os.path.splitext(os.path.basename(part.get('script', 'part')))[0]
            before_bodies = _bodies_for_part(root, part_name)
            part_component, part_occurrence = _create_part_component(preview_component, part_name, log_lines)
            script_path = _script_path(project_folder, part)

            context = {
                'app': app,
                'ui': ui,
                'project': project,
                'project_name': project.get('project_name') or project.get('name') or 'Untitled CAD Project',
                'global_parameters': project.get('global_parameters', {}),
                'part': part,
                'part_name': part_name,
                'generated_component': part_component,
                'component': part_component,
                'project_folder': project_folder,
                'units': project.get('units', 'mm'),
                'log': log_lines,
                'helpers': helpers,
                'mark_generated': mark_generated,
                'mark_generated_for_part': mark_generated_for_part,
            }
            _run_part_script(script_path, context)
            part_bodies = _new_bodies_for_part(root, part_name, before_bodies)
            generated_parts[part_name] = {
                'component': part_component,
                'occurrence': part_occurrence,
                'bodies': part_bodies,
                'part': part,
            }
            log_lines.append('- Generated `{}` from `{}`.'.format(part_name, _relpath(script_path, project_folder)))
            log_lines.append('- `{}` body count: {}.'.format(part_name, len(part_bodies)))

        if apply_assembly:
            _run_assembly(project_folder, project, generated_parts, log_lines)
        else:
            log_lines.append('')
            log_lines.append('## Assembly')
            log_lines.append('- Assembly step disabled.')

        final_body_count = _body_count(preview_component)
        log_lines.append('')
        log_lines.append('## Viewport')
        log_lines.append('- Preview body count: {}.'.format(final_body_count))
        _refresh_viewport(app, log_lines)

        _write_log(project_folder, log_lines, 'success')
        return 'Preview rebuilt: {} part(s)\nVisible bodies: {}\n\nRun log:\n{}'.format(
            len(parts_to_generate),
            final_body_count,
            os.path.join(project_folder, 'reviews', 'run_log.md')
        )
    except Exception:
        log_lines.append('')
        log_lines.append('## Error')
        log_lines.append('```')
        log_lines.append(traceback.format_exc())
        log_lines.append('```')
        _write_log(project_folder, log_lines, 'failed')
        raise


def export_stl(app, ui, project_folder, selected_part_name=None):
    project_folder = os.path.abspath(os.path.expanduser(project_folder))
    project = load_project(project_folder)

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise RuntimeError('Open or create a Fusion Design before exporting STL.')

    root = design.rootComponent
    part_name = selected_part_name or _default_export_part_name(project)
    preview_occurrence = _find_preview_occurrence(root)
    if not preview_occurrence:
        bodies = _bodies_for_part(root, part_name) if part_name else _generated_bodies(root)
        bodies = [body for body in bodies if body and body.isValid]
        if not bodies:
            raise RuntimeError('No generated preview bodies found to export. Run Preview first.')
    else:
        bodies = []

    export_folder = os.path.join(project_folder, 'exports')
    os.makedirs(export_folder, exist_ok=True)

    safe_name = _safe_filename(project.get('project_name') or project.get('name') or 'codex_preview')
    if part_name:
        safe_name = '{}_{}'.format(safe_name, _safe_filename(part_name))
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    export_path = os.path.join(export_folder, '{}_{}.stl'.format(safe_name, timestamp))

    if preview_occurrence:
        export_entity = _find_part_occurrence(preview_occurrence.component, part_name) if part_name else preview_occurrence
        if not export_entity:
            export_entity = preview_occurrence
        body_count = _body_count(preview_occurrence.component)
    else:
        export_entity = bodies[0] if len(bodies) == 1 else root
        body_count = len(bodies)

    export_manager = design.exportManager
    options = export_manager.createSTLExportOptions(export_entity, export_path)
    _configure_stl_options(options)
    export_manager.execute(options)

    entity_note = '{} generated body/bodies'.format(body_count)
    return 'STL exported:\n{}\n\nIncluded: {}'.format(export_path, entity_note)


def _default_export_part_name(project):
    parts = enabled_parts(project)
    if len(parts) == 1:
        return parts[0].get('name')
    return None


def _generated_bodies(component):
    bodies = []
    try:
        for index in range(component.bRepBodies.count):
            body = component.bRepBodies.item(index)
            if _has_generated_attr(body) or _name_starts_with(body, 'codex_'):
                bodies.append(body)
        for index in range(component.occurrences.count):
            occurrence = component.occurrences.item(index)
            if occurrence and occurrence.component:
                bodies.extend(_generated_bodies(occurrence.component))
    except Exception:
        pass
    return bodies


def _find_preview_occurrence(root):
    try:
        for index in range(root.occurrences.count - 1, -1, -1):
            occurrence = root.occurrences.item(index)
            if occurrence and occurrence.component and occurrence.component.name == PREVIEW_COMPONENT_NAME:
                return occurrence
    except Exception:
        pass
    return None


def _find_part_occurrence(component, part_name):
    if not part_name:
        return None
    try:
        for index in range(component.occurrences.count):
            occurrence = component.occurrences.item(index)
            if occurrence and occurrence.component and (
                _safe_name(occurrence) == part_name or occurrence.component.name == part_name
            ):
                return occurrence
    except Exception:
        pass
    return None


def _configure_stl_options(options):
    for attr_name, value in [
        ('isBinaryFormat', True),
        ('sendToPrintUtility', False),
    ]:
        try:
            setattr(options, attr_name, value)
        except Exception:
            pass
    try:
        options.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementMedium
    except Exception:
        pass


def _safe_filename(value):
    value = str(value or 'export').strip()
    safe = []
    for char in value:
        if char.isalnum() or char in ('-', '_'):
            safe.append(char)
        else:
            safe.append('_')
    return ''.join(safe).strip('_') or 'export'


def load_project(project_folder):
    project_folder = os.path.abspath(os.path.expanduser(project_folder))
    project_path = os.path.join(project_folder, 'project.json')
    if not os.path.isfile(project_path):
        raise RuntimeError('project.json was not found in: {}'.format(project_folder))
    with open(project_path, 'r', encoding='utf-8') as project_file:
        return json.load(project_file)


def enabled_parts(project):
    parts = []
    for part in project.get('parts') or []:
        if isinstance(part, dict) and part.get('enabled', True):
            parts.append(part)
    return parts


def mark_generated(entity):
    try:
        entity.attributes.add(ATTR_GROUP, ATTR_GENERATED, '1')
    except Exception:
        pass


def mark_generated_for_part(entity, part_name):
    mark_generated(entity)
    try:
        entity.attributes.add(ATTR_GROUP, ATTR_PART_NAME, str(part_name))
    except Exception:
        pass


def _parts_to_generate(project, generate_all, selected_part_name):
    parts = enabled_parts(project)
    if generate_all:
        return parts
    return [part for part in parts if part.get('name') == selected_part_name]


def _ensure_direct_modeling(design, log_lines):
    try:
        if design.designType == adsk.fusion.DesignTypes.DirectDesignType:
            log_lines.append('- Design mode: direct modeling already enabled.')
            return
        design.designType = adsk.fusion.DesignTypes.DirectDesignType
        log_lines.append('- Design mode: switched to direct modeling to avoid preview timeline buildup.')
    except Exception:
        log_lines.append('- Warning: could not switch to direct modeling:\n  {}'.format(traceback.format_exc().strip()))


def _reset_preview_workspace(root, log_lines):
    deleted_occurrences = 0
    failed = []

    preview_occurrence = _find_preview_occurrence(root)
    if preview_occurrence:
        preview_component = preview_occurrence.component
        deleted_bodies, deleted_sketches = _clear_component_geometry(preview_component, failed)
        log_lines.append(
            '- Reused `Codex_Preview`: cleared {} body/bodies and {} sketch(es).'.format(
                deleted_bodies,
                deleted_sketches
            )
        )
        log_lines.append('- Preview mode: reused isolated component in the active document.')
        return preview_component, preview_occurrence

    try:
        preview_occurrence = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        _safe_set_component_name(preview_occurrence.component, PREVIEW_COMPONENT_NAME)
        mark_generated(preview_occurrence)
        mark_generated(preview_occurrence.component)
        preview_component = preview_occurrence.component
    except Exception:
        # Fusion's newer "Part Design" documents only allow one component. In
        # that mode, generate directly into root and clear only tagged preview
        # bodies/sketches. Avoid touching timeline features.
        deleted_bodies, deleted_sketches = _clear_root_preview_geometry(root, failed)
        log_lines.append(
            '- Part Design mode: generating directly in root; cleared {} body/bodies and {} sketch(es).'.format(
                deleted_bodies,
                deleted_sketches
            )
        )
        preview_occurrence = None
        preview_component = root

    if failed:
        log_lines.append('- Warning: Fusion could not delete {} stale preview occurrence(s); hidden instead: {}.'.format(
            len(failed),
            ', '.join(failed[:8])
        ))
    if preview_occurrence:
        log_lines.append('- Preview mode: isolated `Codex_Preview` component in the active document.')
    else:
        log_lines.append('- Preview mode: root-body fallback for Part Design document.')
    return preview_component, preview_occurrence


def _clear_component_geometry(component, failed):
    deleted_bodies = 0
    deleted_sketches = 0

    try:
        for index in range(component.occurrences.count - 1, -1, -1):
            occurrence = component.occurrences.item(index)
            try:
                occurrence.deleteMe()
            except Exception:
                failed.append(_safe_entity_label(occurrence, 'child occurrence'))
                _hide_stale_preview(occurrence)
    except Exception:
        failed.append('child occurrences')

    try:
        for index in range(component.bRepBodies.count - 1, -1, -1):
            body = component.bRepBodies.item(index)
            try:
                body.deleteMe()
                deleted_bodies += 1
            except Exception:
                failed.append(_safe_entity_label(body, 'body'))
    except Exception:
        failed.append('component bodies')

    try:
        for index in range(component.sketches.count - 1, -1, -1):
            sketch = component.sketches.item(index)
            try:
                sketch.deleteMe()
                deleted_sketches += 1
            except Exception:
                failed.append(_safe_entity_label(sketch, 'sketch'))
    except Exception:
        failed.append('component sketches')

    return deleted_bodies, deleted_sketches


def _clear_root_preview_geometry(root, failed):
    deleted_bodies = 0
    deleted_sketches = 0

    try:
        for index in range(root.bRepBodies.count - 1, -1, -1):
            body = root.bRepBodies.item(index)
            if _has_generated_attr(body) or _name_starts_with(body, 'codex_'):
                try:
                    body.deleteMe()
                    deleted_bodies += 1
                except Exception:
                    failed.append(_safe_entity_label(body, 'body'))
    except Exception:
        failed.append('root bodies')

    try:
        for index in range(root.sketches.count - 1, -1, -1):
            sketch = root.sketches.item(index)
            if _has_generated_attr(sketch) or _name_starts_with(sketch, 'codex_'):
                try:
                    sketch.deleteMe()
                    deleted_sketches += 1
                except Exception:
                    failed.append(_safe_entity_label(sketch, 'sketch'))
    except Exception:
        failed.append('root sketches')

    return deleted_bodies, deleted_sketches


def _hide_stale_preview(occurrence):
    try:
        occurrence.isLightBulbOn = False
    except Exception:
        pass
    try:
        if occurrence and occurrence.component:
            _safe_set_component_name(
                occurrence.component,
                'Codex_Preview_stale_{}'.format(datetime.datetime.now().strftime('%H%M%S'))
            )
    except Exception:
        pass


def _safe_entity_label(entity, fallback):
    try:
        name = entity.name
        if name:
            return '{} `{}`'.format(fallback, name)
    except Exception:
        pass
    return fallback


def _safe_name(entity):
    try:
        return entity.name
    except Exception:
        return ''


def _safe_set_component_name(component, name):
    try:
        component.name = name
    except Exception:
        pass


def _name_starts_with(entity, prefix):
    try:
        return bool(entity.name and entity.name.startswith(prefix))
    except Exception:
        return False


def _is_preview_occurrence(occurrence):
    try:
        return (
            occurrence.component.name == PREVIEW_COMPONENT_NAME
            or _has_generated_attr(occurrence)
            or _has_generated_attr(occurrence.component)
        )
    except Exception:
        return False


def _has_generated_attr(entity):
    try:
        return entity.attributes.itemByName(ATTR_GROUP, ATTR_GENERATED) is not None
    except Exception:
        return False


def _create_part_component(preview_component, part_name, log_lines):
    log_lines.append('- Generating `{}` directly inside `Codex_Preview`.'.format(part_name))
    return preview_component, None


def _script_path(project_folder, part):
    script = part.get('script')
    if not script:
        raise RuntimeError('Part `{}` is missing a script path.'.format(part.get('name', 'Unnamed')))
    if os.path.isabs(script):
        return script
    return os.path.join(project_folder, script)


def _run_part_script(script_path, context):
    if not os.path.isfile(script_path):
        raise RuntimeError('Part script was not found: {}'.format(script_path))

    module = _load_module(script_path, 'codex_part')
    if not hasattr(module, 'generate'):
        raise RuntimeError('Part script must define generate(context): {}'.format(script_path))
    module.generate(context)


def _run_assembly(project_folder, project, generated_parts, log_lines):
    log_lines.append('')
    log_lines.append('## Assembly')
    assembly_path = os.path.join(project_folder, 'assembly.py')
    if os.path.isfile(assembly_path):
        module = _load_module(assembly_path, 'codex_assembly')
        if not hasattr(module, 'assemble'):
            raise RuntimeError('assembly.py must define assemble(context).')
        context = {
            'project': project,
            'project_folder': project_folder,
            'parts': generated_parts,
            'log': log_lines,
            'helpers': helpers,
            'place_part': lambda name, translation_mm=None, rotation_deg=None: _place_generated_part(
                generated_parts,
                name,
                translation_mm,
                rotation_deg,
                log_lines
            ),
        }
        module.assemble(context)
        log_lines.append('- Ran `assembly.py`.')
        return

    _run_json_assembly(project_folder, generated_parts, log_lines)


def _run_json_assembly(project_folder, generated_parts, log_lines):
    assembly_path = os.path.join(project_folder, 'assemblies', 'main_assembly.json')
    if not os.path.isfile(assembly_path):
        log_lines.append('- No `assembly.py` or `assemblies/main_assembly.json` found; parts remain at origin.')
        return

    with open(assembly_path, 'r', encoding='utf-8') as assembly_file:
        assembly = json.load(assembly_file)

    placed = 0
    for spec in assembly.get('components') or []:
        if not isinstance(spec, dict):
            continue
        name = spec.get('name')
        generated = generated_parts.get(name)
        if not generated:
            log_lines.append('- Warning: assembly references `{}` but that part was not generated.'.format(name))
            continue
        if _place_generated_part(
            generated_parts,
            name,
            spec.get('translation') or [0, 0, 0],
            spec.get('rotation_deg') or [0, 0, 0],
            log_lines
        ):
            placed += 1
            log_lines.append('- Placed `{}` from JSON assembly.'.format(name))
            continue
        log_lines.append('- Warning: failed to place `{}` from JSON assembly.'.format(name))

    if placed == 0:
        log_lines.append('- No assembly components were placed.')


def _load_module(path, prefix):
    module_name = '{}_{}_{}'.format(prefix, abs(hash(path)), int(datetime.datetime.now().timestamp() * 1000))
    spec = importlib.util.spec_from_file_location(module_name, path)
    if not spec or not spec.loader:
        raise RuntimeError('Could not load script: {}'.format(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bodies_for_part(component, part_name):
    bodies = []
    try:
        for index in range(component.bRepBodies.count):
            body = component.bRepBodies.item(index)
            if _entity_part_name(body) == part_name or _body_name_matches(body, part_name):
                bodies.append(body)
        for index in range(component.occurrences.count):
            occurrence = component.occurrences.item(index)
            if occurrence and occurrence.component:
                bodies.extend(_bodies_for_part(occurrence.component, part_name))
    except Exception:
        pass
    return bodies


def _new_bodies_for_part(component, part_name, before_bodies):
    before_ids = set()
    for body in before_bodies:
        try:
            before_ids.add(body.entityToken)
        except Exception:
            before_ids.add(id(body))

    bodies = []
    try:
        for index in range(component.bRepBodies.count):
            body = component.bRepBodies.item(index)
            token = None
            try:
                token = body.entityToken
            except Exception:
                token = id(body)
            if token in before_ids:
                continue
            if _entity_part_name(body) == part_name or _body_name_matches(body, part_name):
                mark_generated_for_part(body, part_name)
                bodies.append(body)
        for index in range(component.occurrences.count):
            occurrence = component.occurrences.item(index)
            if occurrence and occurrence.component:
                bodies.extend(_new_bodies_for_part(occurrence.component, part_name, before_bodies))
    except Exception:
        pass
    return bodies


def _entity_part_name(entity):
    try:
        attr = entity.attributes.itemByName(ATTR_GROUP, ATTR_PART_NAME)
        return attr.value if attr else None
    except Exception:
        return None


def _body_name_matches(body, part_name):
    try:
        return hasattr(body, 'name') and body.name.startswith('codex_{}_'.format(part_name))
    except Exception:
        return False


def _generated_body_count(component):
    try:
        count = 0
        for index in range(component.bRepBodies.count):
            body = component.bRepBodies.item(index)
            if _has_generated_attr(body) or (hasattr(body, 'name') and body.name.startswith('codex_')):
                count += 1
        for index in range(component.occurrences.count):
            occurrence = component.occurrences.item(index)
            if occurrence and occurrence.component:
                count += _generated_body_count(occurrence.component)
        return count
    except Exception:
        return 0


def _place_generated_part(generated_parts, part_name, translation_mm=None, rotation_deg=None, log_lines=None):
    generated = generated_parts.get(part_name)
    if not generated:
        return False

    occurrence = generated.get('occurrence')
    if occurrence:
        helpers.place_occurrence(occurrence, translation_mm, rotation_deg)
        return True

    bodies = generated.get('bodies') or []
    if not bodies:
        return False

    if _is_identity_placement(translation_mm, rotation_deg):
        return True

    try:
        component = bodies[0].parentComponent
        collection = adsk.core.ObjectCollection.create()
        for body in bodies:
            collection.add(body)
        move_input = component.features.moveFeatures.createInput(
            collection,
            helpers.transform_mm(translation_mm, rotation_deg)
        )
        component.features.moveFeatures.add(move_input)
        return True
    except Exception:
        if log_lines is not None:
            log_lines.append('- Warning: failed to place `{}` bodies:\n  {}'.format(part_name, traceback.format_exc().strip()))
        return False


def _is_identity_placement(translation_mm=None, rotation_deg=None):
    values = list(translation_mm or [0, 0, 0]) + list(rotation_deg or [0, 0, 0])
    return all(abs(float(value)) < 1e-12 for value in values)


def _body_count(component):
    try:
        count = component.bRepBodies.count
        for index in range(component.occurrences.count):
            occurrence = component.occurrences.item(index)
            if occurrence and occurrence.component:
                count += _body_count(occurrence.component)
        return count
    except Exception:
        return 0


def _refresh_viewport(app, log_lines):
    try:
        viewport = app.activeViewport if app else None
        if viewport:
            viewport.refresh()
            viewport.fit()
            log_lines.append('- Viewport refreshed and fit to preview.')
    except Exception:
        log_lines.append('- Warning: viewport refresh failed:\n  {}'.format(traceback.format_exc().strip()))


def _new_log(project_folder, project):
    return [
        '# Codex CAD Workbench Run Log',
        '',
        '- Status: running',
        '- Timestamp: {}'.format(datetime.datetime.now().isoformat(timespec='seconds')),
        '- Project folder: `{}`'.format(project_folder),
        '- Project name: `{}`'.format(project.get('project_name') or project.get('name') or 'Untitled CAD Project'),
        '- Units: `{}`'.format(project.get('units', 'mm')),
        '',
        '## Preview Build',
    ]


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


def _relpath(path, folder):
    try:
        return os.path.relpath(path, folder).replace('\\', '/')
    except Exception:
        return path
