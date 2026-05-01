# Codex CAD Workbench

Codex CAD Workbench is a Fusion 360 add-in for a live CAD coding loop: Codex edits Fusion API scripts, then Fusion rebuilds tagged preview geometry so you can inspect the result and iterate.

## Workflow

1. Ask Codex to create or modify part and assembly scripts.
2. In Fusion, open the **Codex CAD Workbench** command.
3. Click **Load project.json**.
4. Click **Run preview**.
5. Inspect the generated bodies in the Fusion viewport and browser.
6. Ask Codex for the next change, then click **Run preview** again.

You do not need to close the workbench window between preview runs. Reload the add-in only after changing the add-in/runtime code itself.

Generated preview bodies and sketches are disposable. Manual edits are fine for exploration, but the next **Run preview** deletes tagged preview geometry and rebuilds it from the scripts.

## Project Layout

```text
example_project/
  project.json
  parts/
    example_box.py
    example_lid.py
  assembly.py
  reviews/
    run_log.md
```

`project.json` lists the enabled part scripts:

```json
{
  "project_name": "example_project",
  "units": "mm",
  "global_parameters": {
    "wall_thickness": 2.5,
    "clearance": 0.5
  },
  "parts": [
    {
      "name": "Example_Box",
      "script": "parts/example_box.py",
      "enabled": true
    },
    {
      "name": "Example_Lid",
      "script": "parts/example_lid.py",
      "enabled": true
    }
  ]
}
```

Each part script defines:

```python
def generate(context):
    component = context['component']
    helpers = context['helpers']
    ...
```

The runtime provides `context['component']`, `context['generated_component']`, `context['project']`, `context['part']`, `context['global_parameters']`, `context['log']`, `context['helpers']`, `context['mark_generated']`, and `context['mark_generated_for_part']`.

## Assembly Script

Prefer `assembly.py` for placement logic:

```python
def assemble(context):
    helpers = context['helpers']
    parts = context['parts']

    helpers.place_occurrence(
        parts['Example_Lid']['occurrence'],
        translation_mm=[0, 0, 40],
        rotation_deg=[25, 0, 0],
    )
```

The older `assemblies/main_assembly.json` placement file is still supported as a fallback when no `assembly.py` exists.

## Runtime Files

- `Codex_CAD_Workbench.py` - Fusion toolbar command and dialog.
- `fusion_runtime/runner.py` - clears and rebuilds tagged preview geometry, reloads scripts every run, writes logs.
- `fusion_runtime/helpers.py` - small Fusion API helpers for millimeter transforms and occurrence placement.
- `example_project/assembly.py` - example assembly placement script.

Logs are written to `example_project/reviews/run_log.md`.
