"""Targeted tests for the parser's Foundation-compatible behavior and helpers.

The conformance vectors cover the spec. These cases pin the JSON-layer decisions
that Python's json module needs help with (see the module docstring of
heurica_tap.parse), and the public helpers around parse().
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from heurica_tap import normalize_tool_name, parse  # noqa: E402
from heurica_tap.aliases import ALIASES  # noqa: E402

FENCE = "```"


def fenced(body):
    return "Working.\n" + FENCE + "json\n" + body + "\n" + FENCE


class ParseTests(unittest.TestCase):
    def test_ok_result_shape(self):
        result = parse(fenced('{"say": "Hi.", "actions": [], "done": true}'))
        self.assertTrue(result.ok)
        self.assertEqual(result.as_dict()["reply"]["thought"], "Working.")
        self.assertEqual(result.reply.say, "Hi.")
        self.assertTrue(result.reply.done)

    def test_error_result_shape(self):
        result = parse("nothing to see here")
        self.assertFalse(result.ok)
        self.assertEqual(result.as_dict(), {"ok": False, "error": {"kind": "no_json"}})

    def test_never_raises_on_non_string(self):
        self.assertEqual(parse(None).error.kind, "no_json")

    def test_duplicate_keys_keep_the_first_value(self):
        reply = parse(fenced('{"say": "a", "say": "b", "actions": []}')).reply
        self.assertEqual(reply.say, "a")

    def test_nan_and_infinity_are_rejected(self):
        result = parse(fenced('{"say": "a", "milestone": NaN, "actions": []}'))
        self.assertEqual(result.error.kind, "invalid_json")

    def test_lone_surrogate_escape_is_rejected(self):
        result = parse(fenced('{"say": "a\\ud800b", "actions": []}'))
        self.assertEqual(result.error.kind, "invalid_json")

    def test_surrogate_pair_escape_is_decoded(self):
        reply = parse(fenced('{"say": "\\ud83d\\ude00", "actions": []}')).reply
        self.assertEqual(reply.say, "\U0001F600")

    def test_big_integer_becomes_a_double(self):
        reply = parse(fenced('{"say": "x", "actions": [{"tool": "t", "args": {"n": 12345678901234567890}}]}')).reply
        self.assertEqual(reply.actions[0].args["n"], 1.2345678901234567e19)

    def test_whole_numbers_are_ints_and_compare_by_value(self):
        reply = parse(fenced('{"say": "x", "milestone": 2.0, "actions": []}')).reply
        self.assertIsInstance(reply.milestone, int)
        self.assertEqual(reply.milestone, 2)

    def test_milestone_rounds_half_away_from_zero(self):
        self.assertEqual(parse(fenced('{"say": "x", "milestone": 2.5}')).reply.milestone, 3)
        self.assertEqual(parse(fenced('{"say": "x", "milestone": -2.5}')).reply.milestone, -3)

    def test_milestone_accepts_booleans_and_padded_strings(self):
        self.assertEqual(parse(fenced('{"say": "x", "milestone": true}')).reply.milestone, 1)
        self.assertEqual(parse(fenced('{"say": "x", "milestone": " 3 "}')).reply.milestone, 3)

    def test_number_say_becomes_text(self):
        self.assertEqual(parse(fenced('{"say": 2.0}')).reply.say, "2")
        self.assertEqual(parse(fenced('{"say": 1.5}')).reply.say, "1.5")
        self.assertEqual(parse(fenced('{"say": 1e15}')).reply.say, "1000000000000000.0")

    def test_crlf_inside_a_string_is_escaped(self):
        raw = fenced('{"say": "a", "actions": [{"tool": "write_file", "args": {"path": "p", "content": "x\r\ny"}}]}')
        args = parse(raw).reply.actions[0].args
        self.assertEqual(args["content"], "x\r\ny")

    def test_content_is_not_repaired(self):
        raw = fenced('{"say": "a", "actions": [{"tool": "write_file", "args": {"path": "p", "content": "True // not a comment, ok,}"}}]}')
        self.assertEqual(parse(raw).reply.actions[0].args["content"], "True // not a comment, ok,}")

    def test_repairs_run_only_when_strict_read_fails(self):
        raw = fenced('{"say": "a", "actions": [{"tool": "shell", "args": {"command": "ls"}},],}')
        self.assertEqual(parse(raw).reply.actions[0].tool, "shell")

    def test_completion_action_becomes_done(self):
        reply = parse(fenced('{"actions": [{"tool": "attempt_completion", "args": {"result": "Fixed."}}]}')).reply
        self.assertTrue(reply.done)
        self.assertTrue(reply.explicit_done)
        self.assertEqual(reply.say, "Fixed.")
        self.assertEqual(reply.actions, [])

    def test_prose_answer_after_the_block_replaces_a_pointer(self):
        prose = "The config sets the port to 8080, and TLS is enabled for every route."
        reply = parse(fenced('{"say": "See below.", "actions": []}') + "\n\n" + prose).reply
        self.assertEqual(reply.say, prose)
        self.assertTrue(reply.done)

    def test_grapheme_count_is_used_for_the_forty_character_rule(self):
        combining = "é" * 40  # 40 characters, 40 graphemes
        reply = parse(fenced('{"say": "See below.", "actions": []}') + "\n\n" + combining + "x").reply
        self.assertEqual(reply.say, combining + "x")  # 41 graphemes: replaces the pointer

    def test_only_the_first_valid_block_runs(self):
        raw = fenced('{"say": "one", "actions": []}') + "\n" + fenced('{"say": "two", "actions": []}')
        reply = parse(raw).reply
        self.assertEqual(reply.say, "one")
        self.assertEqual(reply.ignored_blocks, 1)

    def test_reply_shape_key_list_is_the_spec_list(self):
        self.assertEqual(parse(fenced('{"reply": "hi"}')).error.kind, "no_json")
        self.assertEqual(parse(fenced('{"message": "hi"}')).reply.say, "hi")


class NormalizeToolNameTests(unittest.TestCase):
    def test_case_dashes_and_spaces(self):
        self.assertEqual(normalize_tool_name("Read-File"), "read_file")
        self.assertEqual(normalize_tool_name("  Read File "), "read_file")

    def test_aliases(self):
        self.assertEqual(normalize_tool_name("bash"), "shell")
        self.assertEqual(normalize_tool_name("str_replace"), "edit_file")
        self.assertEqual(normalize_tool_name("unknown_thing"), "unknown_thing")

    def test_extra_aliases_come_first(self):
        self.assertEqual(normalize_tool_name("bash", {"bash": "run_tests"}), "run_tests")
        self.assertEqual(normalize_tool_name("Deploy-Now", {"deploy now": "deploy"}), "deploy")

    def test_generated_table_matches_aliases_json(self):
        path = os.path.normpath(os.path.join(HERE, "..", "..", "..", "aliases.json"))
        if not os.path.exists(path):
            self.skipTest("aliases.json not found")
        import hashlib
        import json

        with open(path, "rb") as fh:
            raw = fh.read()
        from heurica_tap import aliases as generated

        self.assertEqual(generated.SOURCE_SHA256, hashlib.sha256(raw).hexdigest(),
                         "aliases.py is stale: run scripts/gen_aliases.py")
        self.assertEqual(generated.ALIASES, json.loads(raw.decode("utf-8"))["aliases"])
        self.assertEqual(len(ALIASES), 54)


if __name__ == "__main__":
    unittest.main()
