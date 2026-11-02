"""Generate the deliberately-broken fixture files used to demonstrate healing.

Run once:  python3 make_fixtures.py
Produces fixtures/ with one broken sample per fault domain so humans can
inspect exactly what each healer sees and fixes.
"""

from __future__ import annotations

import os

HERE = os.path.dirname(os.path.abspath(__file__))
FX = os.path.join(HERE, "fixtures")


def main() -> None:
    os.makedirs(FX, exist_ok=True)

    # H1 — CRLF line endings + a UTF-8 BOM (v3.19.1 class of fault)
    with open(os.path.join(FX, "sample_crlf.txt"), "wb") as fh:
        fh.write(b"\xef\xbb\xbf")  # BOM
        fh.write("line one\r\nline two\r\nline three\r\n".encode("utf-8"))

    # H2 — f-string / template escape brace leak (v3.16.0 / v3.19.0 class)
    with open(os.path.join(FX, "sample_leak.py"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write("# generated stub with an escape brace leak\n")
        fh.write('msg = "value {{name}} rendered"\n')
        fh.write("count = 0\n")

    # H3 — .yaml extension whose body is really JSON (v3.19.0 fake-YAML class)
    with open(os.path.join(FX, "sample_fake.yaml"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write('{"name": "demo", "version": "1.0", "tags": ["a", "b"]}\n')

    # Marker used by Scenario B (a fault no healer can auto-fix)
    with open(os.path.join(FX, "sample_unrepairable.txt"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write("this file carries a %%UNREPAIRABLE%% marker\n")

    print("fixtures written to", FX)


if __name__ == "__main__":
    main()
