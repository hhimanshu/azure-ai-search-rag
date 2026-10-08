# Module 2: Indexing pipeline

Build an Azure AI Search index for the five driver's manuals, in three parts. Each part adds one goal. Black boxes are what the part adds.

| File | What it is |
|---|---|
| `README.md` | This page: one diagram per part. |
| `helpers.py` | Pre-built functions. Each has a one-line description of what it does and which Azure services it uses. |
| `02_indexing_pipeline.ipynb` | The notebook. Fill in each `____` to build the part. |

## Part 1: Turn the PDFs into searchable chunks

![Part 1: Turn the PDFs into searchable chunks](pipeline-part1.svg)

| Box | Azure class | What it does | Azure service |
|---|---|---|---|
| 1 Data source | `SearchIndexerDataSourceConnection` | Points the indexer at the PDF container in Blob Storage. | Blob Storage, read with the search service's managed identity |
| 2 Skillset | `SearchIndexerSkillset` | Holds the enrichment steps and the index projection. | Azure AI Search |
| Skillset step | `OcrSkill` | Reads text from the images in the PDFs. | Azure AI Services (Azure Vision OCR) |
| Skillset step | `MergeSkill` | Puts the OCR text back into the page text. | Built into Azure AI Search |
| Skillset step | `SplitSkill` | Cuts the text into chunks of about 2,000 characters, with 500 characters of overlap. | Built into Azure AI Search |
| Skillset step | `SearchIndexerIndexProjection` | Makes each chunk its own search document. | Azure AI Search |
| 3 Indexer | `SearchIndexer` | Runs the skillset and fills the index. It maps `title` from the blob name. | Azure AI Search |
| 4 Index | `SearchIndex` | Stores one search document for each chunk: `chunk_id`, `parent_id`, `title`, `chunk`. | Azure AI Search |

## Part 2: Match by meaning, not just words

![Part 2: Match by meaning, not just words](pipeline-part2.svg)

| Box | Azure class | What it does | Azure service |
|---|---|---|---|
| Skillset step | `AzureOpenAIEmbeddingSkill` | Creates one vector for each chunk. | Azure OpenAI (embedding model), called by Azure AI Search while the indexer runs |
| Index vectors | `VectorSearch` | Stores the `vector` field and how to search it. | Azure AI Search |
| Index vectors | `AzureOpenAIVectorizer` | Turns the query text into a vector at search time. | Azure OpenAI (the same embedding model), called by Azure AI Search when a query arrives |

## Part 3: Filter by state and rank by relevance

![Part 3: Filter by state and rank by relevance](pipeline-part3.svg)

| Box | Azure class | What it does | Azure service |
|---|---|---|---|
| Indexer mapping | `FieldMappingFunction` | Takes `state` from the blob folder name. | Azure AI Search |
| Index ranking | `SemanticSearch` | Adds the semantic ranker. The `state` field adds the filter. | Azure AI Search (semantic ranker, Microsoft-hosted language models) |
