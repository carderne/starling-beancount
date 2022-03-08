#!/usr/bin/env python3

import sys
from pprint import pprint
from pathlib import Path
import datetime

import httpx
import attr
from attr import define
import typer
import yaml
from beancount.core import data, flags, amount
from beancount.ingest.extract import print_extracted_entries
from decimal import Decimal

tokens = Path(__file__).parent.resolve() / "tokens"


def echo(it):
    print(it, file=sys.stderr)


def log(it):
    print("\n\n\n")
    pprint(it, stream=sys.stderr)
    print()


def parse_accs(accs):
    if accs == "all":
        return [p.stem for p in sorted(tokens.glob("*")) if ".gitkeep" not in p.stem]
    elif "," in accs:
        return accs.split(",")
    else:
        return [accs]


@define(init=False)
class Config:
    base: str
    cps: dict
    accs: dict
    joint: list
    users: dict

    def __init__(self, path=None, user_path=None):
        if not path:
            path = Path(__file__).parents[0] / "config.yml"
        with open(path) as f:
            config = yaml.safe_load(f)
        self.base = config["base"]
        self.cps = config["cps"]
        self.accs = {p.stem: open(p).read().strip() for p in tokens.glob("*")}
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
            return self.conf.accs[self.acc]
        except KeyError:
            echo("Token not found, make sure it exists under tokens/")
            sys.exit()

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def get_balance_data(self):
        url = f"/api/v2/accounts/{self.uid}/balance"
        r = httpx.get(self.conf.base + url, headers=self.headers)
        data = r.json()
        if self.verbose:
            keys = [
                "clearedBalance",
                "effectiveBalance",
                "pendingTransactions",
                "amount",
                "totalClearedBalance",
                "totalEffectiveBalance",
            ]
            for k in keys:
                echo(f"{k:<23}: {data[k]['minorUnits']/100}")
        bal = Decimal(data["totalEffectiveBalance"]["minorUnits"]) / 100
        return bal

    def balance(self, display=False):
        bal = self.get_balance_data()
        amt = amount.Amount(bal, "GBP")
        meta = data.new_metadata("starling-api", 0)
        acct = self.full_account
        balance = data.Balance(
            meta,
            datetime.date.today() + datetime.timedelta(days=1),
            acct,
            amt,
            None,
            None,
        )
        if display:
            print_extracted_entries([balance], file=sys.stdout)
        return balance

    def get_transaction_data(self, fr, to):
        # first get all the category IDs

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
        all_categories = spaces_categories + [default_category]
        for category in all_categories:
            url = f"/api/v2/feed/account/{self.uid}/category/{category}/transactions-between"
            params = {
                "minTransactionTimestamp": f"{fr}T00:00:00.000Z",
                "maxTransactionTimestamp": f"{to}T00:00:00.000Z",
            }
            r = httpx.get(
                self.conf.base + url,
                params=params,
                headers=self.headers,
            )
            data = r.json()
            all_data.extend(data["feedItems"])
        return all_data

    def extract_info(self, it):
        try:
            date = it["transactionTime"][:10]
            payee = it.get("counterPartyName", "FIXME")
            ref = " ".join(it["reference"].split())
            acct = self.full_account
            cp = self.get_cp(it)
            amt = Decimal(it["amount"]["minorUnits"]) / 100
            amt = amt if it["direction"] == "IN" else -amt
            user = it.get("transactingApplicationUserUid", None)
            if user and self.acc in self.conf.joint:
                user = self.conf.users[user]
            else:
                # must add this to not get unwanted UIDs returned
                user = None
        except KeyError:
            log(it)
            sys.exit(1)
        return date, payee, ref, acct, cp, amt, user

    def transactions(self, fr, to, display=False):
        tr = self.get_transaction_data(fr, to)
        txns = []
        for i, it in enumerate(tr):
            if it["source"] == "INTERNAL_TRANSFER" or it["status"] != "SETTLED":
                continue
            date, payee, ref, acct, cp, amt, user = self.extract_info(it)

            extra_meta = {"user": user} if user else None
            meta = data.new_metadata("starling-api", i, extra_meta)
            p1 = data.Posting(acct, amount.Amount(amt, "GBP"), None, None, None, None)
            p2 = data.Posting(cp, None, None, None, None, None)
            txn = data.Transaction(
                meta=meta,
                date=datetime.date.fromisoformat(date),
                flag=flags.FLAG_OKAY,
                payee=payee,
                narration=ref,
                tags=set(),
                links=set(),
                postings=[p1, p2],
            )
            txns.append(txn)

        if display:
            print_extracted_entries(txns, sys.stdout)
        return txns


def extract(acc: str, full_account: str, fr: str, to: str) -> list:
    if not to:
        to = datetime.date.today().isoformat()

    conf = Config()
    account = Account(acc, full_account, conf)
    transactions = account.transactions(fr, to)
    balance = account.balance()
    return transactions + [balance]


def main(
    accs: str,
    fr: str = None,
    to: str = None,
    balance: bool = False,
    verbose: bool = False,
):
    if not fr and not balance:
        echo("Need to provide a from date for transactions")
        return

    if not to:
        to = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

    conf = Config()

    accs = parse_accs(accs)
    for acc in accs:
        account = Account(acc, f"Assets:Starling:{acc.capitalize()}", conf, verbose)
        if balance:
            account.balance(display=True)
        else:
            print(f"* {acc} - {to}")
            account.transactions(fr, to, display=True)
            print("\n\n\n")


if __name__ == "__main__":
    typer.run(main)
