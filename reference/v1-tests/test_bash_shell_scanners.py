"""bash_shell stack: its contract and coverage scanners, without the bash toolchain.

The real gates (`ios-pipeline stack test bash_shell`) need bats and shellcheck; these pin down the
two pure-Python line scanners those gates rely on, so a change to either is caught anywhere.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

from helpers import PIPELINE

STACK = PIPELINE / "stacks" / "bash_shell"


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"bash_shell_{name}", STACK / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


coverage = load("coverage")
contract = load("contract")

# Common constructs; the lines bash 5's xtrace reports for each were checked against a real trace
# when the scanner was written (see coverage.py's docstring).
CORPUS = """\
# comment
f() {
  local a=1 b
  if [[ $a -eq 1 ]]; then
    b=2
  elif [[ $a -eq 3 ]]; then
    b=3
  else
    b=4
  fi
  for x in 1 2; do
    : "$x"
  done
  case "$b" in
    2)
      echo two
      ;;
    3) echo three ;;
    *) ;;
  esac
  echo one \\
    two
  cat <<EOT
heredoc $a
EOT
  local arr=(
    x
  )
  echo "multi
line string"
  v="$(
    echo inner
  )"
  return 0
}
g() { echo inline; }
function h {
  echo h
}
"""


class CommandSpansTest(unittest.TestCase):
    def test_spans_cover_each_command_once(self) -> None:
        self.assertEqual(coverage.commands(CORPUS.splitlines()), [
            (3, 3), (4, 4), (5, 5), (6, 6), (7, 7), (9, 9), (11, 11), (12, 12), (14, 14),
            (16, 16), (18, 18), (21, 22), (23, 25), (26, 28), (29, 30), (31, 33), (34, 34),
            (36, 36), (38, 38),
        ])

    def test_keyword_lines_and_headers_are_not_code(self) -> None:
        firsts = {first for first, _ in coverage.commands(CORPUS.splitlines())}
        # f() {, else, fi, done, `2)`, ;;, `*) ;;`, esac, }, function h {, }
        for line in (2, 8, 10, 13, 15, 17, 19, 20, 35, 37, 39):
            self.assertNotIn(line, firsts)

    def test_uncovered_counts_any_traced_line_of_a_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "lib").mkdir()
            source = root / "lib" / "x.sh"
            source.write_text(CORPUS)
            never = root / "lib" / "never.sh"
            never.write_text("echo never\n")
            # Everything ran except the elif/else branches, case 3 and h's body; the $( … ) was
            # traced at its last line (33), as bash reports it. Paths come unnormalized, as a test
            # that sources "$BATS_TEST_DIRNAME/../../lib/x.sh" leaves them in BASH_SOURCE.
            ran = [3, 4, 5, 11, 12, 14, 16, 21, 23, 26, 29, 33, 34, 36]
            data = root / "lines.txt"
            data.write_text("".join(f"tests/x/../../lib/x.sh:{n}\n" for n in ran))
            (root / "tests" / "x").mkdir(parents=True)
            result, missing = coverage.uncovered(root, [source, never], data)
            self.assertEqual(result, {source: [6, 7, 9, 18, 38]})
            self.assertEqual(missing, [never])


class ContractTest(unittest.TestCase):
    def test_usage_lines_and_constants_without_private_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "counter.sh"
            path.write_text(
                "# usage: counter::add <n>\n"
                "#   -> stdout: the new count\n"
                "counter::add() {\n"
                "  echo \"not implemented\" >&2\n"
                "  return 70\n"
                "}\n"
                "\n"
                "counter::bare() { return 70; }\n"
                "_counter::helper() { :; }\n"
                "readonly COUNTER_E_BAD=2 # bad input\n"
                "declare -r COUNTER_NAME=\"a # b\"\n"
                "readonly _COUNTER_PRIVATE=1\n")
            self.assertEqual(contract.extract(path), [
                "counter::add: counter::add <n> -> stdout: the new count",
                "counter::bare: (no usage)",
                "COUNTER_E_BAD=2",
                "COUNTER_NAME=\"a # b\"",
            ])


if __name__ == "__main__":
    unittest.main()
