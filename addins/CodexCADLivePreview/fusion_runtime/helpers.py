import math

import adsk.core


def mm(value):
    return float(value) / 10.0


def deg(value):
    return float(value) * math.pi / 180.0


def transform_mm(translation_mm=None, rotation_deg=None):
    translation_mm = translation_mm or [0, 0, 0]
    rotation_deg = rotation_deg or [0, 0, 0]

    tx, ty, tz = [float(value) for value in translation_mm]
    rx, ry, rz = [deg(value) for value in rotation_deg]

    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

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
    transform.translation = adsk.core.Vector3D.create(mm(tx), mm(ty), mm(tz))
    return transform


def place_occurrence(occurrence, translation_mm=None, rotation_deg=None):
    occurrence.transform = transform_mm(translation_mm, rotation_deg)
    return occurrence
