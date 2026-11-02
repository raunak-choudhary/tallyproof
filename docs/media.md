# Videos and diagrams

Four videos and two interactive diagrams explain Tallyproof without reading the code. All of them are published with the site.

## Videos

**[Product demo](https://raunak-choudhary.github.io/tallyproof/media/videos/tallyproof-product-demo.mp4)**, 25 seconds. A narrated walk through the live site: the problem, the name, a record verified in the browser, one cent changed and the check failing, then a real cited answer.

**[Architecture explained](https://raunak-choudhary.github.io/tallyproof/media/videos/tallyproof-architecture-explained.mp4)**, 70 seconds. The system map lights up one group of components at a time while a narrator explains what each part does: the data pipeline, the append-only ledger and its signed checkpoints, the live projections, the analyst that never types a number, and the browser that checks every proof.

**[Data pipelines, explained](https://raunak-choudhary.github.io/tallyproof/media/videos/tallyproof-data-pipelines-explained.mp4)**, 2 minutes 34 seconds. What a data pipeline is, then where the two pipelines run in Tallyproof: the batch side from the 27 GB download through Spark, Deequ and the gold build to the Kafka replay, and the streaming side from ingestion to the signed ledger, the projections and the Iceberg lake. It closes with why it is built this way and where to look in the code.

**[Kafka, explained](https://raunak-choudhary.github.io/tallyproof/media/videos/tallyproof-kafka-explained.mp4)**, 2 minutes 18 seconds. What Kafka is, how the topic, the producers and the exactly-once consumer work in Tallyproof, the measured throughput, why Kafka is used and what it is deliberately not used for, and where to look in the code.

## Interactive diagrams

Every box in these diagrams links to the file and line range that implements it, at the commit the diagram was built from. Press `t` to switch between dark and light, `f` for a presentation view, and use the Live toggle to animate the flows.

**[Architecture map](https://raunak-choudhary.github.io/tallyproof/media/diagrams/tallyproof-architecture-map.html).** The fifteen runtime components, from the public data sources through Spark, Kafka, the ledger, the checkpointer and witness, to the analyst and the browser verifier. The [architecture document](architecture.md) explains the same picture in prose.

**[From a question to a proof](https://raunak-choudhary.github.io/tallyproof/media/diagrams/tallyproof-question-to-proof-sequence.html).** One question to the analyst, step by step: routing, the guarded query, composing and verifying the answer, and the inclusion proof the browser checks.

## Source and credits

The definitions, compositions and narration scripts are in the repository's `media/source/` folder, with instructions to rebuild each file in the [media folder's own README](https://github.com/raunak-choudhary/tallyproof/tree/main/media). The diagrams were made with Archify; the videos were planned with Brag and rendered with Hyperframes, with narration from Kokoro-82M run locally. The music is "Happy Beats / Business Moves Vol. 12" by Sascha Ende (ende.app), CC BY 4.0; sound effects are CC0 from Kenney and unicae_games.
