# References

Every outside claim in this repository traces to one of the sources below. Each was checked against the original publication in October 2026.

## Regulation and industry

- **FINRA, 2026 Annual Regulatory Oversight Report, "GenAI: Continuing and Emerging Trends."** Names accuracy (including hallucinations) and bias as risks to address, and lists storing prompt and output logs as an effective practice. The report states that it creates no new legal requirements. [Report page at FINRA](https://www.finra.org/rules-guidance/guidance/reports/2026-finra-annual-regulatory-oversight-report/gen-ai)
- **EU AI Act, Articles 12 and 14.** Automatic event logging and human oversight for high-risk AI systems. Under the 2026 Digital Omnibus amendments (Regulation (EU) 2026/1744), these obligations apply from 2 December 2027 for stand-alone high-risk systems and 2 August 2028 for systems embedded in products. Tallyproof is not a high-risk system under the Act; the articles describe properties it aims to demonstrate. [Article 12](https://artificialintelligenceact.eu/article/12/), [Article 14](https://artificialintelligenceact.eu/article/14/), [legislative status](https://www.europarl.europa.eu/legislative-train/package-digital-package/file-digital-omnibus-on-ai)
- **AWS, Amazon QLDB end of support.** QLDB reached end of support on 31 July 2025. AWS's migration guidance recommends Aurora PostgreSQL and notes that it "does not keep a permanent, immutable record of changes," so that history must be generated separately. The original AWS pages have since been retired. [Archived blog post](http://web.archive.org/web/20251114160405/https://aws.amazon.com/blogs/database/replace-amazon-qldb-with-amazon-aurora-postgresql-for-audit-use-cases/), [archived documentation notice](http://web.archive.org/web/20250617052438/https://docs.aws.amazon.com/qldb/latest/developerguide/what-is.html)
- **AWS, S3 Object Lock.** Compliance mode prevents any user, including the root account, from deleting or overwriting a locked object version. AWS reports an assessment by Cohasset Associates for SEC 17a-4, CFTC, and FINRA record-keeping environments. [AWS documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)

## Research on citations and numeric accuracy

- **Wallat, Heuss, de Rijke, Anand. "Correctness is not Faithfulness in Retrieval Augmented Generation Attributions." ICTIR 2025.** Up to 57 percent of citations in attributed answers were not faithful: the model had not actually relied on the cited source. [arXiv 2412.18004](https://arxiv.org/abs/2412.18004), [ACM Digital Library](https://doi.org/10.1145/3731120.3744592)
- **Gao et al. "Enabling Large Language Models to Generate Text with Citations" (ALCE). EMNLP 2023.** On ELI5, even the best models lacked complete citation support about half the time. [arXiv 2305.14627](https://arxiv.org/abs/2305.14627)
- **Ma, Chu, Fuhr. "VERICITE." BioNLP 2026.** Only 27 to 41 percent of citation pairs were supported at the sentence level at retrieval depths of 3 and 5. [ACL Anthology](https://aclanthology.org/2026.bionlp-1.62/)
- **Islam et al. "FinanceBench." 2023.** On a 150-question sample, GPT-4-Turbo with a retrieval system answered incorrectly or refused 81 percent of questions. [arXiv 2311.11944](https://arxiv.org/abs/2311.11944)
- **Long et al. "FinLFQA." Findings of EMNLP 2025.** GPT-4o reached 42.3 numerical F1 in the post-hoc setting on the development set; BERTScore did not separate models meaningfully. [arXiv 2510.06426](https://arxiv.org/abs/2510.06426)
- **Lin et al. "VeriRAG: Efficient Zero-Knowledge Proofs for Verifiable Retrieval-Augmented Generation." IACR ePrint 2026/637.** A direction for future work. [Paper on IACR ePrint](https://eprint.iacr.org/2026/637)

## Transparency logs and canonical data

- **RFC 9162, Certificate Transparency Version 2.0.** Merkle tree hashing with leaf and node prefixes, inclusion proofs, and consistency proofs. [RFC 9162 text](https://www.rfc-editor.org/rfc/rfc9162.html)
- **RFC 8785, JSON Canonicalization Scheme.** Deterministic JSON bytes for hashing and signing. [RFC 8785 text](https://www.rfc-editor.org/rfc/rfc8785.html)
- **C2SP, tlog-checkpoint.** The signed checkpoint format used by transparency logs. [Specification on GitHub](https://github.com/C2SP/C2SP/blob/main/tlog-checkpoint.md)
- **Crosby and Wallach. "Efficient Data Structures for Tamper-Evident Logging." USENIX Security 2009.** Tree-based logs give logarithmic proofs that an untrusted logger has not rewritten history. [Paper page at USENIX](https://www.usenix.org/conference/usenixsecurity09/technical-sessions/presentation/efficient-data-structures-tamper-evident)
- **Transparency.dev.** Background on verifiable logs, witnesses, and tiles. [Project site](https://transparency.dev/)

## Data sources

- **USAspending.gov, Award Data Archive and API.** Federal contract transactions and account-level outlays. No authentication required. [API documentation](https://api.usaspending.gov/docs/endpoints)
- **U.S. Treasury, Fiscal Data API, Daily Treasury Statement.** Deposits and withdrawals of operating cash, offered free and without restriction. [API documentation](https://fiscaldata.treasury.gov/api-documentation/)
- **Federal Acquisition Regulation.** Public policy text used for the analyst's policy questions. [FAR on acquisition.gov](https://www.acquisition.gov/browse/index/far)

## Related projects

- **Answerproof.** Signed receipts with a Merkle root over the documents a RAG system retrieved. It proves that a known set of sources was used; it does not prove those sources were unchanged since they were recorded. [Repository on GitHub](https://github.com/AgentPostmortem/Answerproof)
