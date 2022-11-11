#!/usr/bin/env python3

import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from pprint import pprint
from typing import Any, Optional, Union

import httpx
import typer
import yaml
from beancount.core.amount import Amount
from beancount.core.data import Balance, Note, Posting, Transaction, new_metadata
from beancount.core.flags import FLAG_OKAY
from beancount.ingest.extract import print_extracted_entries  # type: ignore[import]
from beancount.utils.date_utils import parse_date_liberally  # type: ignore[import]

VALID_STATUS = ["REVERSED", "SETTLED", "REFUNDED"]


def echo(it: str) -> None:
    print(it, file=sys.stderr)


def log(it: Any) -> None:
    print("\n\n\n")
    pprint(it, stream=sys.stderr)
    print()


class Config:
    def __init__(self, config_path: Path) -> None:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        self.base = config["base"]
        self.cps = config["cps"]
        self.joint = config["jointAccs"]
        self.users = config["userIds"]


class Account:
    def __init__(
        self,
        config_path: Path,
        acc: str,
        token_path: Path,
        verbose: bool = False,
    ) -> None:
        self.acc = acc
        self.verbose = verbose
        self.conf = Config(config_path=config_path)
        self.account_name = ":".join((w.capitalize() for w in self.acc.split("_")))
        self.token = open(token_path / self.acc).read().strip()
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.uid = self.get_uid()
        self.today = date.today()
        self.tomorrow = self.today + timedelta(days=1)
        self.start = self.today

    def get_uid(self) -> str:
        url = "/api/v2/accounts"
        r = httpx.get(self.conf.base + url, headers=self.headers)
        data = r.json()
        try:
            uid = str(data["accounts"][0]["accountUid"])
        except KeyError:
            log(data)
            sys.exit(1)
        if self.verbose:
            log(f"{uid}")
        return uid

    def get_balance_data(self) -> Decimal:
        url = f"/api/v2/accounts/{self.uid}/balance"
        r = httpx.get(self.conf.base + url, headers=self.headers)
        data = r.json()
        if self.verbose:
            log(data)
        bal = Decimal(data["totalClearedBalance"]["minorUnits"]) / 100
        return bal

    def balance(self, display: bool = False) -> Balance:
        bal = self.get_balance_data()
        amt = Amount(bal, "GBP")
        meta = new_metadata("starling-api", 999)

        balance = Balance(meta, self.tomorrow, self.account_name, amt, None, None)
        if display:
            print_extracted_entries([balance], file=sys.stdout)

        return balance

    def note(self) -> Note:
        meta_end = new_metadata("starling-api", 998)
        note_end = Note(meta_end, self.tomorrow, self.account_name, "end bean-extract")
        return note_end

    def spaces(self) -> list[str]:
        # get default category UID
        url = "/api/v2/accounts"
        r = httpx.get(self.conf.base + url, headers=self.headers)
        default_category = r.json()["accounts"][0]["defaultCategory"]

        # get spaces
        url = f"/api/v2/account/{self.uid}/spaces"
        r = httpx.get(self.conf.base + url, headers=self.headers)
        data = r.json()
        if "error" in data:
            echo(f"Error: {data['error_description']}")
            sys.exit(1)
        try:
            spaces_categories = [sp["savingsGoalUid"] for sp in data["savingsGoals"]]
        except KeyError:
            spaces_categories = []

        if self.verbose:
            log(default_category)
            log(spaces_categories)

        return [default_category] + spaces_categories

    def get_transaction_data(self, since: date, new: bool = True) -> list[dict]:
        categories = self.spaces()

        all_data = []
        for category in categories:
            url = f"/api/v2/feed/account/{self.uid}/category/{category}"
            if new:
                url = f"/api/v2/feed/account/{self.uid}/category/{category}/transactions-between"
            params = {
                "changesSince": f"{since}T00:00:00.000Z",
            }
            if new:
                params = {
                    "minTransactionTimestamp": f"{since}T00:00:00.000Z",
                    "maxTransactionTimestamp": f"{self.tomorrow}T00:00:00.000Z",
                }
            r = httpx.get(
                self.conf.base + url,
                params=params,
                headers=self.headers,
            )
            data = r.json()
            all_data.extend(data["feedItems"])
        return sorted(all_data, key=lambda x: str(x["transactionTime"]))

    def transactions(self, since: date, display: bool = False) -> list[Transaction]:
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
            p2 = Posting(cp, None, None, None, None, None)  # type: ignore[arg-type]
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

        if len(txns) > 0:
            self.start = txns[0].date

        if display:
            print(f"* {self.acc} - {self.today}")
            print_extracted_entries(txns, sys.stdout)
        return txns


def extract(
    config_path: Path,
    acc: str,
    token_path: Path,
    since: date,
) -> list[Union[Transaction, Balance, Note]]:
    """bean-extract entrypoint"""
    account = Account(config_path=config_path, acc=acc, token_path=token_path)
    txns = account.transactions(since)
    bal = account.balance()
    note = account.note()
    return [*txns, bal, note]


def main(
    config_path: Path,
    acc: str,
    token_path: Path,
    since: Optional[str] = None,
    balance: bool = False,
    verbose: bool = False,
) -> None:
    """CLI entrypoint"""
    if not since and not balance:
        echo("Need to provide a 'since' date for transactions")
        return

    account = Account(
        config_path=config_path, acc=acc, token_path=token_path, verbose=verbose
    )
    if balance:
        account.balance(display=True)
    else:
        assert since is not None
        since_dt = date.fromisoformat(since)
        account.transactions(since_dt, display=True)


def cli() -> None:
    typer.run(main)


if __name__ == "__main__":
    cli()
