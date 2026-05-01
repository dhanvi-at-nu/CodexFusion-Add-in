# Workflow for Codex or Claude Code

This repo is set up for a simple feedback loop:

1. The model edits the project scripts.
2. You run the Fusion preview from the add-in.
3. You inspect the model visually.
4. We iterate until the part looks right.

Recommended division of labor:

- The model edits `cad_projects/<project>/project.json`, `parts/*.py`, and `assembly.py`.
- You handle Fusion preview, export, and physical print checks.
- The add-in itself should stay stable and change only when the workflow needs it.

Keep projects small and explicit. Use one project folder per design, and keep generated files, STL exports, and review logs out of version control.

For a new chat instance, use [prompt_template_for_copilot.md](prompt_template_for_copilot.md) as the model briefing template.
