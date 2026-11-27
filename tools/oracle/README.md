# Conformance oracle

`ActionParser.swift` and `JSON.swift` are copied unmodified from [Anvil](https://github.com/heurica-labs/anvil) (`Anvil/Brain/`), the reference host. `main.swift` runs the parser over a list of cases and prints the structured result. This is how `conformance/vectors.json` was generated.

```bash
swiftc -O -o oracle main.swift ActionParser.swift JSON.swift
./oracle ../../conformance/cases.src.json > /tmp/out.json
```

The copied Anvil sources are © Heurica and are included here under this repository's MIT license.
