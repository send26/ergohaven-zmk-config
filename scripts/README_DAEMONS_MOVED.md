ZMK host daemon tooling has been moved to:

- `~/github/dotfiles-latest/zmk/scripts`
- `~/github/dotfiles-latest/zmk/config`
- `~/github/dotfiles-latest/zmk/*.plist`

This firmware repository now keeps only firmware build/flash tooling.

Set `ZMK_FIRMWARE_ROOT` (default: `~/zmk/ergohaven-zmk-config`) for the
dotfiles-side parser/tests that read keymaps from this repo.
