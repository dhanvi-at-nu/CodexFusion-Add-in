# Project format

Each CAD project lives in its own folder and usually contains:

- `project.json`
- `assembly.py`
- `parts/*.py`
- `assemblies/*.json` when the project needs assembly metadata

The preview runner reads `project.json`, loads the enabled part scripts, and then calls the project `assembly.py` when assembly placement is needed.

Keep coordinates in millimeters in the project files. Fusion's API often works in centimeters internally, so the runtime handles the unit conversion.
