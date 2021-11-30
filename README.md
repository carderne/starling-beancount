# starling-beancount
## TODO
- Deal with unsettled txns
- Deal with spaces

## What is this
Use a [Starling Developer](https://developer.starlingbank.com/get-started) account to programatically export your bank transactions to [beancount](https://beancount.github.io/) files.

## Usage
Get a [Starling Personal Access Token](https://developer.starlingbank.com/get-started) with the scopes `account:read`, `balance:read`, and `transaction:read` and save the token text in a file called eg `myaccount.token` (it can be whatever you want, but must have the extension `.token`).

Clone and install requirements:
```
git clone https://github.com/carderne/starling-beancount.git
cd starling-beancount
pip install -r requirements.txt
```

Rename and update the config file:
```
mv config_template.yml config.yml

# edit it with counterparties if needed!
```

Then run the script:
```
Usage: star.py [OPTIONS] ACC FR TO

Arguments:
  ACC  [required]
  FR   [required]
  TO   [required]

Options:
  --balance / --no-balance        [default: no-bal]
  --verbose / --no-verbose        [default: no-verbose]
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
