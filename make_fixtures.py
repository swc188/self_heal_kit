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

    # H4 — config-style file with unbalanced double quotes (v3.19.0 class)
    with open(os.path.join(FX, "sample_quotes.cfg"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write("# config with an unbalanced quote\n")
        fh.write('app_name = "my app\n')
        fh.write('endpoint = "https://example.test"\n')
        fh.write('token = "abc123\n')

    # H5 — alias table with a known alias whose canonical key is empty
    # (v3.10.1 display-name vs key; v3.22.0 Chinese term -> method name)
    with open(os.path.join(FX, "sample_terms.csv"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write("term,canonical\n")
        fh.write("区块链 / Web3,\n")
        fh.write("列表,\n")
        fh.write("Web 框架,django\n")

    # H6 — declaration (README) vs implementation (__version__) drift
    # (v3.19.1 README claim != implementation; v3.10.3 contract drift)
    with open(os.path.join(FX, "README.md"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write("# Demo Project\n")
        fh.write("Version: 1.0.0\n")
    with open(os.path.join(FX, "sample_impl.py"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write('# implementation whose version drifted from README\n')
        fh.write('__version__ = "0.9.0"\n')

    # Marker used by Scenario B (a fault no healer can auto-fix)
    with open(os.path.join(FX, "sample_unrepairable.txt"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write("this file carries a %%UNREPAIRABLE%% marker\n")

    print("fixtures written to", FX)


if __name__ == "__main__":
    main()
