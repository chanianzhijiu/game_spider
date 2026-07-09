# Story Tree Schema

Use this schema when turning scripts into an auditable branching narrative graph.

## Required Concepts

- `scene`: A narrative unit such as a Ren'Py `label`, Ink knot/stitch, KiriKiri `*label`, chapter, date, or location scene.
- `choice_group`: One player choice point containing multiple options.
- `branch`: One selectable option and its target.
- `effect`: State changes caused by a branch or scene, such as flags, route variables, affection changes, inventory, or jumps.
- `end`: A terminal or merge point: ending label, return, game over, chapter end, or route convergence.

## JSON Shape

```json
{
  "game": {
    "title": "",
    "source_url": "",
    "script_format": "renpy|ink|ks|mixed|unknown",
    "script_files": []
  },
  "nodes": [
    {
      "id": "scene:start",
      "type": "scene",
      "label": "start",
      "file": "game/script.rpy",
      "line": 1,
      "summary": ""
    },
    {
      "id": "choice:start:1",
      "type": "choice_group",
      "scene": "scene:start",
      "file": "game/script.rpy",
      "line": 42,
      "choices": [
        {
          "id": "branch:start:1:a",
          "text": "",
          "target": "scene:next",
          "condition": null,
          "effect": []
        }
      ]
    },
    {
      "id": "end:normal",
      "type": "end",
      "label": "normal_end",
      "summary": ""
    }
  ],
  "edges": [
    {
      "from": "scene:start",
      "to": "choice:start:1",
      "condition": null,
      "effect": []
    }
  ],
  "warnings": []
}
```

## Ren'Py Mapping

Parse these constructs:

- `label name:` -> `scene`
- `menu:` -> `choice_group`
- menu option `"Text":` -> `branch`
- `jump label` -> edge to target scene
- `call label` -> edge with call effect
- `return` -> `end` or return edge
- `if/elif/else` -> conditional edge or branch condition
- `$ var = ...`, `$ var += ...`, `default var = ...`, `python:` -> `effect`

Ignore or down-rank engine files under `renpy/common/` unless the user asks for engine analysis.

## Ink Mapping

Parse these constructs:

- `== knot ==` -> scene
- `= stitch` -> scene inside knot
- `* choice` and `+ sticky choice` -> branches inside a choice group
- `-> target` -> edge
- `VAR`, `~ assignment` -> effect
- `{ condition }` -> condition
- `-> END` or `-> DONE` -> end

## KiriKiri / KS Mapping

Parse these constructs:

- `*label` -> scene
- `[link target=*label]... [endlink]` -> branch
- `[jump target=*label]` -> edge
- `[if exp="..."]` / `[elsif]` / `[else]` / `[endif]` -> condition
- `[eval exp="..."]` -> effect
- `[return]` -> end or return edge

## Output Rules

- Preserve source file paths and line numbers whenever possible.
- Summarize scenes instead of copying long script text.
- Include warnings for dynamic Python, computed jumps, missing labels, or compiled-only scripts.
- If only `.rpyc` exists, report that the script is compiled and ask before decompiling.

