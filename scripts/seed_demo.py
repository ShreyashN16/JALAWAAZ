"""Add or remove clearly labelled SYNTHETIC demo tickets (see app/services/demo.py).

  python -m scripts.seed_demo           # add 14 synthetic tickets across every lifecycle path
  python -m scripts.seed_demo --clear   # remove every synthetic ticket; real tickets are untouched
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db  # noqa: E402
from app.services import demo  # noqa: E402


def main(clear: bool) -> None:
    db.init_db()
    con = db.connect()
    try:
        if clear:
            print(f"Removed {demo.clear(con)} synthetic tickets. Real tickets were not touched.")
        else:
            print(f"Seeded {demo.seed(con)} synthetic tickets (flagged is_synthetic=1 and labelled in every view).")
    finally:
        con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clear", action="store_true", help="remove synthetic tickets")
    main(ap.parse_args().clear)
