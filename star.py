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
from decimal import Decimal

tokens = Path(__file__).parent.resolve() / "tokens"


def echo(it):
    pprint(it, stream=sys.stderr)


def log(it):
    print("\n\n\n")
    echo(it)
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

    def __init__(self, path=None):
        if not path:
            path = Path(__file__).parents[0] / "config.yml"
        with open(path) as f:
            config = yaml.safe_load(f)
        self.base = config["base"]
        self.cps = config["cps"]
        self.accs = {p.stem: open(p).read().strip() for p in tokens.glob("*")}


@define
class Account:
    acc: str
    full_account: str
    conf: Config
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
            echo(data)
            sys.exit()
        log(uid)
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

    def get_balance_data(self, verbose=False):
        url = f"/api/v2/accounts/{self.uid}/balance"
        r = httpx.get(self.conf.base + url, headers=self.headers)
        data = r.json()
        if verbose:
            keys = [
                "clearedBalance",
                "effectiveBalance",
                "pendingTransactions",
                "amount",
                "totalClearedBalance",
                "totalEffectiveBalance",
            ]
            for k in keys:
                print(f"{k:<23}: {data[k]['minorUnits']/100}", file=sys.stderr)
        bal = Decimal(data["totalEffectiveBalance"]["minorUnits"]) / 100
        return bal

    def balance(self):
        bal = self.get_balance_data()
        amt = amount.Amount(bal, "GBP")
        meta = data.new_metadata("starling-api", 0)
        acct = self.full_account
        balance = data.Balance(meta, datetime.date.today(), acct, amt, None, None)
        return balance

    def print_balance(self, verbose=False):
        bal = self.get_balance_data(verbose=verbose)
        date = datetime.date.today().isoformat()
        acct = self.full_account
        print(f"{date} balance {acct} {bal} GBP")

    def get_transaction_data(self, fr, to):
        url = f"/api/v2/feed/account/{self.uid}/settled-transactions-between"
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
        return data

    def extract_info(self, it):
        date = it["transactionTime"][:10]
        payee = it.get("counterPartyName", "FIXME")
        ref = " ".join(it["reference"].split())
        acct = self.full_account
        cp = self.get_cp(it)
        amt = Decimal(it["amount"]["minorUnits"]) / 100
        amt = amt if it["direction"] == "IN" else -amt
        return date, payee, ref, acct, cp, amt

    def transactions(self, fr, to):
        tr = self.get_transaction_data(fr, to)
        txns = []
        for i, it in enumerate(tr["feedItems"]):
            date, payee, ref, acct, cp, amt = self.extract_info(it)

            meta = data.new_metadata("starling-api", i)
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
        return txns

    def print_transactions(self, fr, to, verbose=False):
        tr = self.get_transaction_data(fr, to)
        for it in tr["feedItems"]:
            if verbose:
                log(it)
            try:
                date, payee, ref, acct, cp, amt = self.extract_info(it)
                print(f'{date} * "{payee}" "{ref}"')
                print(f"  {acct} {amt} GBP")
                print(f"  {cp}\n")
            except KeyError as e:
                print(f"KeyError on {e}", sys.stderr)
                pprint(it, stream=sys.stderr)


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
        print("Need to provide a from date for transactions")
        return

    if not to:
        to = datetime.date.today().isoformat()

    conf = Config()

    accs = parse_accs(accs)
    for acc in accs:
        account = Account(acc, f"Assets:Starling:{acc}", conf)
        if balance:
            account.print_balance(verbose=verbose)
        else:
            print(f"* {acc} - {to}")
            account.print_transactions(fr, to, verbose=verbose)
            print("\n\n\n")


if __name__ == "__main__":
    typer.run(main)
