from datetime import date
from pathlib import Path
from typing import Any

import beancount.loader
from beancount.core.data import Note
from beancount.ingest import importer  # type: ignore[import]

from starling_beancount import extractor


def filt_notes(entry: Any, account_name: str) -> bool:
    if (
        isinstance(entry, Note)
        and entry.account == account_name
        and "bean-extract" in entry.comment
    ):
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


class StarlingImporter(importer.ImporterProtocol):  # type: ignore[no-any-unimported]
    def __init__(
        self,
        config_path: Path,
        acc: str,
        token_path: Path,
        bean_path: Path,
    ):
        self.config_path = config_path
        self.acc = acc
        self.token_path = token_path
        self.account_name = ":".join((w.capitalize() for w in acc.split("_")))
        self.bean_path = bean_path

    def name(self) -> str:
        return self.account_name

    def identify(self, file: Path) -> bool:
        return self.acc in file.name

    def extract(self, file: str) -> list:
        since = last_date(self.bean_path, self.account_name)
        res = extractor.extract(self.config_path, self.acc, self.token_path, since)
        return res

    # Deliberately no file_account, file_date, file_name
    # So that bean_file doesn't move the target files
