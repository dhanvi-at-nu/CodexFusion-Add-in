def assemble(context):
    log = context['log']
    place_part = context['place_part']

    if place_part('Example_Box', translation_mm=[0, 0, 0], rotation_deg=[0, 0, 0]):
        log.append('- assembly.py placed `Example_Box` at the origin.')

    if place_part('Example_Lid', translation_mm=[0, 0, 24], rotation_deg=[0, 0, 0]):
        log.append('- assembly.py placed `Example_Lid` flat above the box.')
