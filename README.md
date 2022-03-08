# starling-beancount
## What is this
Use a [Starling Developer](https://developer.starlingbank.com/get-started) account to programatically export your bank transactions to [beancount](https://beancount.github.io/) files.

## Setup
Get a [Starling Personal Access Token](https://developer.starlingbank.com/personal/token) with the following scopes:
```
account:read
balance:read
transaction:read
```

Save the provided token text in a file under the directory `tokens/`, eg `tokens/personal`.

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

## Running the script

Then run the script:
```
Usage: star.py [OPTIONS] ACCS

Options:
  --fr TEXT
  --to TEXT                       [default: today]
  --balance / --no-balance        [default: no-balance]
```

Example get the transactions from `myaccount` (or whatever you called your `token` file) from a date until today:
```
./star.py myaccount --fr=2021-01-01
```

Print the balance:
```
./star.py myaccount --balance
```

## As a beancount importer
```python
from beancount.ingest import importer
import star

class StarlingImporter(importer.ImporterProtocol):
    def extract(self, file):
    account = "name-of-your-token"
    full_account = "Assets:Name:Of:Account"
    return star.convert(account, full_account, from_date, to_date)
```

## Prior art
[jorgeml/starlingbank](https://github.com/jorgeml/starlingbank) does a similar thing, albeit more simply and with all the Beancount stuff properly included. It doesn't get transactions from all categories/spaces, but it does use the simpler `/api/v2/feed/account/{accountUid}/category/{categoryUid}` route, which probably makes more sense!
