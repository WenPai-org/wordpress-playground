# Release rollback contract

This Release is a runtime artifact, not an in-place site updater.

For the first `play.wenpai.net` product migration, the previous runtime is the
official WordPress Playground 3.1.49 artifact with SHA-256
`5ea2b9d227cd817d7fa1db47dc5d0a9577239b99d87e07bd4caa4f3a6effd44c`.
The site deployment must verify the current runtime against its exact baseline,
create a timestamped archive and SHA-256 before replacing a file, and create an
executable rollback script that removes new manifest paths and restores the
archive. Staging and production acceptance are mandatory; any failure invokes
that rollback immediately.

Later releases use the deployed `.wenpai-runtime-manifest.json` as the old-path
contract. The site repository records exact backup and rollback paths. This
product Release never deletes site business content.
