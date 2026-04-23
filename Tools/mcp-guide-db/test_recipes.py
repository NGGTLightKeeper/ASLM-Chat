# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Quick smoke test for all recipes across all guides."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import db

recipes = db._get_all_recipes()
print(f"Total recipes: {len(recipes)}")
for r in recipes:
    print(f"  [{r.owner_guide}] {r.slug}")

print()
g = db._resolve_guide("mcp-sandbox")
core = db._assemble_guide_content(g, mode="core")
core_r = db._assemble_guide_content(g, mode="core+recipes")

print(f"core mode: {len(core)} chars")
print(f"core+recipes mode: {len(core_r)} chars")
print(f"'Local Snippets' in core: {'Local Snippets' in core}")       # should be False (no snippets yet)
print(f"'Available Recipes' in core: {'Available Recipes' in core}") # should be True
print(f"'## Recipes' in core+recipes: {'## Recipes' in core_r}")    # should be True

print("\n=== OK ===")
