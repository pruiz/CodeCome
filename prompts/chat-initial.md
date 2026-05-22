# Chat Mode: Initial Prompt

You are starting an interactive chat session with the user.

## Startup instructions

1. Read `codecome.yml` to learn the project name and configuration.
2. List the contents of `itemdb/findings/` (all status subdirectories) to get a quick overview of the current finding statuses.
3. Respond with a brief greeting that includes:
   - The project name (from `codecome.yml`).
   - A one-line summary of finding counts by status (e.g., "2 PENDING, 1 CONFIRMED, 1 EXPLOITED, 1 REJECTED").
   - A note that you're ready for instructions.

## What NOT to do at startup

- Do NOT read `AGENTS.md`, reconnaissance notes (`itemdb/notes/*`), skills, templates, or source code.
- Do NOT perform reconnaissance or any analysis.
- Do NOT read large files or directory trees.
- Keep the startup response under 5 lines.

## After startup

Wait for the user's instructions.  Read files only when the user asks or when a specific task requires them.  If a task needs context from reconnaissance notes, skills, or source code, read those on demand.
