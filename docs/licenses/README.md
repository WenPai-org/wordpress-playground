# Third-party licensing gate

`third-party-inventory.json` is the reviewed, machine-readable notice inventory
for the exact upstream commit in `upstream-lock.json`. It covers the shipped
WordPress archives, PHP-WASM builds and their native library graph, SQLite,
WP-CLI, fonts, Node dependencies, and generated runtime assets.

PHP 8.6 is not part of the stable PHP release array at this upstream tag. It is
an independently generated `php-next-builds` input, locked here to branch commit
`c9ce635313dd326b3947a5d5c37b7f36307e665e`. Its manifest reports
`8.6.0-dev`, php-src ref `master`, and build time `2026-07-28T07:18:08.148Z`.
The inventory records exact README, manifest, asyncify WASM, and JSPI WASM
SHA-256 values. The upstream metadata does not resolve php-src `master` to a
php-src commit; the immutable Playground artifact commit and hashes are the
release provenance boundary. Runtime audit fails unless both locked PHP 8.6
WASM payloads are present.

Run the gate against a clean exact source checkout, not the product repository:

```sh
python3 tools/license-notice-audit.py \
  --source /path/to/wordpress-playground \
  --expected-commit 4d9c20678ca7cbd7bb881dc0cc5f4e5739f6cc2d \
  --inventory docs/licenses/third-party-inventory.json \
  --output evidence/license-notice-audit.json \
  --node-notices evidence/node-license-notices.json
```

Add `--runtime /path/to/dist/packages/playground/wasm-wordpress-net` after a
fresh build. A source-only report is evidence for the source and embedded binary
inventory, not evidence for a Release runtime. A public Release requires both
non-zero source and runtime samples.

The tool fails closed for a wrong or tracked-dirty Git commit, an absent required category,
unknown external Node license, an unreviewed inventory component, or a runtime
with no generated assets. Workspace packages inherit the repository's
GPL-2.0-or-later license. The legacy npm packages in the exception map were
manually checked against their installed package metadata/license file; the key
includes exact package path and version so an update cannot silently inherit the
decision.

`--allow-tracked-generated` exists only for auditing a runtime while the
upstream build is regenerating the two locked Blueprint schema outputs. It
allows exactly those two paths, records them in the report, and rejects every
other tracked change. Release CI does not use this option: its source audit is
against the clean `/tmp/upstream` checkout.

This is a redistribution inventory, not legal advice. Trademark attribution is
kept separate: 文派 Playground must not imply endorsement by the WordPress
Foundation.
