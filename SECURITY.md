# Local security checks

Run from the repository root:

```sh
gitleaks git --log-opts="--all" --redact --report-format json --report-path /tmp/gitleaks-report.json .
semgrep scan --config .semgrep.yml --metrics off --disable-version-check --error --json --output /tmp/semgrep-report.json .
```

The checked-in Semgrep rules are an original, offline rule set covering dynamic code, shell execution, unsafe deserialization, disabled TLS, insecure temporary names, weak hashes, unsafe extraction, unreviewed URL opening, workflow input interpolation, broad workflow permissions, active SVG and private-key markers. No remote rule pack or GitHub fetch is required. This is a scoped static review, not an assertion of comprehensive vulnerability coverage. Gitleaks uses its bundled default rules and scans every local Git ref. Report locations are outside the repositories to avoid recursively scanning scanner output.

No credentials, client records or full legal texts should be submitted. Report a suspected issue privately to the repository owner using the firm's published contact page: https://lx20lawfirm.com/it/contatti.
