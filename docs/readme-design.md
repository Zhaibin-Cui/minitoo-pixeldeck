# README design notes

The README places a miniature console in a pixel forest: leaves, hanging vines, floating ground and warm fireflies around a clear technical workspace. It opens with runnable demo previews, followed by architecture, setup and extension guides. The default-dark documentation homepage uses an enlarged demo stage and the same original forest artwork.

## Layout choices

- The animated hero keeps the recognizable device silhouette inside an original woodland scene.
- Static forest dividers mark the setup, gallery and extension sections. Leaf accents stay outside text, code and real demo renders.
- Dark blue and pine green carry the setting; cyan, pink and gold retain their meaning in technical diagrams and status displays.
- A compact terminal-style project map lists the canvas, cartridge count and input/output model.
- Three navigation chapters separate the engine, first run and cartridge shelf.
- Each gallery card places its render beside a command and an activation behavior.
- Utility cards are grouped around real tasks: host instruments, time tools and pushed signals.
- Deeper recipes use collapsible sections so the gallery remains easy to browse.
- The source links next to the gallery connect every visual to reproducible code.

The forest artwork, control strip, architecture graphic, illustrations and previews are generated locally by `tools/build_gallery.py` from the project's drawing code and renderers. Monitor and audio previews use synthetic data; hardware measurements stay in the validation record. Decorative images have empty alternative text; the hero and diagrams have descriptive alternatives.

## References

- [Gum README](https://github.com/charmbracelet/gum/blob/main/README.md): a distinctive visual identity followed closely by useful commands and examples.
- [VHS README](https://github.com/charmbracelet/vhs/blob/main/README.md): demonstrations explicitly connected to their generating source.
- [Starship README](https://github.com/starship/starship/blob/main/README.md): compact navigation and deeper setup details kept out of the main visual path.

The references guided the layout; the text and artwork are original.
