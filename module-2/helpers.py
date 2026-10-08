"""Module 2 helpers: each function does one job in Azure AI Search, and names the Azure services it calls."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from azure.core.exceptions import HttpResponseError
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient, SearchIndexerClient
from azure.search.documents.indexes.models import (
    CognitiveServicesAccountKey,
    FieldMapping,
    HnswAlgorithmConfiguration,
    IndexingParameters,
    IndexingParametersConfiguration,
    IndexProjectionMode,
    InputFieldMappingEntry,
    MergeSkill,
    OcrSkill,
    OutputFieldMappingEntry,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchIndexerDataContainer,
    SearchIndexerDataSourceConnection,
    SearchIndexerIndexProjection,
    SearchIndexerIndexProjectionSelector,
    SearchIndexerIndexProjectionsParameters,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

from config import load_config

# ===== Setup: our Azure AI Search clients, and the names of the four pieces we build =====

config = load_config()
credential = DefaultAzureCredential()

index_client = SearchIndexClient(config.search_endpoint, credential)
indexer_client = SearchIndexerClient(config.search_endpoint, credential)
search_client = SearchClient(config.search_endpoint, config.search_index_name, credential)

DATA_SOURCE_NAME = "state-driver-manuals-blob"
SKILLSET_NAME = "state-driver-manuals-skillset"
INDEXER_NAME = "state-driver-manuals-indexer"
INDEX_NAME = config.search_index_name


# ===== Part 1 · Box 1: Data source =====

# Tells Azure AI Search where the PDFs sit in Blob Storage, signing in with its own managed identity.
def create_data_source():
    data_source = SearchIndexerDataSourceConnection(
        name=DATA_SOURCE_NAME,
        type="azureblob",
        connection_string=(
            f"ResourceId=/subscriptions/{config.subscription_id}/resourceGroups/"
            f"{config.resource_group}/providers/Microsoft.Storage/storageAccounts/"
            f"{config.storage_account_name}/;"
        ),
        container=SearchIndexerDataContainer(name=config.storage_container_name),
    )
    indexer_client.create_or_update_data_source_connection(data_source)
    print(f"Data source '{DATA_SOURCE_NAME}' ready.")


# ===== Part 1 · Box 2: Skillset =====

# Tells a skill where in the document to read its input from (InputFieldMappingEntry).
def inputs(**sources):
    return [InputFieldMappingEntry(name=name, source=source) for name, source in sources.items()]


# Tells a skill what to call its result, so later steps can use it (OutputFieldMappingEntry).
def outputs(**targets):
    return [OutputFieldMappingEntry(name=name, target_name=target) for name, target in targets.items()]


# Reads text out of page images by calling Azure AI Services (Azure Vision) for OCR (OcrSkill).
def ocr_skill():
    return OcrSkill(
        context="/document/normalized_images/*",
        default_language_code="en",
        should_detect_orientation=True,
        inputs=inputs(image="/document/normalized_images/*"),
        outputs=outputs(text="text"),
    )


# Puts the OCR text back into the page text, inside Azure AI Search with no extra service (MergeSkill).
def merge_skill():
    return MergeSkill(
        context="/document",
        insert_pre_tag=" ",
        insert_post_tag=" ",
        inputs=inputs(
            text="/document/content",
            itemsToInsert="/document/normalized_images/*/text",
            offsets="/document/normalized_images/*/contentOffset",
        ),
        outputs=outputs(mergedText="merged_text"),
    )


# Attaches our Azure AI Services resource, by key, so the OCR calls can be billed (CognitiveServicesAccountKey).
def ai_services_account():
    return CognitiveServicesAccountKey(key=config.ai_services_key)


# Turns each chunk into its own search document in the index, inside Azure AI Search (SearchIndexerIndexProjection).
def build_index_projection(include_vector=False, include_state=False):
    mappings = inputs(chunk="/document/pages/*", title="/document/title")
    if include_vector:
        mappings += inputs(vector="/document/pages/*/vector")
    if include_state:
        mappings += inputs(state="/document/state")
    return SearchIndexerIndexProjection(
        selectors=[
            SearchIndexerIndexProjectionSelector(
                target_index_name=INDEX_NAME,
                parent_key_field_name="parent_id",
                source_context="/document/pages/*",
                mappings=mappings,
            ),
        ],
        parameters=SearchIndexerIndexProjectionsParameters(
            projection_mode=IndexProjectionMode.SKIP_INDEXING_PARENT_DOCUMENTS,
        ),
    )


# ===== Part 1 · Box 3: Indexer =====

# Tells the indexer to read each PDF's text and details, and to pull out its page images for OCR.
def blob_indexing_parameters():
    return IndexingParameters(
        configuration=IndexingParametersConfiguration(
            data_to_extract="contentAndMetadata",
            image_action="generateNormalizedImages",
            # A blob data source rejects the default query_timeout, so set None.
            query_timeout=None,
        ),
    )


# Copies each blob's file name into the index's title field (FieldMapping).
def title_field_mapping():
    return FieldMapping(source_field_name="metadata_storage_name", target_field_name="title")


# Makes the indexer forget what it already read, retrying while Azure AI Search closes out the last run.
def reset_indexer_with_retry(retries=6, delay=5):
    for attempt in range(retries):
        try:
            indexer_client.reset_indexer(INDEXER_NAME)
            return
        except HttpResponseError as e:
            if attempt == retries - 1:
                raise
            print(f"(reset busy, retrying in {delay}s: {e.message})")
            time.sleep(delay)


# Starts the indexer and waits for its result; reset=True re-reads every PDF from Blob Storage.
def run_and_wait(reset=False, poll_seconds=5):
    if reset:
        reset_indexer_with_retry()
        previous_start = None
    else:
        prior = indexer_client.get_indexer_status(INDEXER_NAME).last_result
        previous_start = prior.start_time if prior else None
    indexer_client.run_indexer(INDEXER_NAME)
    print("Indexer running", end="", flush=True)
    # The previous run can linger briefly, so wait for a result with a new start_time.
    while True:
        last = indexer_client.get_indexer_status(INDEXER_NAME).last_result
        is_new_result = last is not None and last.start_time != previous_start
        if is_new_result and last.status in ("success", "transientFailure", "persistentFailure"):
            print()
            print(f"Status: {last.status} — {last.item_count} item(s), {len(last.errors)} error(s)")
            for err in last.errors[:5]:
                print("  ERROR:", err.error_message)
            return last
        print(".", end="", flush=True)
        time.sleep(poll_seconds)


# ===== Part 1 · Box 4: Index =====

# Creates the Azure AI Search index that holds one searchable document per chunk (SearchIndex).
def create_index():
    index = SearchIndex(
        name=INDEX_NAME,
        fields=[
            # SearchField, not SimpleField: a projection key needs the keyword analyzer.
            SearchField(name="chunk_id", type=SearchFieldDataType.String, key=True,
                        analyzer_name="keyword", filterable=True),
            SimpleField(name="parent_id", type=SearchFieldDataType.String, filterable=True),
            SearchField(name="title", type=SearchFieldDataType.String, filterable=True, sortable=False),
            SearchField(name="chunk", type=SearchFieldDataType.String, searchable=True),
        ],
    )
    index_client.create_or_update_index(index)
    print(f"Index '{INDEX_NAME}' created (title + chunk, no vector field yet).")


# ===== Part 1 · See the results =====

# Prints each search result's rank, its scores, and the fields you ask for.
def show_hits(results, fields=("state", "title", "chunk"), snippet_len=180):
    for i, r in enumerate(results, start=1):
        line = f"{i}. score={r['@search.score']:.3f}"
        if r.get("@search.reranker_score") is not None:
            line += f"  reranker={r['@search.reranker_score']:.3f}"
        print(line)
        for field in fields:
            if field not in r:
                continue
            value = r[field]
            if field == "chunk" and isinstance(value, str):
                value = value.strip().replace("\n", " ")[:snippet_len] + "..."
            print(f"   {field}: {value}")
        print()


# ===== Part 2: Match by meaning =====

# Adds the vector field and a vectorizer that calls our Azure OpenAI embedding model when a query arrives.
def add_vector_search(vectorizer, dimensions=1536):
    index = index_client.get_index(INDEX_NAME)
    index.fields.append(
        SearchField(
            name="vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            # Must equal the embedding skill's dimensions.
            vector_search_dimensions=dimensions,
            vector_search_profile_name="vector-profile",
        )
    )
    index.vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
        profiles=[VectorSearchProfile(
            name="vector-profile",
            algorithm_configuration_name="hnsw-config",
            vectorizer_name=vectorizer.vectorizer_name,
        )],
        vectorizers=[vectorizer],
    )
    index_client.create_or_update_index(index)
    print("Index updated: 'vector' field + vectorizer added.")


# Adds a skill to the skillset already in Azure AI Search, and refreshes which fields each chunk fills.
def add_skill(skill, include_vector=False):
    skillset = indexer_client.get_skillset(SKILLSET_NAME)
    skillset.skills = list(skillset.skills) + [skill]
    skillset.index_projection = build_index_projection(include_vector=include_vector)
    indexer_client.create_or_update_skillset(skillset)
    print("Skillset updated: skill added.")


# ===== Part 3: Filter and rank =====

# Adds one new field to the index that already lives in Azure AI Search (SearchIndex).
def add_index_field(field):
    index = index_client.get_index(INDEX_NAME)
    index.fields.append(field)
    index_client.create_or_update_index(index)
    print(f"Index updated: '{field.name}' field added.")


# Adds one rule telling the indexer how to fill an index field from the blob (SearchIndexer).
def add_field_mapping(mapping):
    indexer = indexer_client.get_indexer(INDEXER_NAME)
    indexer.field_mappings = list(indexer.field_mappings) + [mapping]
    indexer_client.create_or_update_indexer(indexer)
    print(f"Indexer updated: mapping to '{mapping.target_field_name}' added.")


# Rewrites which fields each chunk document gets, such as vector and state (SearchIndexerIndexProjection).
def set_projection(include_vector=True, include_state=False):
    skillset = indexer_client.get_skillset(SKILLSET_NAME)
    skillset.index_projection = build_index_projection(include_vector=include_vector, include_state=include_state)
    indexer_client.create_or_update_skillset(skillset)
    print("Skillset updated: projection refreshed.")


# Turns on the semantic ranker, which reorders the top results with Microsoft's language models (SemanticSearch).
def add_semantic_search(configuration):
    index = index_client.get_index(INDEX_NAME)
    index.semantic_search = SemanticSearch(
        configurations=[configuration],
        default_configuration_name=configuration.name,
    )
    index_client.create_or_update_index(index)
    print("Semantic configuration added (query time only; no indexer re-run).")
