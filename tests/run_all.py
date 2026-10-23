"""Run the tests without pytest: python tests/run_all.py"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_ui  # noqa: E402

failed = 0
for name in sorted(n for n in dir(test_ui) if n.startswith("test_")):
    try:
        getattr(test_ui, name)()
        print("ok   ", name)
    except Exception:
        failed += 1
        print("FAIL ", name)
        traceback.print_exc()
print("%d failed" % failed)
sys.exit(1 if failed else 0)
