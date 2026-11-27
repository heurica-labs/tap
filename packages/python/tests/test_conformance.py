"""Runs every case in conformance/vectors.json against parse().

Each case is one subTest named by its id, so a failure names the case.
For ok results every reply field is compared through as_dict(). For errors the
kind is compared; the diagnosis text of invalid_json is not part of the contract.
For the four divergesFromAnvil vectors, `result` (the spec behavior) is the
expected value; `anvilResult` is the reference's output and is ignored.
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from heurica_tap import parse  # noqa: E402


def vectors_path():
    env = os.environ.get("TAP_VECTORS")
    if env:
        return env
    return os.path.normpath(os.path.join(HERE, "..", "..", "..", "conformance", "vectors.json"))


class ConformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = vectors_path()
        if not os.path.exists(path):
            raise unittest.SkipTest("conformance vectors not found at %s (set TAP_VECTORS)" % path)
        with open(path, encoding="utf-8") as fh:
            cls.vectors = json.load(fh)

    def test_vectors_are_present(self):
        self.assertGreaterEqual(len(self.vectors), 150)

    def test_every_vector(self):
        for vector in self.vectors:
            with self.subTest(id=vector["id"]):
                expected = vector["result"]
                actual = parse(vector["input"]).as_dict()
                self.assertEqual(actual["ok"], expected["ok"], "ok differs")
                if expected["ok"]:
                    self.assertEqual(actual["reply"], expected["reply"])
                else:
                    self.assertEqual(actual["error"]["kind"], expected["error"]["kind"])

    def test_divergent_vectors_follow_the_spec(self):
        divergent = [v for v in self.vectors if v.get("divergesFromAnvil")]
        self.assertEqual(len(divergent), 4)
        for vector in divergent:
            with self.subTest(id=vector["id"]):
                self.assertNotEqual(vector["result"], vector["anvilResult"])


if __name__ == "__main__":
    unittest.main()
