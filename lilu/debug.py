import json

from pathlib import Path
from script import run

with open(Path(__file__).parent.parent / 'input' / 'test_event.json') as f:
  event = json.load(f)
result = run(event, {})
print(result)