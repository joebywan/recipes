# Recipes

A personal collection of recipes, each written once as YAML and rendered to a Markdown page with an engineer's-format chart.

## Index

<!-- index:start -->
| Recipe | Notes |
| --- | --- |
| [Protein Banana-Oat Brownies](recipes/protein-banana-oat-brownies.md) | Fudgy banana-oat, blender only · 9 squares · ~110 cal / 7–8 g protein each |
| [Red Lentil Protein Brownies](recipes/red-lentil-protein-brownies.md) | Fudgy, flourless, high-protein · 9 squares · ~110 cal / 8 g protein each |
<!-- index:end -->

## Conventions

- Each recipe is written once as `recipes/<name>.yaml` (kebab-case). The `.md` page, the `.svg` chart and the index table above are generated from it, so edit the YAML and never the generated files.
- Render locally with `pip install pyyaml && python3 tools/render.py`. If you don't, the Render workflow does it on pull requests and on pushes to `main`, and commits the result.
- Metric weights first, with cup/spoon measures where they're genuinely easier.
- Oven temperatures are stated as fan (convection) unless noted otherwise.
- The chart is in the engineer's format (Cooking for Engineers style): ingredients down the left, and each step a box spanning the ingredients and earlier steps it combines, finishing with the dish on the right.
- In the YAML, `chart` lists those steps. Each step `uses` ingredient ids or earlier step ids, every ingredient is used exactly once, and the last step is the finished dish. Ingredients in a group marked `optional: true` stay out of the chart.
