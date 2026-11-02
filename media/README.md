# Media

Videos, interactive diagrams and images that explain Tallyproof. Everything here is published with the site, so each file has a copy you can open in a browser without cloning the repository.

## Videos

| File | What you get | Length |
|---|---|---|
| [Product demo](https://raunak-choudhary.github.io/tallyproof/media/videos/tallyproof-product-demo.mp4) (`videos/tallyproof-product-demo.mp4`) | A narrated walk through the live site: the problem, the name, a record verified in the browser, one cent changed and the check failing, then a real cited answer. American English voice. | 25 seconds |
| [Architecture explained](https://raunak-choudhary.github.io/tallyproof/media/videos/tallyproof-architecture-explained.mp4) (`videos/tallyproof-architecture-explained.mp4`) | The system map, one group of components at a time, with a narrator explaining what each part does and why the proofs hold. American English voice. | 70 seconds |
| [Data pipelines, explained](https://raunak-choudhary.github.io/tallyproof/media/videos/tallyproof-data-pipelines-explained.mp4) (`videos/tallyproof-data-pipelines-explained.mp4`) | What a data pipeline is, then Tallyproof's batch pipeline (download, Spark, Deequ, gold, replay) and streaming pipeline, with the real row counts, why it is built this way, and where the code lives. | 2 min 34 s |
| [Kafka, explained](https://raunak-choudhary.github.io/tallyproof/media/videos/tallyproof-kafka-explained.mp4) (`videos/tallyproof-kafka-explained.mp4`) | What Kafka is, how Tallyproof's topic, producers and the exactly-once consumer work, the measured throughput, why Kafka is used and what it is deliberately not used for, and where the code lives. | 2 min 18 s |

Posters for all four are in `images/`, for platforms that ask for a thumbnail.

## Interactive diagrams

Open either file in a browser. Every box links to the file and line range that implements it, at the commit the diagram was built from. Press `t` to switch between dark and light, `f` for a presentation view, and use the Live toggle to animate the flows.

| File | What you get |
|---|---|
| [Architecture map](https://raunak-choudhary.github.io/tallyproof/media/diagrams/tallyproof-architecture-map.html) (`diagrams/tallyproof-architecture-map.html`) | The fifteen runtime components, from the public data sources through Spark, Kafka, the append-only ledger, the checkpointer and witness, to the analyst and the browser verifier. |
| [From a question to a proof](https://raunak-choudhary.github.io/tallyproof/media/diagrams/tallyproof-question-to-proof-sequence.html) (`diagrams/tallyproof-question-to-proof-sequence.html`) | A sequence diagram of one question to the analyst: routing, the guarded query, composing and verifying the answer, and the inclusion proof the browser checks. |

Still images of both diagrams are in `images/`.

## How they were made, and how to make them again

The diagrams were built with [Archify](https://github.com/tt-a1i/archify), which checks every cited file and line against the repository before it will produce a diagram. The definitions are in `source/architecture-map/` and `source/question-to-proof-sequence/`. To rebuild one:

```bash
git clone --depth 1 https://github.com/tt-a1i/archify
node archify/archify/bin/archify.mjs finalize architecture \
  media/source/architecture-map/candidate.json out.html \
  --repo-root . --quality showcase
```

The videos were planned with the [Brag](https://github.com/latent-spaces/brag) workflow and rendered with [Hyperframes](https://github.com/HeyGen/hyperframes) 0.8.229, which turns an HTML composition into an MP4. The compositions are in `source/product-demo/`, `source/architecture-explained/`, `source/data-pipelines-explained/` and `source/kafka-explained/`. The narration is generated locally with Kokoro-82M through the Hyperframes `tts` command; the text of every line is beside its composition. To render one:

```bash
cd media/source/architecture-explained/composition
# generate the narration once (voice am_michael; the product demo uses af_heart)
for i in 1 2 3 4 5 6 7 8; do
  npx hyperframes@0.8.229 tts "$(cat assets/vo/line-$i.txt)" --voice am_michael --lang en-us --speed 1.05 --output assets/vo/line-$i.wav
done
npx hyperframes@0.8.229 check
npx hyperframes@0.8.229 render --quality delivery --workers 1 -o ../out.mp4
```

The music and sound effects are not in this repository; the composition names the files it expects, and they come with the Brag repository. The product demo's recording of the live site is made by `source/product-demo/record-verify.mjs` with Playwright.

## Credits

- Music: "Happy Beats / Business Moves Vol. 12" by Sascha Ende, [ende.app](https://ende.app), licensed CC BY 4.0.
- Sound effects: [Kenney](https://kenney.nl) (CC0) and the Keyboard Soundpack #1 by unicae_games (CC0).
- Voices: Kokoro-82M, run locally.
- Fonts: Fraunces, Manrope and Caveat (SIL Open Font License) from Google Fonts; JetBrains Mono.
- Tools: Archify (Apache-2.0), Brag (MIT), Hyperframes (MIT), Playwright.
