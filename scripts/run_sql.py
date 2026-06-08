"""
run_sql.py — execute the .sql files against DuckDB and print labelled results.

Statements are split on ';'. CREATE VIEW/TABLE statements run silently;
any statement preceded by a '-- @label:' comment is printed with that label.
Runs from the repo root so the relative data/raw paths resolve.

Usage:  .venv/bin/python scripts/run_sql.py [profile_checks|business_questions|dashboard_tables]
"""
import os, re, sys
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)

files = sys.argv[1:] or ["profile_checks", "business_questions", "dashboard_tables"]
con = duckdb.connect()

def parse(sql):
    """Strip comments line-by-line (so semicolons inside prose are ignored),
    capture '-- @label:' annotations, and split into (label, statement) pairs."""
    statements, buf, label = [], [], None
    for line in sql.splitlines():
        lm = re.match(r"\s*--\s*@label:\s*(.+)", line)
        if lm:
            label = lm.group(1).strip()
            continue
        code = re.sub(r"--.*", "", line)        # drop line/inline comments
        buf.append(code)
        if ";" in code:
            stmt = "\n".join(buf).strip().rstrip(";").strip()
            buf = []
            if stmt:
                statements.append((label, stmt))
            label = None
    return statements

for stem in files:
    path = ROOT / "sql" / f"{stem}.sql"
    print("\n" + "#" * 72)
    print(f"# {stem}.sql")
    print("#" * 72)
    for label, stmt in parse(path.read_text(encoding="utf-8")):
        if stmt.lower().startswith(("select", "with")):
            if label:
                print(f"\n>>> {label}")
            print(con.execute(stmt).fetchdf().to_string(index=False))
        else:
            con.execute(stmt)  # setup (views/tables), no output

print("\nDone.")
