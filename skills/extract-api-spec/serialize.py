"""Deterministically transform a walkthrough sidecar into OpenAPI + Postman + AWS companion.

Usage: python serialize.py <sidecar.json> <outdir>
Stdlib only. Output is byte-identical across runs on the same sidecar.
"""

import json
import sys
from pathlib import Path

from openapi_render import render_openapi
from postman_render import render_postman
from aws_render import render_aws_calls


def _dump(obj):
    return json.dumps(obj, sort_keys=True, indent=2) + "\n"


def _assert_no_invention(sidecar, openapi):
    op_ids = [op["operationId"]
              for methods in openapi["paths"].values() for op in methods.values()]
    ep_ids = [ep["operationId"] for ep in sidecar["endpoints"]]
    if sorted(op_ids) != sorted(ep_ids):
        raise ValueError("no-invention check failed: OpenAPI operations do not match sidecar endpoints "
                         "(%d vs %d)" % (len(op_ids), len(ep_ids)))


def serialize(sidecar, outdir):
    name = sidecar["project"]["name"]
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    openapi = render_openapi(sidecar)
    _assert_no_invention(sidecar, openapi)
    collection, environment = render_postman(sidecar)
    aws_md = render_aws_calls(sidecar)

    written = []
    targets = [
        ("%s-openapi.json" % name, _dump(openapi)),
        ("%s.postman_collection.json" % name, _dump(collection)),
        ("%s.postman_environment.json" % name, _dump(environment)),
        ("%s-aws-calls.md" % name, aws_md),
    ]
    for filename, content in targets:
        path = out / filename
        path.write_text(content)
        written.append(str(path))
    return written


def main(argv):
    if len(argv) != 3:
        print("usage: python serialize.py <sidecar.json> <outdir>", file=sys.stderr)
        return 2
    with open(argv[1]) as fh:
        sidecar = json.load(fh)
    written = serialize(sidecar, argv[2])
    for p in written:
        print("wrote %s" % p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
