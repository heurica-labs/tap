# Conformance quirks

Observed behavior of the reference parser (`tools/oracle/oracle`, Anvil's `ActionParser.swift`) that is surprising,
inconsistent with SPEC.md, or looks accidental. The oracle output in `vectors.json` is the truth. These cases were
kept as they are; the expected results were not edited by hand.

## Disagrees with SPEC.md

1. **CRLF inside a string is not escaped (bug).** `repair-raw-crlf-in-string` returns `invalid_json`
   ("Unescaped control character"). Spec 6.3 says raw CR and LF inside strings are escaped. Cause: Swift treats
   `"\r\n"` as one `Character`, so the `c == "\r"` and `c == "\n"` branches in `normalizeJSON` never match. A lone CR
   (`repair-raw-cr-alone-in-string`), a lone LF and a tab all pass.

2. **A non-reply package.json becomes an action.** `unrelated-json-fence-alone` gives
   `actions: [{tool: "anvil_demo", args: {version: "1.0.0"}}]`. Spec 6.1 says fences holding other JSON (a quoted
   `package.json`) are skipped. The fallback path takes any fence that starts with `{`, and `name` is a tool-name key.
   (The same file is correctly skipped when a real reply follows, `package-json-quoted-skipped`.)

3. **Non-reply JSON accepted as an empty reply.** These return `ok` with no say, no actions and `done: false`:
   `json-array-fence-not-actions` (`[1, 2, 3]`), `empty-object-fence` (`{}`), and `shape-milestone-only`
   (`{"milestone": 2}`, which also gives `milestone: 2`). Spec 4.1 says a valid reply MUST contain `say`, `actions` or
   `plan`, so these should fail. `shape-done-key-only` (`{"done": true}`) is also accepted with no say and no actions.

4. **Empty say is inferred as done.** `empty-say-no-prose-inferred-done` (`{"say": "", "actions": []}`) gives `done: true`,
   `explicitDone: false`. Spec 6.5 infers done only for a non-empty say. Cause: the check is `say != nil`, and `""` is non-nil.

5. **`"done": null` counts as explicit.** `repair-python-none-done` (`"done": None`) gives `done: false` and
   `explicitDone: true`. Spec 4.1 says `done` is a boolean, and explicit done suppresses the 6.5 and 6.7 inference, so
   null should behave as an absent key.

6. **The 6.7 pointer rule overrides an explicit status.** `pointer-status-working-long-after`
   (`"status": "working"`, long prose after) gives `done: true` and `explicitDone: true`. The reply is explicit and
   not done, yet 6.7 sets `done` to true. Spec 6.7 says done unless `done` was given explicitly. (`status-working-not-done`
   alone correctly gives `done: false`, but `explicitDone: true`, since `status` counts as explicit.)

7. **Non-string say is converted, and can shadow message.** `say-number-becomes-string` (`"say": 42`) gives `say: "42"`
   (spec says string). `say-object-shadows-message` (`"say": {"text": "Hi"}`, `"message": "Hello there."`) gives
   `say: null`: the `say` key wins with an object, `.string` yields nil, and the message is dropped.

8. **Non-string tool name becomes a string.** `tool-name-number-becomes-string` (`"tool": 5`) gives an action with
   `tool: "5"`. Spec 6.4 says tool names are strings.

9. **done, milestone and plan values are coerced.** `done-string-true` (`"done": "true"`) gives `done: true` and
   `explicitDone: true`. `milestone-string-number` (`"milestone": "2"`) gives `milestone: 2`. `plan-numeric-entries-become-strings`
   (`"plan": [1, 2]`) gives `["1", "2"]`. The spec gives only the types. Lenient, but undocumented.

10. **`milestones` key is accepted.** `milestones-key-alias` reads `milestones` as the plan. Spec 4.1 and 6.8 name only
    `plan`. Either the spec should list this alias or the parser should not read it.

11. **Spec 6.4 points at an alias file that does not exist.** It says the table is in `aliases.json`. The repository
    has no such file; the only table is in `ActionParser.swift`. Also `find` maps to `glob` and `search_files` maps to
    `grep` (`alias-search-family`). These are the table's values and are recorded as such.

## Surprising, but within the spec's wording

12. **`done: true` with actions is kept.** `done-true-with-actions-kept` keeps the shell action and sets `done: true`.
    Spec 4.1 says a done reply SHOULD have no actions, so this is allowed, but a host would run them.

13. **Bare-brace text is `invalid_json`, not `no_json`.** `braces-in-prose-not-json` ("uses {name} and {count}")
    and the single-quote, unquoted-key and bare-word errors all return `invalid_json`. Spec 6.1 step 4 takes the
    outermost `{...}`, so the error kind follows from that step. Spec 6.1 also says `no_json` when nothing is found,
    which can be read the same way. Both readings are plausible; the oracle picks `invalid_json`.

14. **Pointer prefixes are broad.** Any say of 40 characters or fewer that starts with `below` or `here it is` is a
    pointer, so `pointer-below-prefix-long-after` and `pointer-here-it-is-long-after` take the prose after the block.
    Spec 6.6 gives examples, not a prefix rule.

15. **Thought includes earlier code fences.** `swift-fence-before-json` puts the whole swift fence in `thought`. Spec 4.3
    says the thought is the text before the block, so this is correct. Noted only because hosts may show it.

## Coverage gaps

No section 6 rule is left uncovered. Two notes:
- Spec 6.4's alias table cannot be vectored beyond the aliases used in `alias-*` cases, because the table is not
  published (see item 11).
- Section 6 says nothing about parsing a reply whose `say` is not a string or whose `plan` has non-string entries.
  Items 7 and 9 record what the reference does, not what the spec requires.

## Resolutions (decided by the spec author)

- Items 4, 5 and 6 and the coercions listed under "Other quirks" are intended Anvil behavior. SPEC.md was changed to match them (6.4 coercion, 6.5, 6.7, plan keys). The vectors keep the oracle output.
- Item 1 (CRLF) and items 2 and 3 (unrelated JSON accepted as a reply) are bugs in the reference parser. SPEC.md keeps the stricter rule, and four vectors carry the spec-correct result instead of the oracle's: `repair-raw-crlf-in-string`, `unrelated-json-fence-alone`, `json-array-fence-not-actions`, `empty-object-fence`. Each is marked `"divergesFromAnvil": true` and keeps the oracle output under `anvilResult`. Libraries MUST match `result`, not `anvilResult`.
- `{"milestone": 2}` and `{"done": true}` stay accepted: they are shaped like replies (SPEC 4.1, 6.2).

- Item 11 (alias table) is resolved: `aliases.json` now exists with 54 entries.
- Duplicate keys: the reference (Foundation) keeps the first value, `JSON.parse` keeps the last. SPEC 6.3 says the result is unspecified.
