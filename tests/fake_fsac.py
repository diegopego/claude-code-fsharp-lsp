#!/usr/bin/env python3
"""A stand-in for the fsautocomplete binary, for testing check_fsharp_lsp.py.

The check works by EXECUTING the binary rather than looking for it on
disk, so testing it needs something executable that behaves like FSAC's
`--version`. That is all this has to do.

Set FAKE_FSAC_VERSION_FAILS to make it exit non-zero with a runtime error on
stderr — the "present but broken" case, which is the failure that makes the LSP
tool hang instead of reporting anything.
"""

import os
import sys


def main() -> int:
    if "--version" in sys.argv[1:]:
        if os.environ.get("FAKE_FSAC_VERSION_FAILS"):
            print("fake failure: could not resolve runtime", file=sys.stderr)
            return 1
        print("0.0.0-fake")
        return 0

    # check_fsharp_lsp.py never invokes it any other way.
    print(f"fake_fsac: unexpected argv {sys.argv[1:]}", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main())
