"""Pipe this process into `pixeldeck run signal --stdin`. One real push, then EOF."""
import json
print(json.dumps({'type':'notice','text':'BUILD COMPLETE. TIME FOR TEA.'}),flush=True)
