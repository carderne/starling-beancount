#!/usr/bin/env python3

import sys
from pprint import pprint
from pathlib import Path
import datetime
from typing import Union

import httpx
import attr
from attr import define
import typer
import yaml
from beancount.core.amount import Amount
from beancount.core.data import Transaction, Posting, Balance, Note, new_metadata
from beancount.core.flags import FLAG_OKAY
from beancount.ingest.extract import print_extracted_entries
from beancount.utils.date_utils import parse_date_liberally
from decimal import Decimal

token_path = Path(__file__).parent.resolve() / "tokens"
config_path = Path(__file__).parents[0] / "config.yml"

VALID_STATUS = ["REVERSED", "SETTLED", "REFUNDED"]


def echo(it):
    print(it, file=sys.stderr)


def log(it):
    print("\n\n\n")
    pprint(it, stream=sys.stderr)
    print()


@define(init=False)
class Config:
    base: str
    cps: dict
    tokens: dict
    joint: list
    users: dict

    def __init__(self):
        with open(config_path) as f:
            config = yaml.safe_load(f)
        self.base = config["base"]
        self.cps = config["cps"]
        self.tokens = {p.stem: open(p).read().strip() for p in token_path.glob("*")}
        self.joint = config["jointAccs"]
        self.users = config["userIds"]


@define
class Account:
    acc: str
    full_account: str
    conf: Config
    verbose: bool = False
    uid: str = attr.ib(init=False)

    def __attrs_post_init__(self):
        self.uid = self.get_uid()

    def get_uid(self):
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

    def get_cp(self, it):
        try:
            return self.conf.cps[it["spendingCategory"]]
        except KeyError:
            return self.conf.cps["DEFAULT"]

    @property
    def token(self):
        try:
            return self.conf.tokens[self.acc]
        except KeyError:
            echo("Token not found, make sure it exists under tokens/")
            sys.exit()

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

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

        balance = Balance(meta, tomorrow, self.full_account, amt, None, None)
        if display:
            print_extracted_entries([balance], file=sys.stdout)

        note = Note(meta, tomorrow, self.full_account, "bean-extract")
        return [balance, note]

    def get_transaction_data(self, fr: str) -> list[dict]:
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
                "changesSince": f"{fr}T00:00:00.000Z",
            }
            r = httpx.get(
                self.conf.base + url,
                params=params,
                headers=self.headers,
            )
            data = r.json()
            all_data.extend(data["feedItems"])
        return sorted(all_data, key=lambda x: x["transactionTime"])

    def transactions(self, fr: str, display: bool = False) -> list[Transaction]:
        tr = self.get_transaction_data(fr)
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

            extra_meta = {"user": user} if user else None
            meta = new_metadata("starling-api", i, extra_meta)

            p1 = Posting(self.full_account, Amount(amt, "GBP"), None, None, None, None)
            p2 = Posting(self.get_cp(item), None, None, None, None, None)
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


def extract(acc: str, full_account: str, fr: str) -> list[Union[Transaction, Balance]]:
    conf = Config()
    account = Account(acc, full_account, conf)
    transactions = account.transactions(fr)
    balances = account.balances()
    return transactions + balances


def main(
    acc: str,
    fr: str = None,
    balance: bool = False,
    verbose: bool = False,
):
    if not fr and not balance:
        echo("Need to provide a from date for transactions")
        return

    conf = Config()

    account = Account(acc, f"Assets:Starling:{acc.capitalize()}", conf, verbose)
    if balance:
        account.balances(display=True)
    else:
        account.transactions(fr, display=True)


if __name__ == "__main__":
    typer.run(main)
