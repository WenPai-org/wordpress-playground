# Third-party notices

Reviewed for upstream commit `4d9c20678ca7cbd7bb881dc0cc5f4e5739f6cc2d`.

This inventory records redistribution terms for runtime inputs. Copyright remains with each upstream author. The exact source and lock are the corresponding source/provenance; this file does not grant trademark rights.

| Component | Version | License | Source | Redistribution |
|---|---|---|---|---|
| WordPress core archives and extracted runtime trees | 6.3 through 7.0, beta and nightly as pinned by the exact source | GPL-2.0-or-later | https://github.com/WordPress/wordpress-develop | PASS |
| WordPress Playground source and generated website/runtime assets | v3.1.49 | GPL-2.0-or-later | https://github.com/WordPress/wordpress-playground/tree/4d9c20678ca7cbd7bb881dc0cc5f4e5739f6cc2d | PASS |
| PHP compiled to WebAssembly | 5.2.17, 7.4.33, 8.0.30, 8.1.34, 8.2.32, 8.3.32, 8.4.23, 8.5.8 | PHP-3.01 AND GPL-2.0-or-later (Playground packaging) | https://github.com/php/php-src | PASS |
| PHP next WebAssembly branch artifacts | 8.6.0-dev | PHP-3.01 AND GPL-2.0-or-later (Playground packaging) | https://github.com/WordPress/wordpress-playground/tree/c9ce635313dd326b3947a5d5c37b7f36307e665e | PASS |
| Emscripten toolchain runtime portions | 4.0.19 | MIT AND NCSA | https://github.com/emscripten-core/emscripten | PASS |
| SQLite and WordPress SQLite Database Integration | SQLite 3.51.0; integration versions pinned in sqlite-database-integration-versions.json | LicenseRef-SQLite-Public-Domain AND GPL-2.0-or-later | https://sqlite.org/ and https://github.com/WordPress/sqlite-database-integration | PASS |
| WP-CLI Phar fixtures and runtime download contract | embedded fixture SHA-256 af6b7ccc21ed0907cb504db5a059f0e120117905a6017bfdd4375cee3c93d864 | MIT | https://github.com/wp-cli/wp-cli | PASS |
| WordPress theme fonts, Dashicons, TinyMCE fonts and Playground UI fonts | as embedded in exact source | OFL-1.1 OR GPL-2.0-or-later OR license accompanying the containing WordPress component | license files adjacent to each theme font and WordPress component source | PASS |
| ImageMagick | 7.1.1-39 | Apache-2.0 | https://github.com/ImageMagick/ImageMagick/tree/7.1.1-39 | PASS |
| Alliance for Open Media libaom | 3.13.1 | BSD-2-Clause | https://aomedia.googlesource.com/aom/+/v3.13.1 | PASS |
| libavif | 1.3.0 | BSD-2-Clause | https://github.com/AOMediaCodec/libavif/tree/v1.3.0 | PASS |
| curl/libcurl | 7.69.1 | curl | https://curl.se/ | PASS |
| libedit | 20221030-3.1 | BSD-3-Clause | https://www.thrysoee.dk/editline/ | PASS |
| libgd | 2.3.3 | BSD-3-Clause | https://github.com/libgd/libgd | PASS |
| GNU libiconv | 1.17 | LGPL-2.1-or-later | https://www.gnu.org/software/libiconv/ | PASS |
| libjpeg-turbo | 3.0.3 | BSD-3-Clause AND IJG AND Zlib | https://github.com/libjpeg-turbo/libjpeg-turbo/tree/3.0.3 | PASS |
| ncurses | 6.2 | X11 | https://ftp.gnu.org/gnu/ncurses/ | PASS |
| OpenSSL | 1.1.0h and 1.1.1t | Apache-2.0 | https://www.openssl.org/source/ | PASS |
| libpng | 1.6.39 | libpng-2.0 | http://www.libpng.org/pub/png/libpng.html | PASS |
| libwebp | 845d5476a866141ba35ac133f856fa62f0b7445f | BSD-3-Clause | https://chromium.googlesource.com/webm/libwebp/+/845d5476a866141ba35ac133f856fa62f0b7445f | PASS |
| libxml2 | 2.9.10 (compiled artifact; build Dockerfile clones without a source ref) | MIT | https://gitlab.gnome.org/GNOME/libxml2 | PASS |
| zlib | 1.2.13 | Zlib | https://zlib.net/ | PASS |
| libzip | 1.2.0 and 1.9.2 build targets; checked-in artifact 1.9.2 | BSD-3-Clause | https://libzip.org/ | PASS |
| Oniguruma | 6.9.10 | BSD-2-Clause | https://github.com/kkos/oniguruma | PASS |
| Node package dependency graph | package-lock.json exact graph | per-package SPDX value; ten exact legacy lock entries resolved by reviewed exception map | registry URLs and integrity fields in package-lock.json | PASS |
| Generated JavaScript, CSS, HTML, worker and static runtime assets | derived from exact source and lock | GPL-2.0-or-later plus licenses of bundled Node/PHP/font dependencies | exact source commit and deterministic build manifest | PASS |

## Required notices

### WordPress core archives and extracted runtime trees

Copyright WordPress contributors. Preserve GPL and WordPress attribution; marks are not licensed as product endorsement.

License expression: `GPL-2.0-or-later`. Source: https://github.com/WordPress/wordpress-develop

### WordPress Playground source and generated website/runtime assets

Copyright WordPress Playground contributors; see repository LICENSE and downstream UPSTREAM.md.

