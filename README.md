# Codex Fusion Add-in

This repo is a clean starter for the Codex Fusion 360 add-in workflow.

It contains:

- `addins/CodexCADLivePreview/` for the Fusion add-in and live preview UI
- `cad_projects/example_box_lid/` for a generic example project
- `docs/` for setup and workflow notes

The repo intentionally does not include the UV-384 clamshell project. The idea is to share the toolchain, not the private part design.

## What to open in Fusion

Use `addins/CodexCADLivePreview` as the add-in folder inside Fusion, then point the workbench at `cad_projects/example_box_lid`.

## Typical loop

1. Open Fusion.
2. Run the Codex CAD Workbench add-in.
3. Load the example project.
4. Click `Run Preview`.
5. Inspect the geometry and edit the project scripts.
6. When ready, click `Export STL`.

## Repo layout

- `addins/CodexCADLivePreview/Codex_CAD_Workbench.py` is the Fusion palette/workbench entry point.
- `addins/CodexCADLivePreview/fusion_runtime/` contains the preview runner helpers.
- `cad_projects/example_box_lid/project.json` is the project manifest.
- `cad_projects/example_box_lid/parts/` contains the part scripts.
- `docs/prompt_template_for_copilot.md` gives a copy-paste prompt format for fresh chat sessions.
