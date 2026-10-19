# fsm-to-mp

Python tooling to convert FreeCol map-editor saves (`.fsm`) into the original
Sid Meier's Colonization `.MP` map format, and into OpenCol's `.MPX`, which also
keeps the map's resources, Lost City Rumours and villages.

The converter is intentionally small and dependency-free at runtime. It reads
the FreeCol ZIP/XML container directly, resamples FreeCol's diamond grid onto
Colonization's square grid, writes a three-plane `.MP` file, and can read the
generated `.MP` back for validation.

## Quick Start

```bash
python -m pip install -e ".[dev]"
python -m fsm_to_mp path/to/map.fsm out.MP
python -m fsm_to_mp path/to/map.fsm out.MP --mpx out.MPX --info "author=Jane Doe"
python -m fsm_to_mp --summary path/to/map.fsm
pytest
```

The CLI prints conversion warnings for information that original Colonization
cannot represent exactly, such as FreeCol lakes, great rivers, tile ownership
and roads, and for resources, rumours and villages the `.MPX` cannot place.
`--info KEY=VALUE` adds a line to the `.MPX`'s `INFO` (title, author, source,
license); `--copy-tiles` copies tile for tile as 0.1 did, without resampling.
See `docs/conversion.md`.

## Web Converter

The static browser version lives in `web/`. It vendors the shared
`@colonization-re/web-ui` stylesheet, pinned to a release tag and sha256 in
`web/vendor/col-css.json` (update with `python scripts/vendor_css.py <tag>`),
so it can be served as plain files without a build step or package install.

```bash
python -m http.server 8000 -d web
```

GitHub Pages is deployed automatically from `web/` by
`.github/workflows/pages.yml`.

## Releases

The Python tool and the web converter share one version and are released
together with `python scripts/release.py patch|minor|major`. Each
[GitHub release](https://github.com/colonization-re/fsm-to-mp/releases)
carries a runnable `fsm-to-mp-<version>.pyz` (`python3 fsm-to-mp-<version>.pyz
map.fsm out.MP`), the static `fsm-to-mp-web-<version>.zip` for self-hosting,
and a source `.zip`; notes come from `CHANGELOG.md`.

## Documentation

- `docs/formats.md` documents the researched FreeCol `.fsm`, Colonization
  `.MP` and OpenCol `.MPX` formats.
- `docs/conversion.md` documents every terrain conversion rule.
- `scripts/download_test_maps.py` downloads fixed upstream FreeCol maps and
  verifies SHA-256 hashes for local/manual fixture testing.
