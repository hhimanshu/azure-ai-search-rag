# Indexing pipeline

Four parts turn the five driver's-manual PDFs into a searchable index. Each clip adds to the same pipeline.

![Indexing pipeline](pipeline.svg)

## Azure classes

| Box | Azure class | What it does | Clip |
|---|---|---|---|
| 1 Data source | `SearchIndexerDataSourceConnection` | Points the indexer at the PDF container in Blob Storage. | 1 |
| 2 Skillset | `SearchIndexerSkillset` | Holds the enrichment steps and the index projection. | 1 |
| Skillset step | `OcrSkill` | Reads text from the images in the PDFs. | 1 |
| Skillset step | `MergeSkill` | Puts the OCR text back into the page text. | 1 |
| Skillset step | `SplitSkill` | Cuts the text into chunks of about 2,000 characters, with 500 characters of overlap. | 1 |
| Skillset step | `SearchIndexerIndexProjection` | Makes each chunk its own search document. | 1 |
| Skillset step | `AzureOpenAIEmbeddingSkill` | Creates one vector for each chunk. | 2 |
| 3 Indexer | `SearchIndexer` | Runs the skillset and fills the index. It maps `title` from the blob name. | 1 |
| Indexer mapping | `FieldMappingFunction` | Takes `state` from the blob folder name. | 3 |
| 4 Index | `SearchIndex` | Stores one search document for each chunk: `chunk_id`, `parent_id`, `title`, `chunk`. | 1 |
| Index vectors | `VectorSearch` | Stores the `vector` field and how to search it. | 2 |
| Index vectors | `AzureOpenAIVectorizer` | Turns the query text into a vector at search time. | 2 |
| Index ranking | `SemanticSearch` | Adds the semantic ranker. The `state` field adds the filter. | 3 |

## Mermaid version

```mermaid
flowchart LR
    blob["Blob Storage<br/>5 PDFs"] --> ds["1 Data source<br/>SearchIndexerDataSourceConnection<br/>(Clip 1)"]
    ds --> sk["2 Skillset<br/>SearchIndexerSkillset<br/>(Clip 1, 2)"]
    sk --> ix["3 Indexer<br/>SearchIndexer<br/>(Clip 1, 3)"]
    ix --> idx["4 Index<br/>SearchIndex<br/>(Clip 1, 2, 3)"]
    idx --> q["Queries<br/>full-text, vector, hybrid"]

    subgraph skills["Inside the skillset"]
        ocr["OcrSkill (Clip 1)"] --> merge["MergeSkill (Clip 1)"] --> split["SplitSkill (Clip 1)"] --> emb["AzureOpenAIEmbeddingSkill (Clip 2)"] --> proj["SearchIndexerIndexProjection (Clip 1)"]
    end
    sk --- skills

    subgraph indexer_detail["Inside the indexer"]
        m1["title from metadata_storage_name (Clip 1)"]
        m2["state from the blob folder, FieldMappingFunction (Clip 3)"]
    end
    ix --- indexer_detail

    subgraph index_detail["Inside the index"]
        f1["chunk_id, parent_id, title, chunk (Clip 1)"]
        f2["vector, AzureOpenAIVectorizer, VectorSearch (Clip 2)"]
        f3["state filter, SemanticSearch (Clip 3)"]
    end
    idx --- index_detail
```
