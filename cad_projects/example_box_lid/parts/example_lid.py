import adsk.core
import adsk.fusion


def _mm(value):
    # Fusion's API uses centimeters internally for model-space distances.
    return float(value) / 10.0


def generate(context):
    component = context['generated_component']
    part = context['part']
    globals_ = context.get('global_parameters', {}) or {}
    mark_generated = context.get('mark_generated')
    mark_generated_for_part = context.get('mark_generated_for_part')

    params = part.get('parameters', {})
    width_mm = params.get('width_mm', 80)
    depth_mm = params.get('depth_mm', 50)
    lid_height_mm = params.get('height_mm', 10)

    wall_thickness_mm = float(globals_.get('wall_thickness', 2.5))
    clearance_mm = float(globals_.get('clearance', 0.5))

    part_name = part.get('name', 'Example_Lid')

    # Outer lid body.
    outer_sketch = component.sketches.add(component.xYConstructionPlane)
    outer_sketch.name = 'codex_{}_outer_profile'.format(part_name)
    if callable(mark_generated):
        mark_generated(outer_sketch)
    if callable(mark_generated_for_part):
        mark_generated_for_part(outer_sketch, part_name)

    corner_a = adsk.core.Point3D.create(0, 0, 0)
    corner_b = adsk.core.Point3D.create(_mm(width_mm), _mm(depth_mm), 0)
    outer_sketch.sketchCurves.sketchLines.addTwoPointRectangle(corner_a, corner_b)

    if outer_sketch.profiles.count < 1:
        raise RuntimeError('Lid outer sketch did not create a closed profile.')

    outer_profile = outer_sketch.profiles.item(0)
    extrudes = component.features.extrudeFeatures
    outer_height = adsk.core.ValueInput.createByReal(_mm(lid_height_mm))
    outer_input = extrudes.createInput(outer_profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    outer_input.setDistanceExtent(False, outer_height)
    outer_extrude = extrudes.add(outer_input)

    if outer_extrude.bodies.count < 1:
        raise RuntimeError('Lid extrude did not create a body.')

    lid_body = outer_extrude.bodies.item(0)
    lid_body.name = 'codex_{}_body'.format(part_name)
    if callable(mark_generated):
        mark_generated(lid_body)
    if callable(mark_generated_for_part):
        mark_generated_for_part(lid_body, part_name)

    # Recess cut: offset rectangle inward by wall_thickness+clearance, cut most of the height.
    offset_mm = wall_thickness_mm + clearance_mm
    inner_sketch = component.sketches.add(component.xYConstructionPlane)
    inner_sketch.name = 'codex_{}_inner_profile'.format(part_name)
    if callable(mark_generated):
        mark_generated(inner_sketch)
    if callable(mark_generated_for_part):
        mark_generated_for_part(inner_sketch, part_name)

    inner_a = adsk.core.Point3D.create(_mm(offset_mm), _mm(offset_mm), 0)
    inner_b = adsk.core.Point3D.create(_mm(width_mm - offset_mm), _mm(depth_mm - offset_mm), 0)
    inner_sketch.sketchCurves.sketchLines.addTwoPointRectangle(inner_a, inner_b)

    if inner_sketch.profiles.count < 1:
        raise RuntimeError('Lid inner sketch did not create a closed profile.')

    inner_profile = inner_sketch.profiles.item(0)
    cut_depth_mm = max(0.0, lid_height_mm - wall_thickness_mm)
    cut_depth = adsk.core.ValueInput.createByReal(_mm(cut_depth_mm))
    cut_input = extrudes.createInput(inner_profile, adsk.fusion.FeatureOperations.CutFeatureOperation)
    cut_input.setDistanceExtent(False, cut_depth)
    extrudes.add(cut_input)

    context['log'].append(
        '- Lid: {} mm x {} mm x {} mm, wall {} mm, clearance {} mm.'.format(
            width_mm, depth_mm, lid_height_mm, wall_thickness_mm, clearance_mm
        )
    )
