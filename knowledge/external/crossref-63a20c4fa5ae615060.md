---
title: Large Language Models for Literature-Based Analysis: Constructing Ontology-Grounded Citation Knowledge Graphs
organization: Crossref
published_at: 2026-5-20
url: https://doi.org/10.21203/rs.3.rs-9583368/v1
---

# Large Language Models for Literature-Based Analysis: Constructing Ontology-Grounded Citation Knowledge Graphs

- 外部数据源：Crossref
- 作者：Muhammad Saad Salman¹, Imran Ihsan¹
- 发布日期：2026-5-20
- DOI：10.21203/rs.3.rs-9583368/v1
- 被引次数：0
- 原始链接：https://doi.org/10.21203/rs.3.rs-9583368/v1

## 摘要或检索片段

Abstract This work introduces a novel framework to construct ontology grounded knowledge graphs using contexts from citation sentiment dataset and incorporating large language models LLMs for literature grounded analysis. Recent studies look at the perspectives of ontologies, citation intent and information extraction separately, this work combines these concepts in a single end to end pipeline. The proposed framework uses a small locally hosted LLM along with a subset of the Citation Typing Ontology (CiTO) to decide which relation to assign, applies filtering based on confidence score, finds out the smallest supporting evidence span and finally creates a knowledge graph. In the knowledge graph the relation, intent, stance and evidence of each citation example is stored, and each example is treated as a separate instance. The experiments report results on the SciCite dataset and show that the pipeline finds out smaller evidence spans than the full context for most of the examples, a significant part of data is preserved after the confidence based filtering and most of the assertions are kept. To summarize, this paper addresses the challenges of entity extraction and semantic reasoning and shows that citation contexts can be converted into auditable knowledge graphs backed by confidence score.
