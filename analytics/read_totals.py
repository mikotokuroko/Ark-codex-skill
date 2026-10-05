#!/usr/bin/env python3
"""Read private adoption totals without putting the secret in command history."""
import argparse
import getpass
import json
from pathlib import Path
from urllib.request import Request, urlopen

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--token-file', type=Path)
args = parser.parse_args()
token = args.token_file.read_text().strip() if args.token_file else getpass.getpass('Private totals token: ')
req = Request('https://ark-adoption.hoicheoklam.workers.dev/totals', headers={'Authorization': 'Bearer '+token, 'User-Agent': 'ArkCodex-Adoption/1.0'})
with urlopen(req, timeout=15) as response:
    print(json.dumps(json.load(response), indent=2))
