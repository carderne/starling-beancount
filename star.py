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


def log(it):
    print("\n\n\n")
    pprint(it, stream=sys.stderr)
    print()


def parse_accs(accs, config):
    if accs == "all":
        return list(config.accs.keys())
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
        self.accs = config["accs"]


@define
class Account:
    acc: str
    conf: Config
    uid: str = attr.ib(init=False)

    def __attrs_post_init__(self):
        self.uid = self.get_uid()

    def get_uid(self):
        url = "/api/v2/accounts"
        r = httpx.get(self.conf.base + url, headers=self.headers)
        data = r.json()
        uid = data["accounts"][0]["accountUid"]
        return uid

    def get_cp(self, it):
        return self.conf.cps[it["spendingCategory"]]

    @property
    def token(self):
        return self.conf.accs[self.acc]

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def print_balance(self, verbose=False):
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
                print(f"{k:<23}: {data[k]['minorUnits']/100}", f=sys.stderr)
        date = datetime.date.today().isoformat()
        acct = f"Assets:Starling:{self.acc.capitalize()}"
        bal = data["totalEffectiveBalance"]["minorUnits"] / 100
        print(f"{date} balance {acct} {bal} GBP")

    def get_transactions(self, fr, to):
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

    def print_transactions(self, fr, to, verbose=False):
        tr = self.get_transactions(fr, to)
        for it in tr["feedItems"]:
            if verbose:
                log(it)
            try:
                date = it["transactionTime"][:10]
                payee = it.get("counterPartyName", "???")
                ref = " ".join(it["reference"].split())
                acct = f"Assets:Starling:{self.acc.capitalize()}"
                cp = self.get_cp(it)
                amt = it["amount"]["minorUnits"] / 100
                amt = amt if it["direction"] == "IN" else -amt
                print(f'{date} * "{payee}" "{ref}"')
                print(f"  {acct} {amt} GBP")
                print(f"  {cp}\n")
            except KeyError as e:
                print(f"KeyError on {e}", sys.stderr)
                pprint(it, stream=sys.sdterr)


def main(
    accs: str,
    fr: str = typer.Option(None),
    to: str = typer.Option(None),
    balance: bool = False,
    verbose: bool = False,
):

    if not to:
        to = datetime.date.today().isoformat()

    conf = Config()

    accs = parse_accs(accs, conf)
    for acc in accs:
        account = Account(acc, conf)
        if balance:
            account.print_balance(verbose=verbose)
        else:
            print(f"* {acc} - {to}")
            account.print_transactions(fr, to, verbose=verbose)
            print("\n\n\n")


if __name__ == "__main__":
    typer.run(main)
