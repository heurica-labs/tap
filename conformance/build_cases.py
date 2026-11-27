#!/usr/bin/env python3
"""Builds cases.src.json: the TAP conformance inputs (SPEC.md section 6).

Run:  python3 build_cases.py   (writes cases.src.json next to this file)
Then: tools/oracle/oracle cases.src.json > vectors.json

Each case is {"id", "description", "section", "input"}. Inputs are what a model
might send: prose, fenced JSON, occasional slips. JSON bodies are written as
Python strings; "\\n" in Python becomes a real newline in the model text and
"\\\\n" becomes the two characters backslash-n inside a JSON string.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
cases = []


def add(cid, section, description, text):
    cases.append({"id": cid, "description": description, "section": section, "input": text})


def fence(body, tag="json"):
    return "```%s\n%s\n```" % (tag, body)


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False)


# ---------------------------------------------------------------- 6.1 finding the JSON
add("fence-json-plain-valid", "6.1",
    "Reasoning line, then one plain json fence: the fence is read.",
    "Checking the config first.\n" + fence(
        '{"say": "Reading the config.", "actions": [{"tool": "read_file", "args": {"path": "config.toml"}}], "done": false}'))

add("fence-untagged", "6.1",
    "Untagged fence holding a reply object.",
    "```\n" + '{"say": "Listing the tests.", "actions": [{"tool": "glob", "args": {"pattern": "**/*_test.go"}}]}' + "\n```")

add("fence-tag-uppercase-json", "6.1",
    "Fence tagged JSON in capitals.",
    fence('{"say": "Reading.", "actions": [{"tool": "read_file", "args": {"path": "a.txt"}}], "done": false}', "JSON"))

add("fence-tag-javascript", "6.1",
    "Fence tagged javascript holding a reply object.",
    fence('{"say": "Reading.", "actions": [{"tool": "read_file", "args": {"path": "a.txt"}}], "done": false}', "javascript"))

add("reasoning-before-block", "6.1",
    "Several sentences of reasoning before the block; the reasoning becomes the thought.",
    "The login test fails on the second assertion. I want to see the test body before changing anything, so I will read it.\n\n"
    + fence('{"say": "Reading the login test.", "actions": [{"tool": "read_file", "args": {"path": "tests/login.test.ts"}}], "done": false}'))

add("swift-fence-before-json", "6.1",
    "A swift code fence comes before the reply; the reply's fence is still found.",
    "Here is the function as it stands:\n" + fence("func total(_ xs: [Int]) -> Int {\n    xs.reduce(0, +)\n}", "swift")
    + "\nI will rewrite it to handle an empty list.\n"
    + fence('{"say": "Rewriting total() for the empty case.", "actions": [{"tool": "edit_file", "args": {"path": "Sources/Total.swift", "find": "xs.reduce(0, +)", "replace": "xs.isEmpty ? 0 : xs.reduce(0, +)"}}], "done": false}'))

add("python-fence-braces-before-json", "6.1",
    "A python fence containing dict braces comes first; it is skipped and the reply fence wins.",
    "The data looks like this:\n" + fence('config = {"debug": True, "level": 3}\nprint(config)', "python")
    + "\n" + fence('{"say": "Turning debug off.", "actions": [{"tool": "edit_file", "args": {"path": "config.py", "find": "\\"debug\\": True", "replace": "\\"debug\\": False"}}], "done": false}'))

add("package-json-quoted-skipped", "6.1",
    "A quoted package.json (a json fence that is not a reply) is skipped; the real reply after it is used.",
    "The package file currently reads:\n"
    + fence('{"name": "anvil-demo", "version": "1.0.0", "scripts": {"test": "jest"}}')
    + "\nI will add a lint script next to it.\n"
    + fence('{"say": "Adding a lint script.", "actions": [{"tool": "edit_file", "args": {"path": "package.json", "find": "scripts", "replace": "scripts"}}], "done": false}'))

add("two-valid-blocks-first-wins", "6.1",
    "Two valid reply blocks: the first runs, the second is ignored and counted.",
    fence('{"say": "Reading the parser.", "actions": [{"tool": "read_file", "args": {"path": "parser.swift"}}], "done": false}')
    + "\n\nAfter that I would edit the file:\n"
    + fence('{"say": "Editing the parser.", "actions": [{"tool": "edit_file", "args": {"path": "parser.swift", "find": "a", "replace": "b"}}], "done": false}'))

add("three-valid-blocks", "6.1",
    "Three valid reply blocks: the first wins and two are ignored.",
    fence('{"say": "Step one.", "actions": [{"tool": "shell", "args": {"command": "ls"}}], "done": false}')
    + "\n"
    + fence('{"say": "Step two.", "actions": [{"tool": "shell", "args": {"command": "pwd"}}], "done": false}')
    + "\n"
    + fence('{"say": "Step three.", "actions": [{"tool": "shell", "args": {"command": "whoami"}}], "done": false}'))

add("imagined-observation-second-block", "6.1",
    "The model writes an observation and a final reply after its block; only the first block runs.",
    fence('{"say": "Running the tests.", "actions": [{"tool": "shell", "args": {"command": "npm test"}}], "done": false}')
    + "\n\n<observation step=\"2\">\nresults of your actions:\n- shell npm test -> ok: 12 passed\n</observation>\n\n"
    + fence('{"say": "All tests pass.", "actions": [], "done": true}'))

add("nested-fence-in-write-file-content", "6.1",
    "A json fence whose write_file content is a Markdown file with its own code fence (section 6.1 step 2).",
    "I'll write the README.\n```json\n"
    + '{"say": "Writing the README.", "actions": [{"tool": "write_file", "args": {"path": "README.md", "content": "# Demo\\n\\nRun it:\\n\\n```bash\\nnpm install\\nnpm start\\n```\\n"}}], "done": false}'
    + "\n```")

add("single-fence-starts-brace-trailing-comma", "6.1",
    "A single fence whose body starts with { and has a trailing comma.",
    fence('{"say": "Checking the build log.", "actions": [{"tool": "shell", "args": {"command": "tail -n 20 build.log"}}], "done": false,}'))

add("no-fence-prose-around-object", "6.1",
    "No fence at all: the outermost {...} in the prose is used.",
    'Sure, listing the project first. {"say": "Listing the project.", "actions": [{"tool": "list_dir", "args": {"path": "."}}]} Tell me if you want more detail.')

add("cut-off-no-closing-brace-no-fence", "6.1",
    "Reply cut off before any closing brace and without a fence (section 6.1 step 5).",
    'Writing the notes now.\n{"say": "Writing the notes.", "actions": [{"tool": "write_file", "args": {"path": "notes.md", "content": "Done so far')

add("cut-off-in-fence-missing-brace-and-fence", "6.1",
    "A json fence that ends mid-object with no closing fence.",
    '```json\n{"say": "Editing.", "actions": [{"tool": "edit_file", "args": {"path": "a.txt", "find": "x", "replace": "y"}}')

add("unclosed-json-fence-complete-object", "6.1",
    "A json fence whose object is complete but whose closing fence is missing.",
    '```json\n{"say": "Done.", "done": true}\n')

add("empty-input-no-json", "6.1",
    "Empty reply: no JSON at all, error no_json.",
    "")

add("no-json-at-all", "6.1",
    "Prose only: error no_json.",
    "I cannot help with that request, sorry. Please try again later.")

add("braces-in-prose-not-json", "6.1",
    "Text with braces that is not JSON: the outermost-object step finds something that does not parse.",
    "The template uses {name} and {count} placeholders, so I will keep the braces as they are.")

add("unrelated-json-fence-alone", "6.1",
    "A json fence that is not reply-shaped and is the only fence: the fallback takes it anyway.",
    "Here is the package file.\n" + fence('{"name": "anvil-demo", "version": "1.0.0"}'))

add("json-array-fence-not-actions", "6.1",
    "A json fence holding an array of numbers, which is not reply-shaped.",
    "The ids are:\n" + fence("[1, 2, 3]"))

# ---------------------------------------------------------------- 6.2 what counts as a reply
add("shape-message-key-only", "6.2",
    "An object whose only reply key is message is reply-shaped; message becomes say.",
    fence('{"message": "Hello, the build is green."}'))

add("shape-answer-key-only", "6.2",
    "An object whose only reply key is answer is reply-shaped.",
    fence('{"answer": "The answer is 42."}'))

add("shape-milestone-only", "6.2",
    "An object whose only reply key is milestone is reply-shaped (nothing else is set).",
    fence('{"milestone": 2}'))

add("shape-array-of-actions-only", "6.2",
    "A json fence holding a top-level array that contains action-shaped objects is reply-shaped.",
    fence('[{"tool": "shell", "args": {"command": "make"}}]'))

# ---------------------------------------------------------------- 6.3 repairs
add("repair-trailing-comma-object", "6.3",
    "Trailing commas before } in the action and the reply object.",
    fence('{"say": "Reading.", "actions": [{"tool": "read_file", "args": {"path": "main.go",},},], "done": false,}'))

add("repair-trailing-comma-array", "6.3",
    "Trailing comma after the last action in the array.",
    fence('{"say": "Reading two files.", "actions": [{"tool": "read_file", "args": {"path": "a.go"}}, {"tool": "read_file", "args": {"path": "b.go"}},], "done": false}'))

add("repair-line-comments", "6.3",
    "// line comments outside strings are removed.",
    fence('{\n  // the file to read\n  "say": "Reading.", // why\n  "actions": [{"tool": "read_file", "args": {"path": "main.go"}}]\n}'))

add("repair-python-true-false", "6.3",
    "Python True and False outside strings become JSON booleans.",
    fence('{"say": "Turning on the flag.", "actions": [{"tool": "edit_file", "args": {"path": "config.py", "find": "enabled = False", "replace": "enabled = True", "dry_run": False}}], "done": True}'))

add("repair-python-none-done", "6.3",
    "Python None outside a string (done set to None).",
    fence('{"say": "Checking.", "actions": [{"tool": "shell", "args": {"command": "ls"}}], "done": None}'))

add("repair-curly-quote-delimiters", "6.3",
    "Curly quotes used as JSON string delimiters.",
    fence('{\u201csay\u201d: \u201cChecking the file.\u201d, \u201cactions\u201d: [{\u201ctool\u201d: \u201cread_file\u201d, \u201cargs\u201d: {\u201cpath\u201d: \u201cREADME.md\u201d}}]}'))

add("repair-raw-newline-in-string", "6.3",
    "A raw newline inside the say string is escaped.",
    fence('{"say": "Line one of the answer.\nLine two of the answer.", "actions": [], "done": true}'))

add("repair-raw-tab-in-string", "6.3",
    "A raw tab inside a string value is escaped.",
    fence('{"say": "Aligned columns:", "actions": [{"tool": "write_file", "args": {"path": "table.txt", "content": "name\tvalue\nalpha\t1\n"}}], "done": false}'))

add("repair-raw-cr-alone-in-string", "6.3",
    "A raw carriage return (no line feed) inside a string value is escaped.",
    fence('{"say": "Two rows:", "actions": [{"tool": "write_file", "args": {"path": "rows.txt", "content": "alpha\rbeta\r"}}], "done": false}'))

add("repair-raw-crlf-in-string", "6.3",
    "A raw CRLF line ending inside a string value. Spec 6.3 says CR and LF are escaped; a CRLF pair must be escaped too.",
    fence('{"say": "Windows lines:", "actions": [{"tool": "write_file", "args": {"path": "win.txt", "content": "alpha\r\nbeta\r\n"}}], "done": false}'))

add("ignored-count-skips-invalid-second-block", "6.1",
    "The first block is a reply; the second block is not valid JSON. Only valid reply blocks count as ignored.",
    fence('{"say": "Reading.", "actions": [{"tool": "read_file", "args": {"path": "a.txt"}}], "done": false}')
    + "\n\nThen I would run:\n```json\n{\"say\": \"Running.\", \"actions\": [{\"tool\": \"shell\", \"args\": {\"command\": \"ls\"\n```")

add("ignored-count-four-blocks", "6.1",
    "Four valid reply blocks: the first runs and three are ignored.",
    fence('{"say": "One.", "actions": [{"tool": "shell", "args": {"command": "ls"}}]}')
    + "\n" + fence('{"say": "Two.", "actions": [{"tool": "shell", "args": {"command": "pwd"}}]}')
    + "\n" + fence('{"say": "Three.", "actions": [{"tool": "shell", "args": {"command": "date"}}]}')
    + "\n" + fence('{"say": "Four.", "actions": [{"tool": "shell", "args": {"command": "uname"}}]}'))

add("ignored-count-plan-reply-then-block", "6.1",
    "A plan reply followed by a second reply block: the plan is read from the first, one block is ignored.",
    fence('{"say": "Plan first.", "plan": ["Read the code", "Change it"]}')
    + "\nThen:\n" + fence('{"say": "Reading.", "actions": [{"tool": "read_file", "args": {"path": "a.txt"}}]}'))

add("ignored-count-second-block-is-package-json", "6.1",
    "A second fence that is a package.json is not a reply, so nothing is counted as ignored.",
    fence('{"say": "Reading.", "actions": [{"tool": "read_file", "args": {"path": "a.txt"}}], "done": false}')
    + "\n" + fence('{"name": "demo", "version": "1.0.0"}'))

add("error-single-quoted-keys", "6.3",
    "Single-quoted keys and strings are not JSON and are not a repair: error invalid_json.",
    fence("{'say': 'hi', 'actions': []}"))

add("error-unquoted-keys", "6.3",
    "Unquoted keys are not a repair: error invalid_json.",
    fence('{say: "hi", actions: []}'))

add("error-bare-word-value", "6.3",
    "A bare word as a value is not a repair: error invalid_json.",
    fence('{"say": hello}'))

add("error-top-level-string-no-json", "6.1",
    "A bare JSON string with no object or fence: error no_json.",
    '"just a string"')

add("error-number-only-fence-no-json", "6.1",
    "A json fence holding a bare number: no object in the text, error no_json.",
    "The answer is:\n" + fence("42"))

add("empty-object-fence", "6.2",
    "A json fence holding {} is not reply-shaped; the fallback still takes it (empty reply).",
    fence("{}"))

add("shape-action-key-only", "6.2",
    "An object whose only reply key is action is reply-shaped.",
    fence('{"action": {"tool": "shell", "args": {"command": "ls"}}}'))

add("shape-steps-key-only", "6.2",
    "An object whose only reply key is steps is reply-shaped.",
    fence('{"steps": [{"tool": "shell", "args": {"command": "ls"}}]}'))

add("shape-plan-key-only", "6.2",
    "An object whose only reply key is plan is reply-shaped.",
    fence('{"plan": ["Read the code", "Change it"]}'))

add("shape-done-key-only", "6.2",
    "An object whose only reply key is done is reply-shaped.",
    fence('{"done": true}'))

add("empty-say-no-prose-inferred-done", "6.5",
    "An empty say with no actions and no done key. Spec 6.5 infers done only for a non-empty say.",
    fence('{"say": "", "actions": []}'))

add("done-string-true", "6.4",
    "done given as the string \"true\" (spec says boolean).",
    fence('{"say": "Finished.", "actions": [], "done": "true"}'))

add("say-number-becomes-string", "6.4",
    "say given as a number.",
    fence('{"say": 42, "actions": []}'))

add("say-object-shadows-message", "6.4",
    "say given as an object while message is a string: the say key wins and the value is lost.",
    fence('{"say": {"text": "Hi"}, "message": "Hello there.", "actions": []}'))

add("tool-name-number-becomes-string", "6.4",
    "A tool name given as a number becomes the string \"5\".",
    fence('{"say": "Calling.", "actions": [{"tool": 5, "args": {}}]}'))

add("plan-numeric-entries-become-strings", "6.8",
    "Plan entries given as numbers.",
    fence('{"say": "Plan.", "plan": [1, 2]}'))

add("pointer-status-working-long-after", "6.7",
    "A pointer with status working (not done) and long prose after it: the pointer rule sets done to true.",
    fence('{"say": "See below.", "actions": [], "status": "working"}')
    + "\n\nThe migration finished on staging, and the rollback script has been tested twice.")

add("repair-text-after-object-fenced", "6.3",
    "Text after the object, inside the fence: the first balanced object is taken.",
    fence('{"say": "Found it.", "actions": [], "done": true} and that is all'))

add("repair-text-after-object-unfenced", "6.3",
    "Text after an unfenced object that itself ends with braces.",
    '{"say": "Checking.", "actions": [{"tool": "shell", "args": {"command": "ls"}}]} Hope this helps {note}')

add("repair-extra-closing-brace", "6.3",
    "An extra closing brace after the reply object.",
    fence('{"say": "Finished.", "done": true}}'))

add("repair-mismatched-closer-in-args", "6.3",
    "A ] closes an args object that should close with }.",
    fence('{"say": "Searching.", "actions": [{"tool": "grep", "args": {"pattern": "TODO"}]}'))

add("repair-missing-closers-at-end", "6.3",
    "The fence closes, but the action array and the root object are missing their closers.",
    fence('{"say": "Searching.", "actions": [{"tool": "grep", "args": {"pattern": "TODO"}}'))

add("repair-two-actions-first-unclosed", "6.3",
    "The first action object is never closed before the second one starts.",
    fence('{"say": "Two reads.", "actions": [{"tool": "read_file", "args": {"path": "a.txt"}, {"tool": "read_file", "args": {"path": "b.txt"}}]}'))

add("repair-unterminated-string-at-end", "6.3",
    "The reply stops inside a content string; the string and containers are closed.",
    '{"say": "Writing the note.", "actions": [{"tool": "write_file", "args": {"path": "NOTE.md", "content": "hello wor')

add("content-python-true-untouched", "6.3",
    "A Python True and None inside a file content string must not be rewritten (the outer object is valid).",
    fence(dumps({"say": "Adding the debug guard.", "actions": [{"tool": "write_file", "args": {"path": "guard.py", "content": "DEBUG = True\nif DEBUG == True:\n    print(None)\n"}}], "done": False})))

add("content-trailing-comma-untouched", "6.3",
    "A JS trailing comma inside a content string stays, while the outer object needs repair.",
    '```json\n{"say": "Writing the config.", "actions": [{"tool": "write_file", "args": {"path": "cfg.js", "content": "const cfg = {a: 1, b: 2,};\\n"}}],}\n```')

add("content-comment-and-url-untouched", "6.3",
    "// comments and a URL with // inside a content string stay; the outer object needs a repair.",
    '```json\n{"say": "Writing the notes.", "actions": [{"tool": "write_file", "args": {"path": "notes.js", "content": "// TODO: handle errors\\nconst url = \\"https://example.com/docs\\";\\n"}}],}\n```')

add("content-curly-quotes-untouched", "6.3",
    "Curly quotes inside a straight-quoted content string stay; the outer object needs a repair.",
    '```json\n{"say": "Writing the greeting.", "actions": [{"tool": "write_file", "args": {"path": "hi.txt", "content": "He said \u201chi\u201d and it\'s fine.\\n"}}],}\n```')

add("error-invalid-missing-comma", "6.3",
    "Missing comma between two keys: not repairable, error invalid_json.",
    fence('{"say": "ok" "actions": []}'))

add("error-invalid-missing-colon", "6.3",
    "Missing colon after a key: error invalid_json.",
    fence('{"say" "ok", "actions": []}'))

add("error-invalid-bad-number", "6.3",
    "A malformed number (1.2.3) is not repairable: error invalid_json.",
    fence('{"say": "x", "milestone": 1.2.3}'))

add("error-invalid-missing-comma-in-args", "6.3",
    "A missing comma inside an args object: error invalid_json.",
    fence('{"say": "Running.", "actions": [{"tool": "shell", "args": {"command": "ls" "timeout": 5}}]}'))

# ---------------------------------------------------------------- 6.4 shape normalization
add("tool-key-action", "6.4",
    "Tool name under the key action.",
    fence('{"say": "Reading.", "actions": [{"action": "read_file", "args": {"path": "src/app.ts"}}]}'))

add("tool-key-name", "6.4",
    "Tool name under the key name.",
    fence('{"say": "Reading.", "actions": [{"name": "read_file", "args": {"path": "src/app.ts"}}]}'))

add("tool-key-type", "6.4",
    "Tool name under the key type.",
    fence('{"say": "Reading.", "actions": [{"type": "read_file", "args": {"path": "src/app.ts"}}]}'))

add("tool-key-function", "6.4",
    "Tool name under the key function.",
    fence('{"say": "Running.", "actions": [{"function": "shell", "args": {"command": "make"}}]}'))

add("tool-key-cmd", "6.4",
    "Tool name under the key cmd.",
    fence('{"say": "Running.", "actions": [{"cmd": "shell", "args": {"command": "make"}}]}'))

add("tool-key-command-name", "6.4",
    "Tool name under the key command_name.",
    fence('{"say": "Running.", "actions": [{"command_name": "shell", "args": {"command": "make"}}]}'))

add("args-key-arguments", "6.4",
    "Arguments under the key arguments.",
    fence('{"say": "Reading.", "actions": [{"tool": "read_file", "arguments": {"path": "a.txt", "start": 1, "end": 20}}]}'))

add("args-key-params", "6.4",
    "Arguments under the key params.",
    fence('{"say": "Searching.", "actions": [{"tool": "grep", "params": {"pattern": "TODO"}}]}'))

add("args-key-parameters", "6.4",
    "Arguments under the key parameters.",
    fence('{"say": "Searching.", "actions": [{"tool": "grep", "parameters": {"pattern": "FIXME"}}]}'))

add("args-key-input", "6.4",
    "Arguments under the key input.",
    fence('{"say": "Listing.", "actions": [{"tool": "list_dir", "input": {"path": "src"}}]}'))

add("args-key-inputs", "6.4",
    "Arguments under the key inputs.",
    fence('{"say": "Listing.", "actions": [{"tool": "list_dir", "inputs": {"path": "docs"}}]}'))

add("args-json-string-parsed", "6.4",
    "Arguments given as a string that holds a JSON object: the string is parsed.",
    fence(dumps({"say": "Reading a range.", "actions": [{"tool": "read_file", "arguments": "{\"path\": \"src/app.ts\", \"start\": 1, \"end\": 20}"}]})))

add("args-flat-meta-keys-stripped", "6.4",
    "No argument key: the other keys are the arguments, and meta keys are removed.",
    fence('{"say": "Listing.", "actions": [{"tool": "shell", "command": "ls -la", "timeout": 30, "thought": "need the files", "reasoning": "x", "risk": "low", "why": "see the tree"}]}'))

add("args-non-object-number", "6.4",
    "Non-object arguments (a number) become {\"value\": 42}.",
    fence('{"say": "Setting the limit.", "actions": [{"tool": "shell", "args": 42}]}'))

add("args-non-object-array", "6.4",
    "Non-object arguments (an array) become {\"value\": [...]}.",
    fence('{"say": "Reading both.", "actions": [{"tool": "read_file", "args": ["a.txt", "b.txt"]}]}'))

add("args-non-object-string", "6.4",
    "Non-object arguments (a plain string) become {\"value\": \"...\"}.",
    fence('{"say": "Reading.", "actions": [{"tool": "read_file", "args": "src/main.swift"}]}'))

add("args-null-becomes-value-null", "6.4",
    "Arguments that are null become {\"value\": null}.",
    fence('{"say": "Listing.", "actions": [{"tool": "list_dir", "args": null}]}'))

add("action-list-steps-key", "6.4",
    "Action list under the key steps.",
    fence('{"say": "Two steps.", "steps": [{"tool": "read_file", "args": {"path": "a"}}, {"tool": "shell", "args": {"command": "make"}}]}'))

add("action-list-tool-calls-key", "6.4",
    "Action list under the key tool_calls.",
    fence('{"say": "Two steps.", "tool_calls": [{"name": "read_file", "arguments": {"path": "a"}}, {"name": "shell", "arguments": {"command": "make"}}]}'))

add("single-action-object", "6.4",
    "A single action under the key action (not a list) is a list of one.",
    fence('{"say": "Looking.", "action": {"tool": "shell", "args": {"command": "pwd"}}}'))

add("single-tool-object", "6.4",
    "A single action object under the key tool is a list of one.",
    fence('{"say": "Looking.", "tool": {"name": "shell", "args": {"command": "pwd"}}}'))

add("top-level-single-action", "6.4",
    "The whole reply is one action object with no say.",
    fence('{"tool": "shell", "args": {"command": "pwd"}}'))

add("top-level-array-of-actions", "6.4",
    "The whole reply is a top-level array of actions.",
    fence('[{"tool": "read_file", "args": {"path": "a.txt"}}, {"tool": "read_file", "args": {"path": "b.txt"}}]'))

add("say-key-message", "6.4",
    "say given as message.",
    fence('{"message": "Found it.", "actions": []}'))

add("say-key-reply", "6.4",
    "say given as reply, next to actions.",
    fence('{"reply": "Reading the file now.", "actions": [{"tool": "read_file", "args": {"path": "a.txt"}}]}'))

add("say-key-response", "6.4",
    "say given as response, next to actions.",
    fence('{"response": "Searching the repo.", "actions": [{"tool": "grep", "args": {"pattern": "TODO"}}]}'))

add("done-true-with-actions-kept", "6.4",
    "done true with actions present: the actions are kept (the spec says a done reply SHOULD have none).",
    fence('{"say": "All set.", "actions": [{"tool": "shell", "args": {"command": "make test"}}], "done": true}'))

add("status-done-string", "6.4",
    "status \"done\" means done.",
    fence('{"say": "Finished.", "status": "done"}'))

add("status-complete-string", "6.4",
    "status \"complete\" means done.",
    fence('{"say": "Finished.", "status": "complete"}'))

add("status-finished-string", "6.4",
    "status \"finished\" means done.",
    fence('{"say": "Finished.", "status": "finished"}'))

add("status-working-not-done", "6.4",
    "status with another value is not done, but it is still an explicit status.",
    fence('{"say": "Still working.", "actions": [{"tool": "shell", "args": {"command": "make"}}], "status": "working"}'))

add("tool-name-case-dash-space", "6.4",
    "Tool names with case, dashes and spaces are normalized.",
    fence('{"say": "Reading.", "actions": [{"tool": "  Read File ", "args": {"path": "a"}}, {"tool": "Edit-File", "args": {"path": "a", "find": "x", "replace": "y"}}, {"tool": "list dir", "args": {"path": "."}}]}'))

add("alias-shell-family", "6.4",
    "bash, run_command and sh are aliases for shell.",
    fence('{"say": "Running.", "actions": [{"tool": "bash", "args": {"command": "ls"}}, {"tool": "run_command", "args": {"command": "pwd"}}, {"tool": "sh", "args": {"command": "whoami"}}]}'))

add("alias-read-family", "6.4",
    "cat, view and open_file are aliases for read_file.",
    fence('{"say": "Reading.", "actions": [{"tool": "cat", "args": {"path": "a"}}, {"tool": "view", "args": {"path": "b"}}, {"tool": "open_file", "args": {"path": "c"}}]}'))

add("alias-write-family", "6.4",
    "write, create_file and save_file are aliases for write_file.",
    fence('{"say": "Writing.", "actions": [{"tool": "write", "args": {"path": "a", "content": "1"}}, {"tool": "create_file", "args": {"path": "b", "content": "2"}}, {"tool": "save_file", "args": {"path": "c", "content": "3"}}]}'))

add("alias-edit-family", "6.4",
    "str_replace, replace_in_file and str_replace_editor are aliases for edit_file.",
    fence('{"say": "Editing.", "actions": [{"tool": "str_replace", "args": {"path": "a", "find": "x", "replace": "y"}}, {"tool": "replace_in_file", "args": {"path": "b", "find": "x", "replace": "y"}}, {"tool": "str_replace_editor", "args": {"path": "c", "find": "x", "replace": "y"}}]}'))

add("alias-search-family", "6.4",
    "rg and search_code map to grep; find_files and find map to glob; search_files maps to grep.",
    fence('{"say": "Searching.", "actions": [{"tool": "rg", "args": {"pattern": "TODO"}}, {"tool": "search_code", "args": {"pattern": "FIXME"}}, {"tool": "find_files", "args": {"pattern": "*.swift"}}, {"tool": "find", "args": {"pattern": "*.md"}}, {"tool": "search_files", "args": {"pattern": "main"}}]}'))

add("alias-misc-family", "6.4",
    "multiedit, ls, fetch, todowrite, rm and curl map to their canonical tools.",
    fence('{"say": "Working.", "actions": [{"tool": "multiedit", "args": {"path": "a", "edits": []}}, {"tool": "ls", "args": {"path": "."}}, {"tool": "fetch", "args": {"url": "https://example.com"}}, {"tool": "todowrite", "args": {"todos": []}}, {"tool": "rm", "args": {"path": "old.txt"}}, {"tool": "curl", "args": {"url": "https://example.com/a"}}]}'))

add("alias-unknown-name-kept", "6.4",
    "A name that is not in the alias table is lowercased and kept.",
    fence('{"say": "Calling.", "actions": [{"tool": "Frobnicate Widget", "args": {"id": 7}}]}'))

# ---------------------------------------------------------------- 6.5 completion
add("done-action-with-actions-before-and-after", "6.5",
    "A done action after an edit: the edit stays, the done message is the answer, and the action after done is dropped.",
    fence('{"say": "Fixing it.", "actions": [{"tool": "edit_file", "args": {"path": "a.py", "find": "x", "replace": "y"}}, {"tool": "done", "args": {"message": "Fixed the off-by-one in a.py."}}, {"tool": "shell", "args": {"command": "pytest"}}]}'))

add("finish-action-text-arg", "6.5",
    "A finish action with a text argument.",
    fence('{"say": "Working.", "actions": [{"tool": "finish", "args": {"text": "The config now uses port 8080."}}]}'))

add("final-answer-result-arg", "6.5",
    "A final_answer action with a result argument and no say.",
    fence('{"actions": [{"tool": "final_answer", "args": {"result": "There are 3 TODOs."}}]}'))

add("answer-action-say-arg", "6.5",
    "An answer action with a say argument.",
    fence('{"actions": [{"tool": "answer", "args": {"say": "It is 42."}}]}'))

add("attempt-completion-message-arg", "6.5",
    "attempt_completion under the key name, with arguments under the key arguments.",
    fence('{"say": "Wrapping up.", "actions": [{"name": "attempt_completion", "arguments": {"message": "Refactor complete."}}]}'))

add("complete-no-message-keeps-say", "6.5",
    "A complete action with no message argument keeps the reply's say as the answer.",
    fence('{"say": "Everything is in place.", "actions": [{"tool": "complete", "args": {}}]}'))

add("done-action-first-no-prior-actions", "6.5",
    "A done action as the only action: the actions list is empty and the message is the answer.",
    fence('{"actions": [{"tool": "done", "args": {"message": "Nothing to change."}}]}'))

add("done-action-empty-message-keeps-say", "6.5",
    "A done action with an empty message does not replace say.",
    fence('{"say": "Finished.", "actions": [{"tool": "done", "args": {"message": ""}}]}'))

add("inferred-done-say-only", "6.5",
    "Say only, no actions, no done key and no plan: done is inferred (explicitDone false).",
    fence('{"say": "The function returns 3."}'))

add("explicit-done-false-say-only", "6.5",
    "Say only with an explicit done false: the reply is not done.",
    fence('{"say": "Which file should I edit?", "actions": [], "done": false}'))

add("plan-with-say-only-not-done", "6.5",
    "Say and plan with no actions: done is not inferred, because a plan is present.",
    fence('{"say": "Here is the plan for the migration.", "plan": ["Add the new table", "Backfill the rows", "Drop the old column"]}'))

# ---------------------------------------------------------------- 6.6 / 6.7 say pointers
add("pointer-answered-below-long-after", "6.7",
    "say is \"Answered below.\" and more than 40 characters follow the block: the prose replaces say.",
    "Let me think about that.\n"
    + fence('{"say": "Answered below.", "actions": []}')
    + "\n\nThe Eiffel Tower is in Paris, France, and it was completed in 1889 for the World's Fair.")

add("pointer-see-below-short-after-kept", "6.7",
    "say is \"See below.\" but only 4 characters follow: say stays.",
    fence('{"say": "See below.", "actions": []}') + "\n\nYes.")

add("pointer-as-follows-colon-long-after", "6.7",
    "say ends with \"as follows:\" and a numbered list follows the block.",
    fence('{"say": "As follows:", "actions": []}')
    + "\n\n1. Add the index. 2. Run the migration. 3. Restart the service and check the logs.")

add("pointer-empty-say-long-after", "6.6",
    "An empty say followed by long prose: the prose is the answer.",
    fence('{"say": "", "actions": []}')
    + "\n\nThe build uses Node 20, and the lockfile pins every transitive dependency to a fixed version.")

add("pointer-explicit-done-false-long-after", "6.7",
    "A pointer with explicit done false and long prose after: the prose replaces say but done stays false.",
    fence('{"say": "Answered below.", "actions": [], "done": false}')
    + "\n\nThe cache is cleared on every deploy, so stale entries never survive a release.")

add("pointer-with-actions-ignores-after", "6.7",
    "A pointer with actions present: the prose after the block is not used as the answer.",
    fence('{"say": "See below.", "actions": [{"tool": "read_file", "args": {"path": "README.md"}}]}')
    + "\n\nThe README describes the install steps in detail for every platform.")

add("say-not-pointer-keeps-say", "6.6",
    "A real say with long prose after it: say is kept.",
    fence('{"say": "The build passes on all platforms.", "actions": []}')
    + "\n\nI also checked the lint output, and it is clean apart from two unused imports.")

add("say-over-40-chars-not-pointer", "6.6",
    "A say longer than 40 characters that starts with a pointer phrase is not a pointer.",
    fence('{"say": "See below for the complete list of every file that changed in this commit.", "actions": []}')
    + "\n\nThe commit touches the parser, the tests and the README, in that order.")

# ---------------------------------------------------------------- 6.8 plan and milestone
add("plan-strings", "6.8",
    "plan as an array of strings.",
    fence('{"say": "Here is my plan.", "plan": ["Read the parser", "Write the tests", "Fix the failures"]}'))

add("plan-objects-title", "6.8",
    "plan as objects with a title key; the extra key is ignored.",
    fence('{"plan": [{"title": "Survey the code", "detail": "read the parser"}, {"title": "Add tests"}]}'))

add("plan-objects-step", "6.8",
    "plan as objects with a step key.",
    fence('{"say": "Plan.", "plan": [{"step": "Reproduce the bug"}, {"step": "Patch and verify"}]}'))

add("milestones-key-alias", "6.8",
    "The list is under the key milestones and is read as the plan.",
    fence('{"say": "Plan.", "milestones": ["Schema", "API", "UI"]}'))

add("milestone-integer", "6.8",
    "milestone as an integer, on a reply that finishes milestone 1.",
    fence('{"say": "Schema is done.", "milestone": 1, "actions": []}'))

add("milestone-string-number", "6.8",
    "milestone given as the string \"2\".",
    fence('{"say": "API done.", "milestone": "2", "actions": [{"tool": "shell", "args": {"command": "make"}}]}'))

add("plan-blank-entries-trimmed", "6.8",
    "Blank plan entries are dropped and the rest are trimmed.",
    fence('{"plan": ["  Read the code  ", "", "   ", {"title": ""}, {"step": "Ship"}]}'))

# ---------------------------------------------------------------- 6.3 strings: unicode, escapes, size
add("unicode-emoji-say-and-args", "6.3",
    "Emoji in say and in an edit: they pass through unchanged.",
    fence(dumps({"say": "Adding the rocket \U0001F680 to the banner \U0001F389.", "actions": [{"tool": "edit_file", "args": {"path": "banner.html", "find": "Launch", "replace": "Launch \U0001F680"}}]})))

add("unicode-cjk-content", "6.3",
    "CJK text in a file content string.",
    fence(dumps({"say": "Writing a greeting file.", "actions": [{"tool": "write_file", "args": {"path": "greeting.txt", "content": "\u4f60\u597d\uff0c\u4e16\u754c\n\u65e5\u672c\u8a9e\u306e\u30c6\u30ad\u30b9\u30c8\n\ud55c\uad6d\uc5b4\n"}}]})))

add("unicode-escaped-sequences", "6.3",
    "JSON \\u escapes for a non-ASCII letter and a symbol are decoded.",
    '```json\n{"say": "Caf\\u00e9 check.", "actions": [{"tool": "write_file", "args": {"path": "menu.txt", "content": "Caf\\u00e9 \\u2603"}}]}\n```')

add("unicode-surrogate-pair-escape", "6.3",
    "A surrogate pair escape (an emoji written as \\ud83d\\ude00) is decoded.",
    '```json\n{"say": "Smile.", "actions": [{"tool": "write_file", "args": {"path": "smile.txt", "content": "\\ud83d\\ude00"}}]}\n```')

add("large-content-string", "6.3",
    "A write_file content of about 7000 characters: it passes through whole.",
    fence(dumps({"say": "Writing the report.", "actions": [{"tool": "write_file", "args": {
        "path": "report.txt",
        "content": "".join("Line %04d of the generated report, with some padding text.\n" % i for i in range(120))}}], "done": False})))

add("backslashes-and-quotes-in-content", "6.3",
    "Backslashes, escaped quotes and a Windows path inside a content string.",
    fence(dumps({"say": "Writing the path note.", "actions": [{"tool": "write_file", "args": {
        "path": "notes\\win.txt",
        "content": 'He typed "C:\\Users\\me" and then the pattern \\d+ matched.\n'}}], "done": False})))

add("regex-backslashes-in-args", "6.3",
    "Regex escapes in a grep pattern argument are kept exactly.",
    fence(dumps({"say": "Searching for versions.", "actions": [{"tool": "grep", "args": {"pattern": "\\d+\\.\\w+\\s*=\\s*\"[^\"]*\""}}]})))


add("fence-repairable-first-loses-to-valid-second", "6.1",
    "The first fence is missing a closing bracket and needs structural repair; the second fence is valid JSON and wins because step 1 only accepts strictly valid bodies.",
    fence('{"say": "First try.", "actions": [{"tool": "shell", "args": {"command": "ls"}}'
          )
    + "\n" + fence('{"say": "Second try.", "actions": [{"tool": "shell", "args": {"command": "pwd"}}], "done": false}'))

add("shape-tool-calls-key-only", "6.2",
    "An object whose only reply key is tool_calls is reply-shaped.",
    fence('{"tool_calls": [{"name": "shell", "arguments": {"command": "ls"}}]}'))

add("pointer-below-prefix-long-after", "6.6",
    "A say that starts with the pointer word below (under 40 characters) counts as a pointer.",
    fence('{"say": "Below is the fix I applied.", "actions": []}')
    + "\n\nThe off-by-one was in the loop bound, which now stops at the last index.")

add("pointer-here-it-is-long-after", "6.6",
    "A say that starts with here it is (under 40 characters) counts as a pointer.",
    fence('{"say": "Here it is: the full config", "actions": []}')
    + "\n\nThe config sets the port to 8080 and enables TLS with the bundled certificate.")

add("pointer-after-exactly-40-chars-kept", "6.7",
    "Boundary: exactly 40 characters after the block do not replace the pointer (the rule is more than 40).",
    fence('{"say": "Answered below.", "actions": []}') + "\n\n" + "abcdefghij" * 4)

add("pointer-after-41-chars-replaces", "6.7",
    "Boundary: 41 characters after the block replace the pointer.",
    fence('{"say": "Answered below.", "actions": []}') + "\n\n" + "abcdefghij" * 4 + "k")

def main():
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate ids"
    out = os.path.join(HERE, "cases.src.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("wrote %d cases to %s" % (len(cases), out))


if __name__ == "__main__":
    main()
