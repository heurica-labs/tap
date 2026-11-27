import Foundation

/// A small, Sendable JSON value used for tool arguments and API payloads.
nonisolated enum JSON: Sendable, Equatable, CustomStringConvertible {
    case null
    case bool(Bool)
    case number(Double)
    case string(String)
    case array([JSON])
    case object([String: JSON])

    init(any value: Any?) {
        switch value {
        case nil, is NSNull: self = .null
        case let n as NSNumber:
#if canImport(Darwin)
            // NSNumber bridges Bool too; tell them apart by objCType.
            if CFGetTypeID(n) == CFBooleanGetTypeID() { self = .bool(n.boolValue) } else { self = .number(n.doubleValue) }
#else
            // No CFBoolean here, and `as? Bool` also matches the numbers 0 and 1. corelibs JSONSerialization makes
            // booleans with objCType "c" and integers with "i"/"q", so tell them apart by that (checked on Swift 6.2).
            if String(cString: n.objCType) == "c" { self = .bool(n.boolValue) } else { self = .number(n.doubleValue) }
#endif
        case let s as String: self = .string(s)
        case let a as [Any]: self = .array(a.map { JSON(any: $0) })
        case let d as [String: Any]: self = .object(d.mapValues { JSON(any: $0) })
        default: self = .string(String(describing: value!))
        }
    }

    static func parse(_ text: String) -> JSON? {
        guard let data = text.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed]) else { return nil }
        return JSON(any: obj)
    }

    var anyValue: Any {
        switch self {
        case .null: return NSNull()
        case .bool(let b): return b
        case .number(let n): return n
        case .string(let s): return s
        case .array(let a): return a.map { $0.anyValue }
        case .object(let o): return o.mapValues { $0.anyValue }
        }
    }

    subscript(key: String) -> JSON? {
        if case .object(let o) = self { return o[key] }
        return nil
    }

    subscript(index: Int) -> JSON? {
        if case .array(let a) = self, a.indices.contains(index) { return a[index] }
        return nil
    }

    var string: String? {
        switch self {
        case .string(let s): return s
        case .number(let n): return n == n.rounded() && abs(n) < 1e15 ? String(Int(n)) : String(n)
        case .bool(let b): return b ? "true" : "false"
        default: return nil
        }
    }

    var double: Double? {
        switch self {
        case .number(let n): return n
        case .string(let s): return Double(s.trimmingCharacters(in: .whitespaces))
        case .bool(let b): return b ? 1 : 0
        default: return nil
        }
    }

    var int: Int? { double.map { Int($0.rounded()) } }

    var bool: Bool? {
        switch self {
        case .bool(let b): return b
        case .number(let n): return n != 0
        case .string(let s): return ["true", "yes", "1"].contains(s.lowercased())
        default: return nil
        }
    }

    var object: [String: JSON]? { if case .object(let o) = self { return o }; return nil }
    var array: [JSON]? { if case .array(let a) = self { return a }; return nil }

    var compact: String {
        guard JSONSerialization.isValidJSONObject(anyValue) || true,
              let data = try? JSONSerialization.data(withJSONObject: anyValue, options: [.fragmentsAllowed, .sortedKeys, .withoutEscapingSlashes]),
              let s = String(data: data, encoding: .utf8) else { return "null" }
        return s
    }

    var description: String { compact }
}

/// Lets specs and other Codable types carry free-form JSON (e.g. a provider plugin's extra body fields).
extension JSON: Codable {
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let b = try? c.decode(Bool.self) { self = .bool(b) }
        else if let n = try? c.decode(Double.self) { self = .number(n) }
        else if let s = try? c.decode(String.self) { self = .string(s) }
        else if let a = try? c.decode([JSON].self) { self = .array(a) }
        else if let o = try? c.decode([String: JSON].self) { self = .object(o) }
        else { throw DecodingError.dataCorruptedError(in: c, debugDescription: "not JSON") }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .null: try c.encodeNil()
        case .bool(let b): try c.encode(b)
        case .number(let n): try c.encode(n)
        case .string(let s): try c.encode(s)
        case .array(let a): try c.encode(a)
        case .object(let o): try c.encode(o)
        }
    }
}
