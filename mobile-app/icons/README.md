# Icons

`logo.svg` and `maskable.svg` are the sources. The PNG icons the manifest needs
(`icon-192.png`, `icon-512.png`, `maskable-512.png`) are built from them by the
GitHub Pages workflow with `rsvg-convert`, so they are not committed.

To build them locally:

```bash
cd mobile-app/icons
rsvg-convert -w 192 -h 192 logo.svg -o icon-192.png
rsvg-convert -w 512 -h 512 logo.svg -o icon-512.png
rsvg-convert -w 512 -h 512 maskable.svg -o maskable-512.png
```
