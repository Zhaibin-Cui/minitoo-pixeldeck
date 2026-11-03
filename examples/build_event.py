"""A generic event adapter: emit one supplied build status, never run a command.

python examples/build_event.py --state passed --progress 100 | pixeldeck run build --stdin
"""
import argparse
import json
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--state',choices=['idle','running','passed','failed'],required=True)
parser.add_argument('--project',default='LOCAL BUILD')
parser.add_argument('--step',default='')
parser.add_argument('--progress',type=float)
args=parser.parse_args()
if args.progress is not None and not 0<=args.progress<=100: parser.error('progress must be 0..100')
print(json.dumps({'type':'build','project':args.project[:20],'state':args.state,'progress':args.progress,'step':args.step[:40]}),flush=True)
