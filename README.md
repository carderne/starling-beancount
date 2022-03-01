# starling-beancount
## TODO
- Deal with unsettled txns
- Deal with spaces

## What is this
Use a [Starling Developer](https://developer.starlingbank.com/get-started) account to programatically export your bank transactions to [beancount](https://beancount.github.io/) files.

## Usage
Get a [Starling Personal Access Token](https://developer.starlingbank.com/personal/token) with the following scopes:
```
account:read
balance:read
transaction:read
```

Save the provided token text in a file under the directory `tokens/`, eg `tokens/personal`.

Clone and install requirements:
```
git clone https://github.com/carderne/starling-beancount.git
cd starling-beancount
pip install -e .
```

Then edit the `config.yml` to suit your categories.

Then run the script:
```
Usage: star.py [OPTIONS] ACCS

Arguments:
  ACCS  [required]

Options:
  --fr TEXT
  --to TEXT
  --balance / --no-balance        [default: no-balance]
  --verbose / --no-verbose        [default: no-verbose]
  --help                          Show this message and exit.
```

Example get the transactions from `myaccount` (or whatever you called your `.token` file) for a certain date range:
```
./star.py myaccount 2021-01-01 2021-02-01
```

Print the balance and quit:
```
./star.py myaccount 2021-01-01 2021-02-01 --balance
```

To get it to a beancount file, just pipe `stdout`:
```
./star.py ... > myfile.bean
```
