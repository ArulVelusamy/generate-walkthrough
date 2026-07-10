"""Render the AWS SDK-calls markdown companion from a sidecar. Stdlib only."""


def render_aws_calls(sidecar):
    calls = sidecar.get("aws_calls") or []
    lines = ["# AWS SDK calls", ""]
    if not calls:
        lines.append("_No AWS SDK calls were found in this codebase._")
        return "\n".join(lines) + "\n"
    lines += ["These are AWS service side-effects the code performs. They are not HTTP endpoints, "
              "so they are documented here rather than in the OpenAPI spec.", "",
              "| Service | Operation | Resource | Purpose | Source |",
              "|---------|-----------|----------|---------|--------|"]
    for c in sorted(calls, key=lambda c: (c["service"], c["operation"])):
        res = c.get("resource") or {}
        res_str = ", ".join("%s=%s" % (k, v) for k, v in sorted(res.items()))
        anc = c.get("anchor") or {}
        src = "%s:%s" % (anc.get("file", ""), anc.get("symbol", ""))
        lines.append("| %s | %s | %s | %s | %s |" % (
            c["service"], c["operation"], res_str, c.get("purpose", ""), src))
    return "\n".join(lines) + "\n"
