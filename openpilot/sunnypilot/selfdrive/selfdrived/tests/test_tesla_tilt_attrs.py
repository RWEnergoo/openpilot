"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Our Tesla tilt gestures live inside SelfdriveD and read attributes that upstream owns. An
upstream merge can delete one of those without any conflict, and nothing catches it: ruff does
not look at attributes and `ty check` passes on the broken code. It then raises AttributeError
the first time the gesture completes and takes selfdrived down mid-drive.

That is exactly what happened on 2026-11-03: upstream removed SelfdriveD.experimental_mode
along with its own Experimental Mode handling, and switching Experimental Mode by tilt crashed
the device. This test reads the source and fails if any self.<attr> our methods read is never
assigned in the class.
"""
import ast
import pathlib

SELFDRIVED = pathlib.Path(__file__).parents[4] / "selfdrive" / "selfdrived" / "selfdrived.py"

# the methods we own and maintain in that upstream file
OUR_METHODS = ("update_tesla_tilt_holds",)


def _class_node(tree, name):
  for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == name:
      return node
  raise AssertionError(f"{name} not found in {SELFDRIVED}")


class TestTeslaTiltAttributes:
  def test_our_methods_only_read_attributes_that_exist(self):
    tree = ast.parse(SELFDRIVED.read_text(encoding="utf-8"))
    cls = _class_node(tree, "SelfdriveD")

    assigned = {t.attr for node in ast.walk(cls) if isinstance(node, ast.Assign)
                for t in node.targets if isinstance(t, ast.Attribute)}
    assigned |= {node.target.attr for node in ast.walk(cls) if isinstance(node, ast.AnnAssign)
                 and isinstance(node.target, ast.Attribute)}
    assigned |= {node.target.attr for node in ast.walk(cls) if isinstance(node, ast.AugAssign)
                 and isinstance(node.target, ast.Attribute)}
    defined = {node.name for node in cls.body if isinstance(node, ast.FunctionDef)}

    for method_name in OUR_METHODS:
      method = next((n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name), None)
      assert method is not None, f"{method_name} is gone from SelfdriveD - did an upstream merge drop it?"

      read = {n.attr for n in ast.walk(method) if isinstance(n, ast.Attribute)
              and isinstance(n.value, ast.Name) and n.value.id == "self"}
      missing = read - assigned - defined
      assert not missing, (f"{method_name} reads self.{', self.'.join(sorted(missing))} but nothing in " +
                           "SelfdriveD assigns it. An upstream merge probably removed it.")
