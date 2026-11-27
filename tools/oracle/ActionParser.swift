import Foundation

nonisolated struct AgentAction: Sendable, Equatable {
    var tool: String
    var args: JSON
}

nonisolated struct AgentReply: Sendable {
    var thought: String
    var say: String?
    var actions: [AgentAction]
    var done: Bool
    /// Milestones proposed before starting a big task (shown to the owner for approval).
    var plan: [String] = []
    /// 1-based milestone just finished.
    var milestone: Int?
    /// More JSON blocks followed the first one (the model kept writing past its turn); they were ignored.
    var ignoredBlocks = 0
    /// The reply said done explicitly (a "done" key or a done action), rather than done being inferred.
    var explicitDone = false
}

nonisolated enum ParseError: Error, CustomStringConvertible {
    case noJSON, invalid(String)
    var description: String {
        switch self {
        case .noJSON: return "no ```json block found"
        case .invalid(let s): return "the json block is not valid JSON: \(s)"
        }
    }
}

/// Lenient parser for the model's "reasoning + ```json block" replies (ported from Peep, coding aliases).
nonisolated enum ActionParser {
    static let nameKeys = ["tool", "action", "name", "type", "function", "cmd", "command_name"]
    static let argKeys = ["args", "arguments", "params", "parameters", "input", "inputs"]
    static let metaKeys: Set<String> = ["say", "thought", "thoughts", "reason", "reasoning", "risk", "why", "done", "status", "plan", "milestone"]
    static let completionNames: Set<String> = ["done", "finish", "final_answer", "answer", "complete", "attempt_completion"]

    static func parse(_ raw: String) throws -> AgentReply {
        let (jsonText, before, after, extra) = try extractJSON(raw)
        guard let json = parseLenient(jsonText) else { throw ParseError.invalid(diagnose(escapeNewlinesInStrings(jsonText))) }
        var reply = AgentReply(thought: before, say: nil, actions: [], done: false)
        reply.ignoredBlocks = extra
        reply.explicitDone = json["done"] != nil || json["status"] != nil

        switch json {
        case .array(let items):
            reply.actions = items.compactMap(action(from:))
        case .object(let o):
            reply.say = (o["say"] ?? o["message"] ?? o["answer"] ?? o["reply"] ?? o["response"])?.string
            reply.done = o["done"]?.bool ?? (o["status"]?.string.map { ["done", "complete", "finished"].contains($0.lowercased()) } ?? false)
            reply.plan = (o["plan"]?.array ?? o["milestones"]?.array ?? []).compactMap { $0.string ?? $0["title"]?.string ?? $0["step"]?.string }
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
            reply.milestone = o["milestone"]?.int
            if let list = (o["actions"] ?? o["steps"] ?? o["tool_calls"])?.array {
                reply.actions = list.compactMap(action(from:))
            } else if let a = o["action"]?.object ?? o["tool"]?.object {
                reply.actions = action(from: .object(a)).map { [$0] } ?? []
            } else if let a = action(from: json) {
                reply.actions = [a]
            }
        default:
            throw ParseError.invalid("top level must be an object")
        }

        // A "done" action is a completion signal, not a tool.
        if let i = reply.actions.firstIndex(where: { completionNames.contains($0.tool) }) {
            let a = reply.actions[i]
            let msg = a.args["message"]?.string ?? a.args["answer"]?.string ?? a.args["text"]?.string ?? a.args["say"]?.string ?? a.args["result"]?.string
            if let msg, !msg.isEmpty { reply.say = msg }
            reply.actions = Array(reply.actions[..<i])
            reply.done = true
            reply.explicitDone = true
        }
        if reply.actions.isEmpty && reply.say != nil && json["done"] == nil && reply.plan.isEmpty { reply.done = true }
        // The model wrote its answer as prose after the json block (say was empty or just "answered below").
        // For a final answer with no actions, that prose is the real answer; keep it instead of the pointer.
        if reply.actions.isEmpty, !after.isEmpty, after.count > 40, isPointer(reply.say) {
            reply.say = after
            if json["done"] == nil { reply.done = true }
        }
        return reply
    }

    /// A `say` that's empty or just points elsewhere ("answered below", "see below", "as follows:").
    static func isPointer(_ say: String?) -> Bool {
        let t = (say ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if t.isEmpty { return true }
        guard t.count <= 40 else { return false }
        let pointers = ["answered below", "see below", "below", "as follows", "here you go", "here it is", "response below", "answer below", "details below", "here's the answer", "here is the answer"]
        return pointers.contains { t.hasPrefix($0) || t == $0 || t == $0 + "." || t == $0 + ":" }
    }

    static func action(from j: JSON) -> AgentAction? {
        guard case .object(let o) = j else { return nil }
        guard let nameKey = nameKeys.first(where: { o[$0]?.string != nil }), let name = o[nameKey]?.string else { return nil }
        var args: JSON
        if let k = argKeys.first(where: { o[$0] != nil }), let a = o[k] {
            if case .string(let s) = a, let inner = parseLenient(s), case .object = inner { args = inner } else { args = a }
        } else {
            var flat = o
            flat.removeValue(forKey: nameKey)
            for k in metaKeys { flat.removeValue(forKey: k) }
            args = .object(flat)
        }
        if case .object = args {} else { args = .object(["value": args]) }
        return AgentAction(tool: normalize(name), args: args)
    }

    static func normalize(_ name: String) -> String {
        let n = name.lowercased().trimmingCharacters(in: .whitespaces)
            .replacingOccurrences(of: "-", with: "_").replacingOccurrences(of: " ", with: "_")
        let aliases = [
            "bash": "shell", "run_shell": "shell", "terminal": "shell", "run_command": "shell", "execute_command": "shell", "sh": "shell", "zsh": "shell", "run": "shell",
            "read": "read_file", "cat": "read_file", "view": "read_file", "open_file": "read_file", "view_file": "read_file",
            "write": "write_file", "create_file": "write_file", "save_file": "write_file",
            "edit": "edit_file", "str_replace": "edit_file", "replace_in_file": "edit_file", "str_replace_editor": "edit_file", "apply_edit": "edit_file",
            "multiedit": "multi_edit", "multi_edit_file": "multi_edit", "edits": "multi_edit",
            "ls": "list_dir", "list_files": "list_dir", "list_directory": "list_dir", "dir": "list_dir",
            "search_code": "grep", "search_files": "grep", "ripgrep": "grep", "rg": "grep", "code_search": "grep",
            "find_files": "glob", "find": "glob", "file_search": "glob",
            "search_web": "web_search", "google": "web_search", "websearch": "web_search", "fetch": "fetch_url", "curl": "fetch_url", "webfetch": "fetch_url",
            "todos": "todo_write", "update_todos": "todo_write", "todowrite": "todo_write", "todo": "todo_write",
            "start_background": "start_process", "background": "start_process", "run_background": "start_process",
            "kill_process": "stop_process", "process_output": "read_process", "sleep": "wait",
            "rm": "delete_file", "remove_file": "delete_file",
        ]
        return aliases[n] ?? n
    }

    /// Finds the JSON payload: the FIRST fence holding valid JSON (anything after it is the model running ahead of
    /// its turn, e.g. imagining the observation), else the last ```json fence, else the outermost {...}.
    /// Returns the JSON text, the reasoning before it, and how many further JSON blocks were ignored.
    /// Returns (jsonText, text before the block, text after the block, count of extra blocks ignored).
    static func extractJSON(_ raw: String) throws -> (String, String, String, Int) {
        let fence = try! NSRegularExpression(pattern: "```(?:json|JSON|javascript)?[ \\t]*\\n?([\\s\\S]*?)```")
        let ns = NSString(string: raw)
        let matches = fence.matches(in: raw, range: NSRange(location: 0, length: ns.length))
        var valid: [(String, Int)] = []
        for m in matches {
            let body = ns.substring(with: m.range(at: 1)).trimmingCharacters(in: .whitespacesAndNewlines)
            // Only a fence that really is our JSON (code in other fences may also start with "{").
            if body.hasPrefix("{") || body.hasPrefix("["), let j = parseLenient(body, repair: false), isReply(j) {
                valid.append((body, m.range.location))
            }
        }
        if let first = valid.first {
            let before = ns.substring(to: first.1).trimmingCharacters(in: .whitespacesAndNewlines)
            // Text after the first block's closing fence (an answer the model wrote outside the json).
            let firstMatch = matches.first { $0.range.location == first.1 }
            let after = firstMatch.map { ns.substring(from: $0.range.location + $0.range.length).trimmingCharacters(in: .whitespacesAndNewlines) } ?? ""
            return (first.0, before, after, valid.count - 1)
        }
        // The JSON fence may contain nested ``` (markdown inside a write_file content) or be slightly broken:
        // take everything from the first "```json" opener to the closing fence and let the repairs handle it.
        if let r = raw.range(of: "```json") ?? raw.range(of: "```JSON") {
            var body = String(raw[r.upperBound...])
            if let close = body.range(of: "\n```", options: .backwards) ?? body.range(of: "```", options: .backwards) { body = String(body[..<close.lowerBound]) }
            body = body.trimmingCharacters(in: .whitespacesAndNewlines)
            if body.hasPrefix("{") || body.hasPrefix("[") {
                return (body, String(raw[..<r.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines), "", 0)
            }
        }
        if matches.count == 1 {
            let body = ns.substring(with: matches[0].range(at: 1)).trimmingCharacters(in: .whitespacesAndNewlines)
            if body.hasPrefix("{") { return (body, ns.substring(to: matches[0].range.location).trimmingCharacters(in: .whitespacesAndNewlines), "", 0) }
        }
        // No fence: take the outermost object.
        if let start = raw.firstIndex(of: "{"), let end = raw.lastIndex(of: "}"), start < end {
            return (String(raw[start...end]), String(raw[..<start]).trimmingCharacters(in: .whitespacesAndNewlines), "", 0)
        }
        if let start = raw.firstIndex(of: "{") {   // cut off before the closing brace
            return (String(raw[start...]), String(raw[..<start]).trimmingCharacters(in: .whitespacesAndNewlines), "", 0)
        }
        throw ParseError.noJSON
    }

    /// A JSON value shaped like a reply (not, say, a package.json the model quoted).
    static func isReply(_ j: JSON) -> Bool {
        if case .array(let a) = j { return a.contains { action(from: $0) != nil } }
        guard let o = j.object else { return false }
        let keys: Set<String> = ["say", "actions", "done", "plan", "action", "tool", "steps", "tool_calls", "milestone", "message", "answer"]
        return !keys.isDisjoint(with: o.keys)
    }

    static func parseLenient(_ s: String, repair: Bool = true) -> JSON? {
        if let j = JSON.parse(s) { return j }
        // All repairs are string-aware: file contents inside JSON strings (Python True, JS trailing commas,
        // // comments) must never be rewritten.
        let t = normalizeJSON(s)
        if let j = JSON.parse(t) { return j }
        // Some models end with an extra closing brace or text after the object.
        if let j = JSON.parse(balancedPrefix(t)) { return j }
        // Missing braces (a forgotten "}" after an action's args, or a reply cut off at the end).
        if repair, let j = JSON.parse(repairStructure(t)) { return j }
        return nil
    }

    /// Outside strings: smart quotes become quotes, trailing commas and // comments go, Python literals become JSON.
    /// Inside strings: raw newlines, carriage returns and tabs are escaped. String contents are otherwise untouched.
    static func normalizeJSON(_ s: String) -> String {
        var out = ""
        out.reserveCapacity(s.count)
        let chars = Array(s)
        var i = 0
        var inString = false, escaped = false, smart = false
        while i < chars.count {
            let c = chars[i]
            if inString {
                if escaped { escaped = false; out.append(c) }
                else if c == "\\" { escaped = true; out.append(c) }
                else if (!smart && c == "\"") || (smart && c == "\u{201D}") { inString = false; out.append("\"") }
                else if smart && c == "\"" { out += "\\\"" }
                else if c == "\n" { out += "\\n" }
                else if c == "\r" { out += "\\r" }
                else if c == "\t" { out += "\\t" }
                else { out.append(c) }
                i += 1
                continue
            }
            switch c {
            case "\"":
                inString = true; smart = false; out.append(c)
            case "\u{201C}", "\u{201D}":
                inString = true; smart = true; out.append("\"")
            case ",":
                // Trailing comma: next non-space character closes the container.
                var k = i + 1
                while k < chars.count, chars[k].isWhitespace { k += 1 }
                if k < chars.count, chars[k] == "}" || chars[k] == "]" { i += 1; continue }
                out.append(c)
            case "/" where i + 1 < chars.count && chars[i + 1] == "/":
                while i < chars.count, chars[i] != "\n" { i += 1 }
                continue
            default:
                if c.isLetter, i == 0 || !(chars[i - 1].isLetter || chars[i - 1].isNumber || chars[i - 1] == "_") {
                    var k = i
                    while k < chars.count, chars[k].isLetter || chars[k].isNumber || chars[k] == "_" { k += 1 }
                    let word = String(chars[i..<k])
                    out += ["True": "true", "False": "false", "None": "null"][word] ?? word
                    i = k
                    continue
                }
                out.append(c)
            }
            i += 1
        }
        return out
    }

    /// The first balanced {...} or [...] at the start of `s` (string-aware).
    static func balancedPrefix(_ s: String) -> String {
        var depth = 0, inString = false, escaped = false
        var out = ""
        for c in s {
            out.append(c)
            if inString {
                if escaped { escaped = false } else if c == "\\" { escaped = true } else if c == "\"" { inString = false }
                continue
            }
            if c == "\"" { inString = true } else if c == "{" || c == "[" { depth += 1 } else if c == "}" || c == "]" {
                depth -= 1
                if depth == 0 { return out }
            }
        }
        return s
    }

    static func escapeNewlinesInStrings(_ s: String) -> String { normalizeJSON(s) }

    /// Fixes the structural slips models make in long replies: a "{" where an object key is expected means the
    /// previous object was never closed, a closer of the wrong kind means one is missing, and unclosed containers
    /// at the end are closed.
    static func repairStructure(_ s: String) -> String {
        var out = ""
        var stack: [Character] = []
        var expectKey = false
        var inString = false, escaped = false
        for c in s {
            if inString {
                out.append(c)
                if escaped { escaped = false } else if c == "\\" { escaped = true } else if c == "\"" { inString = false }
                continue
            }
            switch c {
            case "\"":
                inString = true
                if stack.last == "{" && expectKey { expectKey = false }
                out.append(c)
            case "{":
                if stack.last == "{" && expectKey, let comma = out.lastIndex(of: ",") {
                    // `{"tool": "a", "args": {...}, {"tool": "b"...`: close the first object before the comma.
                    out.insert("}", at: comma)
                    stack.removeLast()
                }
                stack.append("{"); expectKey = true; out.append(c)
            case "[":
                stack.append("["); expectKey = false; out.append(c)
            case "}":
                while stack.last == "[" { out.append("]"); stack.removeLast() }
                if !stack.isEmpty { stack.removeLast() }
                expectKey = false; out.append(c)
            case "]":
                while stack.last == "{" { out.append("}"); stack.removeLast() }
                if !stack.isEmpty { stack.removeLast() }
                expectKey = false; out.append(c)
            case ",":
                expectKey = stack.last == "{"; out.append(c)
            case ":":
                expectKey = false; out.append(c)
            default:
                out.append(c)
            }
        }
        if inString { out.append("\"") }
        for open in stack.reversed() { out.append(open == "{" ? "}" : "]") }
        return out
    }

    /// Where the JSON broke, for the retry message (so the model can see its own mistake).
    static func diagnose(_ s: String) -> String {
        guard let data = s.data(using: .utf8) else { return "" }
        do { _ = try JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed]); return "" } catch {
            let desc = (error as NSError).userInfo["NSDebugDescription"] as? String ?? error.localizedDescription
            var snippet = ""
            var offset: Int?
            if let r = desc.range(of: #"character (\d+)"#, options: .regularExpression) { offset = Int(desc[r].filter(\.isNumber)) }
            else if let r = desc.range(of: #"line (\d+), column (\d+)"#, options: .regularExpression) {
                let nums = desc[r].split(whereSeparator: { !$0.isNumber }).compactMap { Int($0) }
                if nums.count == 2 {
                    let lines = s.components(separatedBy: "\n")
                    offset = lines.prefix(max(0, nums[0] - 1)).reduce(0) { $0 + $1.count + 1 } + max(0, nums[1] - 1)
                }
            }
            if let n = offset, n < s.count {
                let i = s.index(s.startIndex, offsetBy: n)
                let lo = s.index(i, offsetBy: -min(80, n)), hi = s.index(i, offsetBy: min(40, s.distance(from: i, to: s.endIndex)))
                snippet = " Near: …\(s[lo..<i])⟦HERE⟧\(s[i..<hi])…"
            }
            return desc + snippet
        }
    }

}
