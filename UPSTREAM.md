# Upstream provenance

This product is a downstream source-level overlay of [WordPress Playground](https://github.com/WordPress/wordpress-playground), maintained by WenPai.org. It is not an official WordPress Foundation or WordPress.org distribution.

The initial source is the peeled commit `4d9c20678ca7cbd7bb881dc0cc5f4e5739f6cc2d` behind annotated tag `v3.1.49`. `upstream-lock.json` is authoritative for the canonical URL, FeiCode mirror, normalized source digest, transform digest, version mapping, and fixed toolchain.

The product repository deliberately does **not** vendor the upstream monorepo. CI materializes the exact tag from the read-only mirror, verifies it against canonical and the recorded source manifest, then applies `overlays/` and product configuration in an isolated worktree. Product changes must not be pushed into the mirror.

Copyright remains with the individual WordPress Playground and dependency contributors. Upstream is distributed under GPL-2.0-or-later; see `LICENSE`. WordPress, PHP, WASM binaries, fonts, Node packages, and other bundled assets may carry additional notices or compatible licenses. The release SBOM is a dependency summary, not a substitute for the still-required per-binary license audit.

“WordPress” is a trademark of the WordPress Foundation. WenPai branding must not imply upstream endorsement. The downstream UI may retain upstream names where required for attribution, interoperability, or license notices.
