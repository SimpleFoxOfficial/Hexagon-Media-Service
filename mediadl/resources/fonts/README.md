# Fonts

Any `.ttf` or `.otf` dropped in this folder is registered at startup, so extra
faces can be added without touching code.

## Comfortaa

`Comfortaa-Variable.ttf` is the logo face, from
[google/fonts](https://github.com/google/fonts/tree/main/ofl/comfortaa) under the
SIL Open Font License 1.1. The full licence text is in `Comfortaa-OFL.txt` and
must stay with the font.

It is the variable version, which Qt registers as the `Comfortaa` family with
Light, Regular, Medium, SemiBold and Bold styles available.

If the file is removed the logo falls back to the interface font and nothing
else changes. Settings reports which of the two is in use.
