import textwrap
from typing import Sequence, TextIO

import dateutil.parser
from beancount.core.data import Balance, Note, Transaction
from beancount.parser import printer

DUPLICATE_META = "__duplicate__"


def parse_date_liberally(string: str):
    return dateutil.parser.parse(string).date()


def print_extracted_entries(entries: Sequence[Transaction | Balance | Note], file: TextIO):
    print("", file=file)

    for entry in entries:
        # Check if this entry is a dup, and if so, comment it out.
        if DUPLICATE_META in entry.meta:
            meta = entry.meta.copy()
            meta.pop(DUPLICATE_META)
            entry = entry._replace(meta=meta)
            entry_string = textwrap.indent(printer.format_entry(entry), "; ")
        else:
            entry_string = printer.format_entry(entry)
        print(entry_string, file=file)

    print("", file=file)
