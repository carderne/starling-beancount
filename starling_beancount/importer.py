import sys
from pathlib import Path

from beancount.ingest import importer
import beancount.loader
from beancount.core.data import Note

from . import extractor


def interesting(account_name):
    def filt(entry):
        if (
            isinstance(entry, Note)
            and entry.account == account_name
            and "bean-extract" in entry.comment
        ):
            return True
        else:
            return False

    return filt


def last_date(bean_file, account_name):
    entries, _, _ = beancount.loader.load_file(bean_file)
    notes = filter(interesting(account_name), entries)
    dates = [r.date for r in notes]
    try:
        max_date = max(dates)
    except ValueError:
        print("No existing 'bean-extract' notes!")
        print("Add this to your ledger specifying the date to extract from:")
        print('2022-03-01 note Assets:Starling "bean-extract"')
        sys.exit(0)

    return max_date


class StarlingImporter(importer.ImporterProtocol):
    def __init__(self, acc: str, bean_file: Path):
        self.acc = acc
        self.account_name = ":".join((w.capitalize() for w in acc.split("_")))
        self.bean_file = bean_file

    def name(self):
        return self.account_name

    def identify(self, file):
        return self.acc in file.name

    def extract(self, file, existing_entries=None):
        since = last_date(self.bean_file, self.account_name)
        res = extractor.extract(self.acc, since)
        return res

    # Deliberately no file_account, file_date, file_name
    # So that bean_file doesn't move the target files
