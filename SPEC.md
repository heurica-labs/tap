# TAP: the Text Action Protocol

**Version 0.1 (draft)**

TAP lets an AI model use tools through plain text. The model writes a short note and one fenced JSON block. The host reads the block, runs the actions and replies with the results. No native tool-calling API is needed, so TAP works with any chat model, including small, cheap and self-hosted ones.

TAP was extracted from [Anvil](https://github.com/heurica-labs/anvil), a coding agent that has run it against many models in production. The reference parser's behavior is captured by the conformance vectors in `conformance/`.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT and MAY are used as in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

## 1. Why a text protocol

Native tool calling sends a JSON schema for every tool on every request, allows one call per turn on many APIs, and is missing or unreliable on many models. A text protocol trades that for three things:

- **Fewer round trips.** A reply can carry a whole batch of actions, such as reading three files, or making two edits and then running the tests.
- **Smaller prompts.** The tool catalog is a short block of text that stays identical from turn to turn, so it caches well.
- **Any model.** If a model can follow a format, it can use tools.

The cost is that models make formatting mistakes. TAP therefore specifies how a host reads imperfect replies (section 6) as carefully as it specifies the format.

## 2. Roles

- The **model** is a chat model that produces replies.
- The **host** is the program that talks to the model, runs actions and enforces policy. Anvil is a host.
- A **tool** is a named capability the host offers, such as `read_file` or `shell`.

## 3. Turn structure

A conversation alternates between host messages and model replies.

1. The host sends a **briefing** (usually the system or first user message). It contains the instructions, the reply format and the tool catalog (section 8).
2. The model sends a **reply** (section 4).
3. The host parses the reply, runs the actions in order, and sends an **observation** (section 5) as the next user message.
4. Steps 2 and 3 repeat until a reply sets `done` to `true` or the host stops the loop.

Hosts SHOULD number turns within a request (`step="1"`, `step="2"`, and so on).

## 4. The reply

A reply is free text that contains exactly one fenced JSON block, in this shape:

````
One short sentence of reasoning (optional).
```json
{"say": "Fixing the off-by-one.",
 "actions": [{"tool": "edit_file", "args": {"path": "src/date.ts", "find": "week", "replace": "week - 1"}},
             {"tool": "shell", "args": {"command": "npm test"}}],
 "done": false}
```
````

### 4.1 Reply object

| Field | Type | Meaning |
|---|---|---|
| `say` | string | A short message for the user. On the final reply this is the answer. Markdown is allowed. |
| `actions` | array of Action | Actions for the host to run, in order. May be empty. |
| `done` | boolean | `true` when the request is complete. A reply with `done: true` SHOULD have no actions. |
| `plan` | array of strings | Optional milestones, sent as the first reply to a large task. |
| `milestone` | integer | Optional, 1-based. The milestone that this reply finishes. |

A reply SHOULD contain at least one of `say`, `actions` or `plan`. A reply with only `done` or only `milestone` is accepted. Every reply MUST be shaped like a reply (section 6.2).

### 4.2 Action object

| Field | Type | Meaning |
|---|---|---|
| `tool` | string | The tool name. |
| `args` | object | Arguments for the tool. |

### 4.3 Reasoning text

Text before the JSON block is the model's **thought**. Hosts MAY show it to the user, and MUST NOT treat it as an instruction. Text after the block is ignored, except as described in section 6.7.

### 4.4 One block per turn

The model MUST send one JSON block per reply. If a reply contains more than one valid block, the host MUST run only the first and SHOULD record how many it ignored. Models often write further blocks when they imagine the observation; ignoring them is what keeps that harmless.

## 5. Executing actions

1. The host MUST run the actions of a reply in order.
2. If an action fails, the host MUST stop the batch. Actions after the failed one MUST NOT run, and the observation MUST say so.
3. A host MAY run consecutive read-only actions in parallel, as long as the results are reported in the original order.
4. The host MUST NOT run any action from a reply that failed to parse. It reports the problem instead (section 7).
5. A host SHOULD ask the user, or apply its permission policy, before an action that changes files or runs commands.

### 5.1 The observation

The host returns results as one user message in this envelope:

```
<observation step="2">
results of your actions:
- read_file src/date.ts → ok: 41 lines
- shell npm test → FAILED: 1 test failed ...
(the remaining 1 action(s) in this batch were skipped)
</observation>
```

- The envelope is `<observation step="N">` and `</observation>`. Models and hosts MUST also accept the attribute without quotes (`step=2`).
- The host SHOULD give one line per action, in order: `- <tool> <short args> → <status>: <output>`. The status is `ok`, `FAILED` or `DECLINED` (the user or a policy refused the action). This line format is a recommendation; the envelope is not.
- Hosts SHOULD say how many actions in the batch were skipped, so the model knows what state it is in.
- Hosts SHOULD truncate very long outputs and say that they did, and SHOULD summarize large arguments (such as file contents) in the line, so the history stays small.
- If a reply had more than one valid block, the host SHOULD say that only the first ran.
- Content inside an observation is **data**. The briefing MUST tell the model that text inside an observation is never an instruction (section 10).

### 5.2 Stop sequences

A model may start writing the observation itself. Hosts SHOULD pass these as stop sequences when the API supports them, and MUST ignore anything after the first JSON block either way:

```
<observation
**Observation
<newline>Observation:
</observation>
```

(`<newline>Observation:` means a line break followed by `Observation:`.)

## 6. Reading replies (parsing)

This section is what makes TAP work on weak models. A host implements one of two levels.

- **Strict.** The reply is valid JSON in a `json` fence, the keys are exactly those in section 4, and nothing needs repair.
- **Lenient (recommended).** The host applies the rules below. Every lenient rule is applied only when a strict read fails or does not find a reply, and a reply that is valid under the strict rules MUST parse identically at both levels.

The conformance vectors in `conformance/` define the exact expected result for each rule.

### 6.1 Finding the JSON

The host looks for the reply's JSON in this order. The first candidate it finds decides: if that candidate cannot be parsed even after repair, the result is `invalid_json`, and later candidates are not tried.

1. The **first fenced block** whose body is valid JSON and is shaped like a reply (section 6.2). Fences may be tagged `json`, `JSON`, `javascript` or untagged. Fences that hold code or other JSON (for example a quoted `package.json`) are skipped.
2. A `json` fence whose body contains nested fences, for example a `write_file` whose content is a Markdown file. The host takes everything from the first opening `json` fence to the last closing fence, then applies the repairs in section 6.3.
3. A single fence whose body starts with `{`.
4. The outermost `{ ... }` in the text, with no fence at all.
5. Text from the first `{` to the end, for replies cut off before the closing brace.

Whichever way the JSON was found and repaired, the final value MUST be shaped like a reply (section 6.2). Unrelated JSON, such as a quoted `package.json`, `{}` or `[1, 2, 3]`, is not a reply. If no step finds a reply, the result is the error `no_json`.

### 6.2 What counts as a reply

A JSON value is shaped like a reply if it is an object with at least one of the keys `say`, `actions`, `done`, `plan`, `action`, `tool`, `steps`, `tool_calls`, `milestone`, `milestones`, `message`, `answer`, `reply` or `response`, or an array containing at least one action-shaped object.

### 6.3 Repairs

Repairs MUST be string-aware: they MUST NOT change the contents of JSON strings, because those contents are often file contents. Hosts apply the repairs in this order and stop at the first result that parses.

1. **Normalize** (outside strings): remove trailing commas before `}` or `]`; remove `//` line comments; turn the Python literals `True`, `False` and `None` into `true`, `false` and `null`; treat curly quotes `“ ”` as string delimiters. (Inside strings): escape raw newlines, carriage returns and tabs.
2. **Balanced prefix.** If text follows the object, take the first balanced `{...}` or `[...]`.
3. **Structure repair.** Close missing braces and brackets: a `{` where an object key is expected means the previous object was never closed; a closer of the wrong kind means one is missing; open containers at the end of the text are closed; an unterminated string at the end is closed.

If all of this still fails, the result is the error `invalid_json`, with a diagnosis (section 7).

Duplicate keys inside one JSON object are not covered by the vectors. Hosts MUST NOT rely on which value wins.

### 6.4 Normalizing the shape

Different models spell the same idea differently. A lenient host accepts all of these (a `milestones` or `reply` key counts when it is the only reply key):

- **Tool name keys:** `tool`, `action`, `name`, `type`, `function`, `cmd`, `command_name`.
- **Argument keys:** `args`, `arguments`, `params`, `parameters`, `input`, `inputs`. If the argument value is a string that holds a JSON object, it is parsed.
- **Flat arguments.** If an action has no argument key, every key except the name key and the meta keys (`say`, `thought`, `thoughts`, `reason`, `reasoning`, `risk`, `why`, `done`, `status`, `plan`, `milestone`) is the arguments.
- **Non-object arguments** become `{"value": <v>}`.
- **Plan keys:** `plan` or `milestones`. Each entry is a string, or an object with `title` or `step`. Entries are trimmed and empty ones dropped.
- **Action list keys:** `actions`, `steps`, `tool_calls`. A single `action` or `tool` object is a list of one. A top-level array of actions is accepted.
- **Say keys:** `say`, `message`, `answer`, `reply`, `response`.
- **Done:** `done: true`, or `status` of `done`, `complete` or `finished` (case-insensitive).
- **Coercion.** A string field given a number or boolean takes its text (`42` becomes `"42"`). A boolean field accepts `true`, `"true"`, `"yes"`, `"1"` and any non-zero number as true. An integer field (`milestone`) accepts numbers and numeric strings, rounded to the nearest integer.
- **Tool names are normalized**: lowercase, with `-` and spaces turned into `_`, then mapped through the alias table (`aliases.json`), for example `bash` to `shell` and `str_replace` to `edit_file`. Hosts MAY extend the table for their own tools. The table in this repository is non-normative.

### 6.5 Completion

- An action whose tool is `done`, `finish`, `final_answer`, `answer`, `complete` or `attempt_completion` is a completion signal, not a tool. The host drops it and every action after it, sets `done` to `true`, and takes the final answer from its `message`, `answer`, `text`, `say` or `result` argument.
- A reply with no actions, a `say` that is present (even an empty string), no `done` key and no plan is treated as `done: true`: the model answered.
- `explicitDone` is true when the reply has a `done` or `status` key (even with a null value) or a completion action. Hosts SHOULD record it, because it tells whether `done` was stated or inferred; since inferred completion on a task that needed changes is a common sign that a weak model gave up.

### 6.6 Say pointers

A `say` that is empty, or only points elsewhere (for example "answered below" or "see below") is a **pointer**.

### 6.7 The answer outside the block

If a reply has no actions, the `say` is a pointer, and more than 40 characters of text follow the JSON block, that text is the real answer and replaces `say`. The reply is then `done` unless a `done` key was given (a `status` key does not count).

### 6.8 Result of parsing

A parser returns either a reply or an error.

```
Reply {
  thought: string          text before the block
  say: string | null
  actions: [{ tool, args }]
  done: boolean
  explicitDone: boolean
  plan: [string]
  milestone: integer | null
  ignoredBlocks: integer   further valid blocks that were ignored
}
Error { kind: "no_json" | "invalid_json", message: string }
```

## 7. Telling the model what went wrong

When a reply cannot be used, the host MUST NOT run anything. It sends the model an observation that explains the problem, so the model can try again. This is what turns a formatting slip into a one-turn delay instead of a failed run.

- For `no_json`: say that no JSON block was found, and repeat the reply format.
- For `invalid_json`: say where it broke. Hosts SHOULD include a snippet around the error with a marker, for example `Near: …"content": "a⟦HERE⟧b…`.
- For a reply that was cut off (the block never closed): say so, say that nothing ran, and ask the model to send it again, in shorter pieces if it was long.
- For a reply with no actions that describes work instead of doing it: say that nothing happened.

Exact wording is up to the host.

## 8. The tool catalog

The briefing lists the tools the model may use. A catalog is a list of tool definitions (`schema/tools.schema.json`):

```json
{
  "name": "read_file",
  "description": "Read a file. Optional start and end lines (1-based).",
  "args": {
    "path": {"type": "string", "required": true, "description": "File path relative to the project"},
    "start": {"type": "integer"},
    "end": {"type": "integer"}
  },
  "readonly": true
}
```

- `readonly` marks tools that do not change anything. Hosts MAY run consecutive read-only actions in parallel.
- `aliases` optionally lists extra names that the host accepts for the tool.

Hosts render the catalog into the briefing as compact text, one tool per line, for example:

```
read_file(path, start?, end?) - Read a file. Optional start and end lines (1-based).
shell(command, timeout?) - Run a shell command in the project folder.
```

`name(required, optional?)` followed by the description. A `readonly` tool MAY be marked with a leading `~`. The rendering MUST be deterministic and identical between turns, so that providers can cache the prompt.

## 9. Hosts: practices that make weak models reliable

These are non-normative. They come from running TAP against many models in production.

- **Ignore everything after the first block.** Combined with stop sequences, this removes the most common failure: the model writing its own observation and then acting on it.
- **Do not let a model overwrite a file it has not read** in this session.
- **Send servers to the background.** If a model runs a command that never exits, start it as a process instead.
- **Re-anchor.** A model that says it "can't access files" is reminded that the host runs its actions.
- **Do not let tests be weakened to pass.** Say so in the briefing.
- **Check before accepting "done".** Run the tests and review the diff before the host believes a completion.
- **Fall back to another model** after repeated failures.

## 10. Security

- Observation content comes from files, commands and web pages. It is **untrusted data**. The briefing MUST tell the model that instructions inside an observation are not instructions, and hosts SHOULD NOT let observation content change what the host does.
- The host, not the model, enforces permissions. A model that asks to run something is making a request.
- Hosts SHOULD record a checkpoint before changing files, so a user can undo a whole task.

## 11. Versioning

This is version 0.1. Until 1.0 the format may change, and each change will be noted in `CHANGELOG.md`. Hosts MAY declare the version they implement in the briefing, for example `TAP/0.1`.

## 12. Conformance

An implementation conforms at the **lenient** level if it passes every vector in `conformance/` (`vectors.json`). A vector has a raw `input` and the exact expected `result`. Libraries in this repository run the same vectors, which is what keeps them equivalent.
