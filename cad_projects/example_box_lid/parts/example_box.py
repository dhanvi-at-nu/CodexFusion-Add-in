import adsk.core
import adsk.fusion


def _mm(value):
    # Fusion's API uses centimeters internally for model-space distances.
    return float(value) / 10.0


def generate(context):
    generated_component = context['generated_component']
    part = context['part']
    params = part.get('parameters', {})
    mark_generated = context.get('mark_generated')
    mark_generated_for_part = context.get('mark_generated_for_part')
    part_name = part.get('name', 'Example_Box')

    width_mm = params.get('width_mm', 80)
    depth_mm = params.get('depth_mm', 50)
    height_mm = params.get('height_mm', 20)

    # Keep v1 simple: generate directly in the provided component. In "Part design"
    # documents this may be the root component (only one component allowed).
    sketch = generated_component.sketches.add(generated_component.xYConstructionPlane)
    sketch.name = 'codex_{}_profile'.format(part_name)
    if callable(mark_generated):
        mark_generated(sketch)
    if callable(mark_generated_for_part):
        mark_generated_for_part(sketch, part_name)

    corner_a = adsk.core.Point3D.create(0, 0, 0)
    corner_b = adsk.core.Point3D.create(_mm(width_mm), _mm(depth_mm), 0)
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(corner_a, corner_b)

    if sketch.profiles.count < 1:
        raise RuntimeError('Example box sketch did not create a closed profile.')

    profile = sketch.profiles.item(0)
    distance = adsk.core.ValueInput.createByReal(_mm(height_mm))
    extrudes = generated_component.features.extrudeFeatures
    extrude_input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    extrude_input.setDistanceExtent(False, distance)
    extrude = extrudes.add(extrude_input)

    if extrude.bodies.count > 0:
        body = extrude.bodies.item(0)
        body.name = 'codex_{}_body'.format(part_name)
        if callable(mark_generated):
            mark_generated(body)
        if callable(mark_generated_for_part):
            mark_generated_for_part(body, part_name)

    context['log'].append(
        '- Box dimensions: {} mm x {} mm x {} mm.'.format(width_mm, depth_mm, height_mm)
    )
