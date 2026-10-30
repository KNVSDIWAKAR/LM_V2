"""Drop every table, recreate the five tables from app/models, and load the data files.

    python -m scripts.reset_db                      # asks before dropping; reads backend/data/
    python -m scripts.reset_db --yes                # no prompt
    python -m scripts.reset_db --data-dir C:/path   # folder holding the three files

The folder must contain msp.json, lm_status.json and extracted_data.json.
This deletes everything in the database named in backend/.env, including workflow and agent runs.
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy import MetaData, inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal, create_tables, engine  # noqa: E402
from scripts.import_data import import_extracted, import_lm_stages, import_msp  # noqa: E402

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FILES = {"msp": "msp.json", "lm_status": "lm_status.json", "extracted": "extracted_data.json"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help=f"folder with the JSON files (default: {DEFAULT_DATA_DIR})")
    parser.add_argument("--yes", action="store_true", help="drop without asking")
    args = parser.parse_args()

    paths = {key: args.data_dir / name for key, name in FILES.items()}
    missing = [str(p) for p in paths.values() if not p.is_file()]
    if missing:
        raise SystemExit("Missing data file(s):\n  " + "\n  ".join(missing))

    existing = MetaData()
    existing.reflect(engine)
    target = f"{engine.url.host or ''}/{engine.url.database}"
    print(f"Database: {target}")
    print(f"Tables to drop ({len(existing.tables)}): {', '.join(sorted(existing.tables)) or 'none'}")
    if not args.yes and input("Drop all of these and reload? Type 'yes' to continue: ").strip().lower() != "yes":
        raise SystemExit("Cancelled; nothing changed.")

    existing.drop_all(engine)
    create_tables()
    print(f"Created: {', '.join(sorted(inspect(engine).get_table_names()))}")

    # One transaction: if any file fails validation, no data is loaded.
    with SessionLocal() as db:
        print(f"msp:             {import_msp(db, paths['msp'])} loans")
        print(f"lm_stages:       {import_lm_stages(db, paths['lm_status'])} loans")
        print(f"extracted_data:  {import_extracted(db, paths['extracted'])} loans")
        db.commit()
    print("Done.")


if __name__ == "__main__":
    main()
