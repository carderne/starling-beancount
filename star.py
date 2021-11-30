#!/usr/bin/env python3

from pprint import pprint
from pathlib import Path

import httpx
import attr
from attr import define
import typer
import yaml


def log(it):
    print("\n\n\n")
    pprint(it)
    print()


@define(init=False)
class Config:
    base: str
    cps: dict

    def __init__(self, path=None):
        if not path:
            path = Path(__file__).parents[0] / "config.yml"
        with open(path) as f:
            config = yaml.safe_load(f)
        self.base = config["base"]
        self.cps = config["cps"]


@define
class Account:
    acc: str
    uid: str = attr.ib(init=False)
    conf: Config = attr.ib(init=False)

    def __attrs_post_init__(self):
        self.conf = Config()
        self.uid = self.get_uid()

    def get_uid(self):
        url = "/api/v2/accounts"
        r = httpx.get(self.conf.base + url, headers=self.headers)
        data = r.json()
        return data["accounts"][0]["accountUid"]

    def get_cp(self, it):
        return self.conf.cps[it["spendingCategory"]]

    @property
    def token(self):
        path = Path(__file__).parents[0] / f"{self.acc}.token"
        with open(path) as f:
            return f.read().strip()

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    @property
    def balance(self):
        url = f"/api/v2/accounts/{self.uid}/balance"
        r = httpx.get(self.conf.base + url, headers=self.headers)
        data = r.json()
        return data

    def get_transactions(self, fr, to):
        url = f"/api/v2/feed/account/{self.uid}/settled-transactions-between"
        params = {
            "minTransactionTimestamp": f"{fr}T00:00:00.000Z",
            "maxTransactionTimestamp": f"{to}T00:00:00.000Z",
        }
        r = httpx.get(self.conf.base + url, params=params, headers=self.headers)
        data = r.json()
        return data

    def print_transactions(self, fr, to, verbose=False):
        tr = self.get_transactions(fr, to)
        for it in tr["feedItems"]:
            if verbose:
                log(it)
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


def main(acc: str, fr: str, to: str, balance: bool = False, verbose: bool = False):
    account = Account(acc)
    if balance:
        print(account.balance)
    else:
        account.print_transactions(fr, to, verbose=verbose)


if __name__ == "__main__":
    typer.run(main)
