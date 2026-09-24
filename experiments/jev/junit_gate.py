#!/usr/bin/env python3
"""CI 闸: junit 里 tests>0 · failures=errors=0 · skipped=0(关键测试被 skip 不算过)。纯标准库。"""
import sys
import xml.etree.ElementTree as ET


def main(path: str, min_tests: int = 40) -> int:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root)
    t = sum(int(s.get("tests", 0)) for s in suites); f = sum(int(s.get("failures", 0)) for s in suites)
    e = sum(int(s.get("errors", 0)) for s in suites); sk = sum(int(s.get("skipped", 0)) for s in suites)
    print(f"tests={t} failures={f} errors={e} skipped={sk}")
    if t < min_tests or f or e or sk:
        print(f"JUNIT_GATE_RED: need >= {min_tests} tests, 0 failures/errors/skips", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 40))