License expression: `GPL-2.0-or-later`. Source: https://github.com/WordPress/wordpress-playground/tree/4d9c20678ca7cbd7bb881dc0cc5f4e5739f6cc2d

### PHP compiled to WebAssembly

PHP is distributed under the PHP License; the Playground packages containing these builds are GPL-2.0-or-later.

License expression: `PHP-3.01 AND GPL-2.0-or-later (Playground packaging)`. Source: https://github.com/php/php-src

### PHP next WebAssembly branch artifacts

Generated from php-src ref master. Exact artifact provenance is the immutable php-next-builds commit and the recorded README/manifest/WASM SHA-256 values; php-src master was not resolved to a commit in upstream metadata.

License expression: `PHP-3.01 AND GPL-2.0-or-later (Playground packaging)`. Source: https://github.com/WordPress/wordpress-playground/tree/c9ce635313dd326b3947a5d5c37b7f36307e665e

### Emscripten toolchain runtime portions

Generated WebAssembly and loader output may contain Emscripten runtime portions.

License expression: `MIT AND NCSA`. Source: https://github.com/emscripten-core/emscripten

### SQLite and WordPress SQLite Database Integration

SQLite is dedicated to the public domain. The WordPress integration plugin is GPL-2.0-or-later and includes its LICENSE.

License expression: `LicenseRef-SQLite-Public-Domain AND GPL-2.0-or-later`. Source: https://sqlite.org/ and https://github.com/WordPress/sqlite-database-integration

### WP-CLI Phar fixtures and runtime download contract

Copyright WP-CLI contributors. Runtime downloads must use a pinned URL and SHA before a product Release.

License expression: `MIT`. Source: https://github.com/wp-cli/wp-cli

### WordPress theme fonts, Dashicons, TinyMCE fonts and Playground UI fonts

Preserve adjacent OFL/LICENSE files and font Reserved Font Name conditions. Do not extract and relicense fonts independently.

License expression: `OFL-1.1 OR GPL-2.0-or-later OR license accompanying the containing WordPress component`. Source: license files adjacent to each theme font and WordPress component source

### ImageMagick

Linked PHP-WASM dependency.

License expression: `Apache-2.0`. Source: https://github.com/ImageMagick/ImageMagick/tree/7.1.1-39

### Alliance for Open Media libaom

Linked PHP-WASM dependency.

License expression: `BSD-2-Clause`. Source: https://aomedia.googlesource.com/aom/+/v3.13.1

### libavif

Linked PHP-WASM dependency.

License expression: `BSD-2-Clause`. Source: https://github.com/AOMediaCodec/libavif/tree/v1.3.0

### curl/libcurl

Copyright curl authors; preserve the curl license.

License expression: `curl`. Source: https://curl.se/

### libedit

Linked PHP-WASM dependency.

License expression: `BSD-3-Clause`. Source: https://www.thrysoee.dk/editline/

### libgd

Linked PHP-WASM dependency.

License expression: `BSD-3-Clause`. Source: https://github.com/libgd/libgd

### GNU libiconv

Dynamically/wasm-linked LGPL component; corresponding source is provided by the pinned upstream URL.

License expression: `LGPL-2.1-or-later`. Source: https://www.gnu.org/software/libiconv/

### libjpeg-turbo

Linked PHP-WASM dependency with a multi-license notice set.

License expression: `BSD-3-Clause AND IJG AND Zlib`. Source: https://github.com/libjpeg-turbo/libjpeg-turbo/tree/3.0.3

### ncurses

Linked PHP-WASM dependency.

License expression: `X11`. Source: https://ftp.gnu.org/gnu/ncurses/

### OpenSSL

This product includes software developed by the OpenSSL Project for use in the OpenSSL Toolkit.

License expression: `Apache-2.0`. Source: https://www.openssl.org/source/

### libpng

Linked PHP-WASM dependency.

License expression: `libpng-2.0`. Source: http://www.libpng.org/pub/png/libpng.html

### libwebp

Linked PHP-WASM dependency.

License expression: `BSD-3-Clause`. Source: https://chromium.googlesource.com/webm/libwebp/+/845d5476a866141ba35ac133f856fa62f0b7445f

### libxml2

Linked PHP-WASM dependency.

License expression: `MIT`. Source: https://gitlab.gnome.org/GNOME/libxml2

### zlib

Linked PHP-WASM dependency.

License expression: `Zlib`. Source: https://zlib.net/

### libzip

Linked PHP-WASM dependency.

License expression: `BSD-3-Clause`. Source: https://libzip.org/

### Oniguruma

Linked PHP-WASM dependency.

License expression: `BSD-2-Clause`. Source: https://github.com/kkos/oniguruma

### Node package dependency graph

The generated Node notice metadata lists every package/license pair; workspace links inherit GPL-2.0-or-later.

License expression: `per-package SPDX value; ten exact legacy lock entries resolved by reviewed exception map`. Source: registry URLs and integrity fields in package-lock.json

### Generated JavaScript, CSS, HTML, worker and static runtime assets

Generated files are not a new license boundary. Retain this inventory, source lock and build manifest with the Release.

License expression: `GPL-2.0-or-later plus licenses of bundled Node/PHP/font dependencies`. Source: exact source commit and deterministic build manifest

## License texts

Full standard license texts are in `docs/licenses/texts/`; their digests are recorded in `docs/licenses/LICENSE_TEXTS.sha256`. SPDX texts are pinned to license-list-data v3.27.0.

