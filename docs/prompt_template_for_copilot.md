# Prompt Template For Fusion CAD Work

Use this when starting a new chat with Copilot, ChatGPT, or Codex for a Fusion add-in project.

The goal is to give the model enough context to write project scripts without needing to inspect the add-in source first.

## What The Model Needs

Provide these items up front:

- The project goal in one sentence
- The part type and function
- The important dimensions
- Units, usually `mm`
- Material and print process, if relevant
- Clearances or tolerances
- Which parts are fixed, sliding, snapped, or threaded
- What the preview should show first
- What must be avoided
- The project folder layout you want the model to follow

## Recommended Prompt Structure

Copy this shape into a new chat and fill in the blanks.

```text
You are helping me author a Fusion 360 CAD project for the Codex CAD add-in.

Project goal:
Create a <part or assembly> that <main function>.

Context:
- The add-in runs Codex-authored Fusion API scripts from a project folder.
- I will load the project in Fusion, click Run Preview, inspect the geometry, and iterate.
- Do not rely on the add-in code itself. Work only from the project description I provide here.
- Generate the project in the same folder structure used by the repo example.

Design requirements:
- Units: mm
- Material: <material>
- Print process: <printer or process>
- Main dimensions:
  - <dimension 1>
  - <dimension 2>
  - <dimension 3>
- Tolerances / clearances:
  - <clearance values>
- Functional constraints:
  - <fit, access, snap, cable, lid, hole, or orientation constraints>

Part structure:
- Part 1: <name, role, key size>
- Part 2: <name, role, key size>
- Assembly behavior: <how parts should sit relative to each other>

Project structure:
- `project.json` defines the project name, units, global parameters, and the list of parts.
- `assembly.py` positions the parts when more than one body or component needs placement.
- `parts/*.py` contains one script per part.
- `assemblies/*.json` is optional metadata for assembly placement or preview settings.

Example folder shape:
```text
cad_projects/<project_name>/
  project.json
  assembly.py
  parts/
    part_1.py
    part_2.py
  assemblies/
    main_assembly.json
  reviews/
    run_log.md
```

Example `project.json` shape:
```json
{
  "project_name": "example_name",
  "units": "mm",
  "global_parameters": {
    "clearance_mm": 0.4,
    "wall_thickness_mm": 2.5
  },
  "parts": [
    {
      "name": "Main_Body",
      "script": "parts/main_body.py",
      "enabled": true,
      "parameters": {
        "width_mm": 120,
        "depth_mm": 85,
        "height_mm": 20
      }
    },
    {
      "name": "Top_Cover",
      "script": "parts/top_cover.py",
      "enabled": true,
      "parameters": {
        "width_mm": 120,
        "depth_mm": 85,
        "height_mm": 5
      }
    }
  ]
}
```

What I want you to generate:
- First, write or update `project.json` so the project has a clear part list and parameters.
- Then write the part scripts under `parts/`.
- Then update `assembly.py` only if part placement is needed.
- Update the project scripts for the part geometry.
- Keep the project organized for the Fusion add-in.
- Prefer stable, easy-to-preview geometry over clever but fragile geometry.
- If anything is ambiguous, call it out before making assumptions.

Output format:
- Briefly summarize the plan.
- Then provide the file-by-file changes or code, starting with `project.json`.
- Mention any assumptions that were necessary.
```

## Example Prompt For A Fresh Chat

```text
You are helping me author a Fusion 360 CAD project for the Codex CAD add-in.

Project goal:
Create a removable box-lid style carrier for a 384-well plate and side-mounted battery chamber.

Context:
- The add-in runs Codex-authored Fusion API scripts from a project folder.
- I will load the project in Fusion, click Run Preview, inspect the geometry, and iterate.
- Do not rely on the add-in code itself. Work only from the project description I provide here.

Design requirements:
- Units: mm
- Material: Tough 2000 or similar resin
- Main dimensions:
  - Plate footprint: 127.76 x 85.48 x 14.4
  - Plate fit clearance: 0.4 mm
  - Battery chamber length: 80 to 82 mm
  - PCB hole diameter: 4 mm
  - PCB hole center offset from edge: 2.5 mm
- Functional constraints:
  - Plate should slide or snap in snugly
  - Battery chamber should be open on one side for access
  - Lid-like form factor
  - Keep LED space above the plate
  - Minimize support-heavy geometry

Part structure:
- Part 1: main carrier body
- Part 2: optional lid or top frame if needed
- Assembly behavior: one previewable part if possible, with optional placement logic

What I want you to generate:
- Update the project scripts for the part geometry.
- Keep the project organized for the Fusion add-in.
- Prefer stable, easy-to-preview geometry over clever but fragile geometry.
- If anything is ambiguous, call it out before making assumptions.
```

## Good Habits

- Give exact dimensions instead of saying "roughly" whenever you can.
- Say which measurements are fixed and which can move.
- Mention the intended preview orientation if printability matters.
- Include tolerances explicitly.
- Ask for one change at a time when the model is close to the target.

## Good Follow-Up Prompts

Use short, specific iteration prompts after the first preview.

```text
Keep the current geometry, but widen the battery chamber by 1 mm and preserve the plate fit.
```

```text
Keep the same layout, but remove any decorative or nonfunctional ribs under the LED area.
```

```text
Keep the preview as a single part, and only adjust the plate snap fit to be 0.4 mm looser.
```

```text
Do not change the outer envelope. Only fix the PCB mount hole positions and export-ready geometry.
```

## What To Avoid In Prompts

- Vague instructions like "make it better"
- Mixed units
- Missing tolerances for parts that have to fit together
- Asking for code changes without saying whether the model should touch the add-in runtime or only the project folder
- Re-describing the same dimension in conflicting ways

## Suggested Workflow

1. Start a new chat.
2. Paste the template.
3. Fill in the dimensions and constraints.
4. Ask for the project scripts only.
5. Run `Run Preview` in Fusion.
6. Report the visual differences back into the chat.
7. Repeat until the part is ready.
