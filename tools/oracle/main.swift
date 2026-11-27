// TAP conformance oracle. Reads a JSON array of {"id", "description", "input"} from the file given as argv[1]
// and prints a JSON array of {"id", "description", "input", "result"} where result is the reference parser's output
// (the parser is Anvil's ActionParser.swift, copied unmodified next to this file).
import Foundation

func j(_ v: JSON?) -> Any { v?.anyValue ?? NSNull() }

let path = CommandLine.arguments[1]
let data = try! Data(contentsOf: URL(fileURLWithPath: path))
let cases = try! JSONSerialization.jsonObject(with: data) as! [[String: Any]]
var out: [[String: Any]] = []
for c in cases {
    var item = c
    let input = c["input"] as! String
    do {
        let r = try ActionParser.parse(input)
        item["result"] = [
            "ok": true,
            "reply": [
                "thought": r.thought,
                "say": r.say as Any? ?? NSNull(),
                "actions": r.actions.map { ["tool": $0.tool, "args": $0.args.anyValue] as [String: Any] },
                "done": r.done,
                "explicitDone": r.explicitDone,
                "plan": r.plan,
                "milestone": r.milestone as Any? ?? NSNull(),
                "ignoredBlocks": r.ignoredBlocks,
            ] as [String: Any],
        ] as [String: Any]
    } catch let e as ParseError {
        switch e {
        case .noJSON: item["result"] = ["ok": false, "error": ["kind": "no_json"]] as [String: Any]
        case .invalid(let m): item["result"] = ["ok": false, "error": ["kind": "invalid_json", "message": m]] as [String: Any]
        }
    } catch { item["result"] = ["ok": false, "error": ["kind": "invalid_json"]] as [String: Any] }
    out.append(item)
}
let o = try! JSONSerialization.data(withJSONObject: out, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])
FileHandle.standardOutput.write(o)
