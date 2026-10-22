import tempfile
import unittest
from pathlib import Path

import render

RECIPE = """
title: Toast
ingredients:
  - group: Main
    items:
      - {id: bread, name: Bread, amount: 1 slice}
      - {id: butter, name: Butter, amount: 5 g}
  - group: Optional
    optional: true
    items:
      - {id: jam, name: Jam, amount: 1 tsp}
chart:
  - {id: toast, uses: [bread], do: Toast until golden}
  - {id: spread, uses: [toast, butter], do: Spread}
"""

README = "# Recipes\n\n<!-- index:start -->\nold\n<!-- index:end -->\n\nMore.\n"


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "recipes").mkdir()
        (self.dir / "README.md").write_text(README)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text):
        path = self.dir / "recipes" / "toast.yaml"
        path.write_text(text)
        return path

    def render(self, text=RECIPE):
        self.write(text)
        return render.outputs(self.dir / "recipes", self.dir / "README.md")

    def test_layout_reads_as_a_tree(self):
        r = render.load(self.write(RECIPE))
        rows, span, col, parent = render.layout(r)
        self.assertEqual(rows, ["bread", "butter"])
        self.assertEqual(span["spread"], (0, 1))
        self.assertEqual(col, {"bread": 0, "toast": 1, "butter": 0, "spread": 2})
        self.assertEqual(parent["butter"], "spread")

    def test_outputs(self):
        files = self.render()
        md = files[self.dir / "recipes" / "toast.md"]
        svg = files[self.dir / "recipes" / "toast.svg"]
        readme = files[self.dir / "README.md"]
        self.assertIn("![Engineer's chart for Toast](toast.svg)", md)
        self.assertIn("| Jam | 1 tsp |", md)
        self.assertIn(">Toast until golden</text>", svg)
        self.assertNotIn(">Jam</text>", svg)
        self.assertIn("| [Toast](recipes/toast.md) |", readme)
        self.assertTrue(readme.endswith("<!-- index:end -->\n\nMore.\n"))
        self.assertNotIn("old", readme)

    def test_brownies_render(self):
        files = render.outputs()
        self.assertTrue(any(p.suffix == ".svg" for p in files))

    def assertRecipeError(self, text, message):
        with self.assertRaisesRegex(render.RecipeError, message):
            self.render(text)

    def test_unknown_reference(self):
        self.assertRecipeError(RECIPE.replace("[toast, butter]", "[toast, marg]"), "'marg'")

    def test_ingredient_used_twice(self):
        self.assertRecipeError(RECIPE.replace("[toast, butter]", "[toast, bread, butter]"), "used by both")

    def test_unused_ingredient(self):
        self.assertRecipeError(RECIPE.replace("[toast, butter]", "[toast]"), "not in the chart")

    def test_two_final_steps(self):
        extra = RECIPE.replace("[toast, butter]", "[toast]") + "  - {id: melt, uses: [butter], do: Melt}\n"
        self.assertRecipeError(extra, "one final step")

    def test_xml_is_escaped(self):
        files = self.render(RECIPE.replace("do: Spread", "do: Spread <thin> & even"))
        self.assertIn("Spread &lt;thin&gt; &amp; even", files[self.dir / "recipes" / "toast.svg"])


if __name__ == "__main__":
    unittest.main()
