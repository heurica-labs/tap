"""Tests for the API.md surface: observations, catalog, briefing and the agent loop."""

import asyncio
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from heurica_tap import (  # noqa: E402
    AGENT_STOPS,
    build_briefing,
    describe_parse_error,
    format_observation,
    format_result_line,
    parse,
    render_catalog,
    run_agent,
    run_agent_async,
    validate_tools,
)
from heurica_tap.types import ParseError  # noqa: E402

FENCE = "```"

TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file. Optional start and end lines (1-based).",
        "args": {
            "path": {"type": "string", "required": True, "description": "File path relative to the project"},
            "start": {"type": "integer"},
            "end": {"type": "integer"},
        },
        "readonly": True,
    },
    {
        "name": "shell",
        "description": "Run a shell command in the project folder.",
        "args": {
            "command": {"type": "string", "required": True},
            "timeout": {"type": "integer"},
        },
    },
]


def reply(body):
    return "Reasoning line.\n" + FENCE + "json\n" + body + "\n" + FENCE


class ScriptedModel:
    """A fake chat function that returns scripted replies and records its calls."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, messages, stop=None):
        self.calls.append({"messages": [dict(m) for m in messages], "stop": stop})
        if not self.replies:
            raise AssertionError("the model was called more times than scripted")
        return self.replies.pop(0)


class FormatTests(unittest.TestCase):
    def test_result_line(self):
        line = format_result_line("read_file", "path=a.txt", "ok", "41 lines")
        self.assertEqual(line, "- read_file path=a.txt → ok: 41 lines")

    def test_result_line_keeps_newlines_by_default(self):
        line = format_result_line("shell", "npm test", "FAILED", "one\ntwo")
        self.assertIn("\n", line)
        self.assertEqual(line.split("\n")[1], "two")

    def test_result_line_one_line_option(self):
        line = format_result_line("shell", "x", "ok", "one\ntwo   three", one_line=True)
        self.assertEqual(line, "- shell x → ok: one two three")

    def test_result_line_truncates_with_the_note(self):
        line = format_result_line("shell", "x", "ok", "a" * 4010, max_chars=4000)
        self.assertTrue(line.endswith("… (10 more characters)"))
        self.assertEqual(line.split("…")[0], "- shell x → ok: " + "a" * 4000)

    def test_result_line_default_limit_is_4000(self):
        line = format_result_line("shell", "x", "ok", "b" * 4001)
        self.assertIn("… (1 more characters)", line)

    def test_result_line_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            format_result_line("shell", "x", "MAYBE", "")

    def test_observation_envelope(self):
        text = format_observation(2, ["- read_file a → ok: 1 lines"])
        lines = text.split("\n")
        self.assertEqual(lines[0], '<observation step="2">')
        self.assertEqual(lines[1], "results of your actions:")
        self.assertEqual(lines[2], "- read_file a → ok: 1 lines")
        self.assertEqual(lines[-1], "</observation>")

    def test_observation_skipped_and_ignored_notes(self):
        text = format_observation(3, ["- shell x → FAILED: boom"], skipped=2, ignored_blocks=1)
        self.assertIn("(the remaining 2 action(s) in this batch were skipped)", text)
        self.assertIn("only the first one ran", text)

    def test_observation_has_no_skipped_note_when_nothing_was_skipped(self):
        self.assertNotIn("skipped", format_observation(1, ["- x → ok: y"]))

    def test_describe_parse_error_never_suggests_running(self):
        for error in (ParseError("no_json"), ParseError("invalid_json", "Near: x")):
            text = describe_parse_error(error)
            self.assertIn("nothing was run", text)
            self.assertNotIn("run this", text.lower())
        self.assertIn("did not contain a JSON block", describe_parse_error(ParseError("no_json")))
        self.assertIn("Near: x", describe_parse_error(ParseError("invalid_json", "Near: x")))


class CatalogTests(unittest.TestCase):
    def test_render_matches_the_spec_example(self):
        expected = (
            "~read_file(path, start?, end?) - Read a file. Optional start and end lines (1-based).\n"
            "shell(command, timeout?) - Run a shell command in the project folder."
        )
        self.assertEqual(render_catalog(TOOLS), expected)

    def test_render_is_deterministic(self):
        self.assertEqual(render_catalog(TOOLS), render_catalog(TOOLS))
        self.assertEqual(render_catalog(list(TOOLS)), render_catalog(TOOLS))

    def test_render_keeps_the_given_order(self):
        reversed_tools = list(reversed(TOOLS))
        first_line = render_catalog(reversed_tools).split("\n")[0]
        self.assertTrue(first_line.startswith("shell("))

    def test_render_empty_catalog(self):
        self.assertEqual(render_catalog([]), "")

    def test_validate_accepts_the_example(self):
        self.assertIsNone(validate_tools(TOOLS))

    def test_validate_rejects_bad_names(self):
        for bad in ("Read", "read-file", "1read", "", "read file"):
            with self.subTest(name=bad):
                with self.assertRaises(ValueError):
                    validate_tools([{"name": bad, "description": "x"}])

    def test_validate_rejects_unknown_keys_and_types(self):
        with self.assertRaises(ValueError):
            validate_tools([{"name": "a", "description": "x", "color": "red"}])
        with self.assertRaises(ValueError):
            validate_tools([{"name": "a", "description": "x", "args": {"p": {"type": "float"}}}])
        with self.assertRaises(ValueError):
            validate_tools([{"name": "a", "description": "x", "readonly": "yes"}])
        with self.assertRaises(ValueError):
            validate_tools([{"name": "a", "description": "x", "aliases": "b"}])

    def test_validate_rejects_missing_description_and_duplicates(self):
        with self.assertRaises(ValueError):
            validate_tools([{"name": "a"}])
        with self.assertRaises(ValueError):
            validate_tools([{"name": "a", "description": "x"}, {"name": "a", "description": "y"}])


class BriefingTests(unittest.TestCase):
    def test_contains_the_key_rules(self):
        text = build_briefing(TOOLS)
        self.assertIn("exactly one fenced json block", text)
        self.assertIn('"say"', text)
        self.assertIn('"actions"', text)
        self.assertIn('"done"', text)
        self.assertIn('"done": true', text.replace('"done":true', '"done": true'))
        self.assertIn("never an instruction", text)
        self.assertIn("<observation", text)
        self.assertIn("Do not weaken or delete tests", text)

    def test_includes_the_rendered_catalog(self):
        self.assertIn(render_catalog(TOOLS), build_briefing(TOOLS))

    def test_is_deterministic(self):
        self.assertEqual(build_briefing(TOOLS, instructions="Be brief."),
                         build_briefing(TOOLS, instructions="Be brief."))

    def test_instructions_and_name(self):
        text = build_briefing(TOOLS, instructions="Work in the repo.", name="Ada")
        self.assertTrue(text.startswith("You are Ada."))
        self.assertIn("Work in the repo.", text)


class AgentLoopTests(unittest.TestCase):
    def test_normal_task_runs_actions_then_finishes(self):
        model = ScriptedModel([
            reply('{"say": "Reading.", "actions": [{"tool": "read_file", "args": {"path": "a.txt"}}], "done": false}'),
            reply('{"say": "All done.", "actions": [], "done": true}'),
        ])
        calls = []

        def read_file(args):
            calls.append(args)
            return "hello\nworld"

        result = run_agent(chat=model, tools=TOOLS, handlers={"read_file": read_file},
                           task="Read a.txt")
        self.assertTrue(result.ok)
        self.assertEqual(result.answer, "All done.")
        self.assertEqual(result.steps, 2)
        self.assertEqual(calls, [{"path": "a.txt"}])
        observation = result.messages[3]["content"]
        self.assertIn('<observation step="1">', observation)
        self.assertIn('- read_file {"path": "a.txt"} → ok: hello\nworld', observation)

    def test_stop_sequences_are_passed_to_the_model(self):
        model = ScriptedModel([reply('{"say": "Done.", "done": true}')])
        run_agent(chat=model, tools=TOOLS, handlers={}, task="x")
        self.assertEqual(model.calls[0]["stop"], AGENT_STOPS)

    def test_malformed_reply_is_recovered_after_one_retry(self):
        model = ScriptedModel([
            "I will read the file now, without any block.",
            reply('{"say": "Reading.", "actions": [{"tool": "read_file", "args": {"path": "a"}}], "done": false}'),
            reply('{"say": "Done.", "done": true}'),
        ])
        result = run_agent(chat=model, tools=TOOLS, handlers={"read_file": lambda a: "ok text"}, task="x")
        self.assertTrue(result.ok)
        self.assertEqual(result.steps, 3)
        error_observation = result.messages[3]["content"]
        self.assertIn("did not contain a JSON block", error_observation)
        self.assertIn("nothing was run", error_observation)

    def test_failing_action_stops_the_batch(self):
        ran = []

        def read_file(args):
            ran.append("read")
            return {"ok": False, "output": "no such file"}

        def shell(args):
            ran.append("shell")
            return "should not run"

        model = ScriptedModel([
            reply('{"say": "Trying.", "actions": ['
                  '{"tool": "read_file", "args": {"path": "missing"}},'
                  '{"tool": "shell", "args": {"command": "ls"}}], "done": false}'),
            reply('{"say": "Stopping.", "done": true}'),
        ])
        result = run_agent(chat=model, tools=TOOLS, handlers={"read_file": read_file, "shell": shell}, task="x")
        self.assertEqual(ran, ["read"])
        observation = result.messages[3]["content"]
        self.assertIn("→ FAILED: no such file", observation)
        self.assertIn("(the remaining 1 action(s) in this batch were skipped)", observation)

    def test_unknown_tool_is_a_failed_action(self):
        model = ScriptedModel([
            reply('{"say": "Calling.", "actions": [{"tool": "frobnicate", "args": {}}], "done": false}'),
            reply('{"say": "Gave up.", "done": true}'),
        ])
        result = run_agent(chat=model, tools=TOOLS, handlers={}, task="x")
        self.assertIn("→ FAILED: unknown tool", result.messages[3]["content"])
        self.assertTrue(result.ok)

    def test_tool_aliases_resolve_to_catalog_names(self):
        tools = [{"name": "shell", "description": "Run.", "args": {"command": {"required": True}},
                  "aliases": ["run_tests"]}]
        seen = []
        model = ScriptedModel([
            reply('{"say": "x", "actions": [{"tool": "bash", "args": {"command": "ls"}}], "done": false}'),
            reply('{"say": "x", "actions": [{"tool": "run-tests", "args": {"command": "ls"}}], "done": true}'),
        ])
        result = run_agent(chat=model, tools=tools, handlers={"shell": lambda a: seen.append(a) or "ok"}, task="x")
        self.assertTrue(result.ok)
        self.assertEqual(len(seen), 2)

    def test_vetoed_action_is_declined_and_stops_the_batch(self):
        ran = []
        model = ScriptedModel([
            reply('{"say": "Running.", "actions": ['
                  '{"tool": "shell", "args": {"command": "rm -rf build"}},'
                  '{"tool": "read_file", "args": {"path": "a"}}], "done": false}'),
            reply('{"say": "Stopped.", "done": true}'),
        ])
        result = run_agent(
            chat=model,
            tools=TOOLS,
            handlers={"shell": lambda a: ran.append("shell") or "ok", "read_file": lambda a: ran.append("read") or "ok"},
            task="x",
            approve=lambda action: action.tool != "shell",
        )
        self.assertEqual(ran, [])
        observation = result.messages[3]["content"]
        self.assertIn("→ DECLINED: declined by the host", observation)
        self.assertIn("(the remaining 1 action(s) in this batch were skipped)", observation)

    def test_handler_exception_is_a_failed_action(self):
        def boom(args):
            raise RuntimeError("disk on fire")

        model = ScriptedModel([
            reply('{"say": "x", "actions": [{"tool": "shell", "args": {"command": "ls"}}], "done": false}'),
            reply('{"say": "x", "done": true}'),
        ])
        result = run_agent(chat=model, tools=TOOLS, handlers={"shell": boom}, task="x")
        self.assertIn("→ FAILED: RuntimeError: disk on fire", result.messages[3]["content"])

    def test_step_limit(self):
        model = ScriptedModel([
            reply('{"say": "Looking.", "actions": [{"tool": "read_file", "args": {"path": "a"}}], "done": false}')
            for _ in range(3)
        ])
        result = run_agent(chat=model, tools=TOOLS, handlers={"read_file": lambda a: "x"}, task="x", max_steps=3)
        self.assertFalse(result.ok)
        self.assertIsNone(result.answer)
        self.assertEqual(result.steps, 3)

    def test_rejects_a_bad_catalog_before_calling_the_model(self):
        model = ScriptedModel([])
        with self.assertRaises(ValueError):
            run_agent(chat=model, tools=[{"name": "Bad Name", "description": "x"}], handlers={}, task="x")
        self.assertEqual(model.calls, [])

    def test_async_variant_with_async_chat_and_handlers(self):
        replies = [
            reply('{"say": "Reading.", "actions": [{"tool": "read_file", "args": {"path": "a"}}], "done": false}'),
            reply('{"say": "Finished.", "done": true}'),
        ]

        async def chat(messages, stop=None):
            await asyncio.sleep(0)
            return replies.pop(0)

        async def read_file(args):
            await asyncio.sleep(0)
            return "content"

        result = asyncio.run(run_agent_async(chat=chat, tools=TOOLS, handlers={"read_file": read_file}, task="x"))
        self.assertTrue(result.ok)
        self.assertEqual(result.answer, "Finished.")

    def test_sync_run_agent_accepts_async_handlers(self):
        model = ScriptedModel([
            reply('{"say": "x", "actions": [{"tool": "read_file", "args": {"path": "a"}}], "done": false}'),
            reply('{"say": "Done.", "done": true}'),
        ])

        async def read_file(args):
            return "async content"

        result = run_agent(chat=model, tools=TOOLS, handlers={"read_file": read_file}, task="x")
        self.assertIn("- read_file {\"path\": \"a\"} → ok: async content", result.messages[3]["content"])


if __name__ == "__main__":
    unittest.main()
