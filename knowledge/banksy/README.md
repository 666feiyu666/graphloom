# Banksy case graph (reviewed)

A small visual-rhetoric knowledge graph for a limited Banksy corpus, built for the Graphloom workbench. The ontology and analytical relations have been reviewed by the researcher.

## Evidence state

- The artworks are **not** CC-licensed. The sources below are CC-licensed photographs on Wikimedia Commons that document a work, a site, or an afterlife.
- Factual details come from the Commons file descriptions. Analytical labels (tropes, rhetorical functions) are provisional and marked in object notes.
- Each source is a `source_ref` with `evidence_state: abstract_preview_verified` (file-page metadata read; not a scholarly full-text verification).

## CC sources

| Source | License | Author | Documents |
| --- | --- | --- | --- |
| [Well Hung Lover, Bristol](https://commons.wikimedia.org/wiki/File:%27Well_Hung_Lover%27,_Banksy%27s_Graffiti_Mural_in_Bristol,_England_(November_14th_2026).jpg) | CC BY-SA 4.0 | Vintage Fan 5678 | 2006 mural, Frogmore Street, Bristol |
| [Paint Pot Angel, Bristol Museum](https://commons.wikimedia.org/wiki/File:Banksy%27s_Paint_Pot_Angel_in_Bristol_Museum_and_Art_Gallery.jpg) | CC BY-SA 4.0 | Vintage Fan 5678 | angel with paint pot, in the museum |
| [Drop In Photographers, New Orleans](https://commons.wikimedia.org/wiki/File:Banksy_Drop_In_Photographers,_New_Orleans.jpg) | CC BY-SA 2.0 | Infrogmation of New Orleans | 2008 photographing of a work; artwork blurred for derivative-work copyright |
| [Girl with Balloon seen in Domburg](https://commons.wikimedia.org/wiki/File:Girl_with_Balloon_(IMG_20230615_150813).jpg) | CC BY-SA 4.0 | Monoxyde | the balloon-girl image seen in Domburg |
| [Balloon Girl by Tetoux, Madrid](https://commons.wikimedia.org/wiki/File:Balloon_Girl_-_Tetoux_-_Bansky_-_Calle_de_Meson_de_Paredes_-_Madrid_01.jpg) | CC BY-SA 4.0 | Javier Perez Montes (Nerve net) | a mural by Tetoux based on Banksy's image |
| [The Walled Off Hotel and the Wall](https://commons.wikimedia.org/wiki/File:The_Walled_Off_Hotel_and_the_Wall.jpg) | CC BY-SA 4.0 | シャター | the hotel and the separation wall, Bethlehem |

Excluded during verification: `File:Love is in the Air (7414282380) (2).jpg` (an unrelated photograph of lizards).

## Build and read back

```bash
cd graphloom/backend && uv run python ../knowledge/build.py --case banksy          # build (or --replace)
cd graphloom/knowledge && python3 agent_read_test.py --case banksy               # OpenAI read-back
```

The files live in `knowledge/banksy/` as `ontology.json`, `sources.json`, and `data.json`; see `knowledge/README.md` for the format.

## Shape

- Classes (12): Visual artifact → {Street artwork, Installation}; Agent → Artist; plus Visual motif, Rhetorical trope, Public site, Institution, Audience, Discourse, Reception event.
- Relations (9): depicts, deploys, sitedAt, attributedTo, respondsTo, addresses, institutionalContext, appropriates, receptionOf.
- Attributes (4): year, medium, locationText, rhetoricalFunction.
- Working trope vocabulary (reviewed): juxtaposition, irony, appropriation, metaphor, metonymy, intertextuality, site-specific intervention, institutional critique, anonymity.

The `rhetoricalFunction` values and several `deploys` assertions are reviewed readings.
