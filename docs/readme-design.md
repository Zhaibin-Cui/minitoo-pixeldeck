# README design notes

The README uses the device's pixel palette and control layout. It starts with architecture and setup, followed by a gallery of runnable cartridges.

## Layout choices

- The animated hero establishes a recognizable device silhouette and pixel palette.
- A compact terminal-style project map lists the canvas, cartridge count and input/output model.
- Three navigation chapters separate the engine, first run and cartridge shelf.
- Each gallery card places its render beside a command and an activation behavior.
- Utility cards are grouped around real tasks: host instruments, time tools and pushed signals.
- Deeper recipes use collapsible sections so the gallery remains easy to browse.
- The source links next to the gallery connect every visual to reproducible code.

The control strip, architecture graphic, illustrations and previews are generated locally by `tools/build_gallery.py` from the project's drawing code and renderers. Monitor and audio previews use synthetic data; hardware measurements stay in the validation record.

## References

- [Gum README](https://github.com/charmbracelet/gum/blob/main/README.md): a distinctive visual identity followed closely by useful commands and examples.
- [VHS README](https://github.com/charmbracelet/vhs/blob/main/README.md): demonstrations explicitly connected to their generating source.
- [Starship README](https://github.com/starship/starship/blob/main/README.md): compact navigation and deeper setup details kept out of the main visual path.

The references guided the layout; the text and artwork are original.
