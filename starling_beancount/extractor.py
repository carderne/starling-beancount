#!/usr/bin/env python3

import datetime
from pathlib import Path
from pprint import pprint
import sys
from typing import Union

from beancount.core.amount import Amount
from beancount.core.data import Transaction, Posting, Balance, Note, new_metadata
from beancount.core.flags import FLAG_OKAY
from beancount.ingest.extract import print_extracted_entries
from beancount.utils.date_utils import parse_date_liberally
from decimal import Decimal
import httpx
import typer
import yaml

repo_root = Path(__file__).parents[1].resolve()
token_path = repo_root / "tokens"
config_path = repo_root / "config.yml"

VALID_STATUS = ["REVERSED", "SETTLED", "REFUNDED"]


def echo(it):
    print(it, file=sys.stderr)


def log(it):
    print("\n\n\n")
    pprint(it, stream=sys.stderr)
    print()


class Config:
    def __init__(self):
        with open(config_path) as f:
            config = yaml.safe_load(f)
        self.base = config["base"]
        self.cps = config["cps"]
        self.joint = config["jointAccs"]
        self.users = config["userIds"]


class Account:
    def __init__(self, acc, verbose=False):
        self.acc = acc
        self.verbose = verbose
        self.conf = Config()
        self.account_name = ":".join((w.capitalize() for w in self.acc.split("_")))
        self.token = open(token_path / self.acc).read().strip()
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.uid = self.get_uid()

    def get_uid(self) -> str:
        url = "/api/v2/accounts"
        r = httpx.get(self.conf.base + url, headers=self.headers)
        data = r.json()
        try:
            uid = data["accounts"][0]["accountUid"]
        except KeyError:
            log(data)
            sys.exit()
        if self.verbose:
            log(f"{uid=}")
        return uid

    def get_balance_data(self) -> Decimal:
        url = f"/api/v2/accounts/{self.uid}/balance"
        r = httpx.get(self.conf.base + url, headers=self.headers)
        data = r.json()
        if self.verbose:
            log(data)
        bal = Decimal(data["totalClearedBalance"]["minorUnits"]) / 100
        return bal

    def balances(self, display=False) -> list[Balance]:
        bal = self.get_balance_data()
        amt = Amount(bal, "GBP")
        meta = new_metadata("starling-api", 0)
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)

        balance = Balance(meta, tomorrow, self.account_name, amt, None, None)
        if display:
            print_extracted_entries([balance], file=sys.stdout)

        note = Note(meta, tomorrow, self.account_name, "bean-extract")
        return [balance, note]

    def get_transaction_data(self, since: str) -> list[dict]:
        # get default category UID
        url = "/api/v2/accounts"
        r = httpx.get(self.conf.base + url, headers=self.headers)
        default_category = r.json()["accounts"][0]["defaultCategory"]

        # get spaces
        url = f"/api/v2/account/{self.uid}/spaces"
        r = httpx.get(self.conf.base + url, headers=self.headers)
        data = r.json()
        try:
            spaces_categories = [
                sp["savingsGoalUid"] for sp in r.json()["savingsGoals"]
            ]
        except KeyError:
            spaces_categories = []

        if self.verbose:
            log(default_category)
            log(spaces_categories)

        all_data = []
        for category in spaces_categories + [default_category]:
            url = f"/api/v2/feed/account/{self.uid}/category/{category}"
            params = {
                "changesSince": f"{since}T00:00:00.000Z",
            }
            r = httpx.get(
                self.conf.base + url,
                params=params,
                headers=self.headers,
            )
            data = r.json()
            all_data.extend(data["feedItems"])
        return sorted(all_data, key=lambda x: x["transactionTime"])

    def transactions(self, since: str, display: bool = False) -> list[Transaction]:
        tr = self.get_transaction_data(since)
        txns = []
        for i, item in enumerate(tr):
            if self.verbose:
                log(item)
            if (
                item["source"] == "INTERNAL_TRANSFER"
                or item["status"] not in VALID_STATUS
            ):
                continue

            date = parse_date_liberally(item["transactionTime"])
            payee = item.get("counterPartyName", "FIXME")
            ref = " ".join(item["reference"].split())
            amt = Decimal(item["amount"]["minorUnits"]) / 100
            amt = amt if item["direction"] == "IN" else -amt

            user = item.get("transactingApplicationUserUid", None)
            if user and self.acc in self.conf.joint:
                user = self.conf.users[user]
            else:
                # must add this to not get unwanted UIDs returned
                user = None

            try:
                cp = self.conf.cps[item["spendingCategory"]]
            except KeyError:
                cp = self.conf.cps["DEFAULT"]

            extra_meta = {"user": user} if user else None
            meta = new_metadata("starling-api", i, extra_meta)
            p1 = Posting(self.account_name, Amount(amt, "GBP"), None, None, None, None)
            p2 = Posting(cp, None, None, None, None, None)
            txn = Transaction(
                meta=meta,
                date=date,
                flag=FLAG_OKAY,
                payee=payee,
                narration=ref,
                tags=set(),
                links=set(),
                postings=[p1, p2],
            )
            txns.append(txn)

        if display:
            print(f"* {self.acc} - {datetime.date.today()}")
            print_extracted_entries(txns, sys.stdout)
        return txns


def extract(acc: str, since: str) -> list[Union[Transaction, Balance]]:
    """bean-extract entrypoint"""
    account = Account(acc)
    transactions = account.transactions(since)
    balances = account.balances()
    return transactions + balances


def main(acc: str, since: str = None, balance: bool = False, verbose: bool = False):
    """CLI entrypoint"""
    if not since and not balance:
        echo("Need to provide a 'since' date for transactions")
        return

    account = Account(acc, verbose)
    if balance:
        account.balances(display=True)
    else:
        account.transactions(since, display=True)


def cli():
    typer.run(main)


if __name__ == "__main__":
    cli()
