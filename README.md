# starling-beancount
## What is this
Use a [Starling Developer](https://developer.starlingbank.com/get-started) account to programatically export your bank transactions to [beancount](https://beancount.github.io/) files.

There are two main scripts:
1. [starling_beancount/extractor.py](./starling_beancount/extractor.py) converts Starling API JSON to beancount Transactions and Balances.
2. [starling_beancount/importer.py](./starling_beancount/importer.py) contains the configuration for `bean-extract` to parse that.

## Setup
Get a [Starling Personal Access Token](https://developer.starlingbank.com/personal/token) with the following scopes:
```
account:read
balance:read
transaction:read
space:read
```

Save the provided token text in a file under the directory `tokens/`, eg `tokens/assets_starling`.

👉 The token name will be converted internally to an account name by replacing '_' with ':' (for Windows compatibility) and capitalizing. So `assets_starling` becomes `Assets:Starling`. **Make sure to name your tokens appropriately!**

Clone and install requirements:
```bash
git clone https://github.com/carderne/starling-beancount.git
cd starling-beancount
pip install -e .
```

## Configuration
Then rename the config template:
```bash
mv config_template.yml config.yml
```

And edit it to suit your needs.
The `jointAccs` and `userIds` fields are only needed if you have a joint account and you want to add metadata about which user made a transaction.
The `cps` are key:value pairs of Starling transaction categories, and the beancount Account you want them assigned to.
If you don't want to do this, just delete all but the `DEFAULT` pair.

## 💪 Running the script

Then run the script:
```
Usage: starling [OPTIONS] ACC

Options:
  --fr TEXT
  --to TEXT                       [default: today]
  --balance / --no-balance        [default: no-balance]
```

Example to get the transactions from `assets_starling` (or whatever you called your `token` file) from a date until today:
```
starling assets_starling --fr=2021-01-01
```

Print the balance:
```
starling assets_starling --balance
```

## 🧠 As a beancount importer
You will need to add something like the following to your `bean-extract` configuration (eg `config.py`):
```python
from starling_beancount.importer import StarlingImporter

CONFIG = [
    ...,
    StarlingImporter("assets_starling", "./path/to/ledger.bean"),
]
```

Then add a `Note` to your ledger, specifying the earliest date you would like `starling-beancount` to extract from.
**It must have the text "bean-extract" somewhere in it.**
A new note will be added each time you run the script, so that you don't have to deal with too many duplicates.
```beancount
2022-03-01 note Assets:Starling "bean-extract"
```

Last thing! You must create the "target" file that `bean-extract` will look for.
Since we don't actually need a file (it all comes from the API), just add a file to wherever you would normally place them (probably wherever you keep your ledger files, _not_ in this repo.

👉 Make sure to name this in the same way as the tokens.

```bash
touch ./raw/assets_starling
```

So long as this file is there, `bean-extract` (and, by extension, the Fava importing tool) will find it and offer you to import that account.

Then run the following:
```bash
bean-extract config.py raw/assets_starling
```

## Prior art
[jorgeml/starlingbank](https://github.com/jorgeml/starlingbank) does a similar thing, albeit more simply (probably for the better).
