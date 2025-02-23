from datetime import date, timedelta
from pathlib import Path
from typing import Any

import beancount.loader
from beancount.core.data import Balance, Note, Transaction
from beangulp.importer import Importer  # type: ignore

from starling_beancount import extractor


def filt_notes(entry: Any, account_name: str) -> bool:
    if isinstance(entry, Note) and entry.account == account_name and "bean-extract" in entry.comment:
        return True
    else:
        return False


def last_date(bean_path: Path, account_name: str) -> date:
    entries, _, _ = beancount.loader.load_file(str(bean_path))
    notes = [e for e in entries if filt_notes(e, account_name)]
    dates = [r.date for r in notes]
    try:
        max_date = max(dates)
    except ValueError:
        print("No existing 'bean-extract' notes!")
        print("Add this to your ledger specifying the date to extract from:")
        print('2022-03-01 note Assets:Starling "bean-extract"')
        return date(2000, 1, 1)

    return max_date


class StarlingImporter(Importer):  # type: ignore
    def __init__(
        self,
        config_path: Path,
        acc: str,
        token_path: Path,
        bean_path: Path,
        lag: int = 3,
    ):
        self.config_path = config_path
        self.acc = acc
        self.token_path = token_path
        self.account_name = ":".join((w.capitalize() for w in acc.split("_")))
        self.bean_path = bean_path
        self.lag = lag

    @property
    def name(self) -> str:
        return self.account_name

    def identify(self, filepath: str) -> bool:
        return self.acc in filepath

    def extract(self, filepath: str, existing: Any = None) -> list[Transaction | Balance | Note]:
        since = last_date(self.bean_path, self.account_name) - timedelta(days=self.lag)
        res = extractor.extract(self.config_path, self.acc, self.token_path, since)
        return res

    def account(self, filepath: str):
        return self.account_name

    def filename(self, filepath: str):
        return None

    def date(self, filepath: str):
        return None
