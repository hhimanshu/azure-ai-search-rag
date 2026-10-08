"""Module 2 helpers. Each function wraps one Azure AI Search SDK class and names the clip that uses it."""

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

# ---- Setup: clients and resource names ----

config = load_config()
credential = DefaultAzureCredential()

index_client = SearchIndexClient(config.search_endpoint, credential)
indexer_client = SearchIndexerClient(config.search_endpoint, credential)
search_client = SearchClient(config.search_endpoint, config.search_index_name, credential)

DATA_SOURCE_NAME = "state-driver-manuals-blob"
SKILLSET_NAME = "state-driver-manuals-skillset"
INDEXER_NAME = "state-driver-manuals-indexer"
INDEX_NAME = config.search_index_name


# ---- Clip 1: data source, skillset, indexer, index ----


def inputs(**sources):
    """InputFieldMappingEntry list for a skill: inputs(text="/document/content")."""
    return [InputFieldMappingEntry(name=name, source=source) for name, source in sources.items()]


def outputs(**targets):
    """OutputFieldMappingEntry list for a skill: outputs(textItems="pages")."""
    return [OutputFieldMappingEntry(name=name, target_name=target) for name, target in targets.items()]


def create_data_source():
    """SearchIndexerDataSourceConnection: points the indexer at the PDF container, signing in as the service's managed identity."""
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


def create_index():
    """SearchIndex: one search document per chunk, with chunk_id, parent_id, title, and chunk."""
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


def ocr_skill():
    """OcrSkill: reads the text out of the page images."""
    return OcrSkill(
        context="/document/normalized_images/*",
        default_language_code="en",
        should_detect_orientation=True,
        inputs=inputs(image="/document/normalized_images/*"),
        outputs=outputs(text="text"),
    )


def merge_skill():
    """MergeSkill: puts the OCR text back into the page text."""
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


def build_index_projection(include_vector=False, include_state=False):
    """SearchIndexerIndexProjection: turns each chunk into its own search document."""
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


def ai_services_account():
    """CognitiveServicesAccountKey: the key-based billing attachment the OCR skill needs."""
    return CognitiveServicesAccountKey(key=config.ai_services_key)


def blob_indexing_parameters():
    """IndexingParameters: read PDF text and metadata, and extract the page images for OCR."""
    return IndexingParameters(
        configuration=IndexingParametersConfiguration(
            data_to_extract="contentAndMetadata",
            image_action="generateNormalizedImages",
            # A blob data source rejects the default query_timeout, so set None.
            query_timeout=None,
        ),
    )


def title_field_mapping():
    """FieldMapping: copies the blob file name into the title field."""
    return FieldMapping(source_field_name="metadata_storage_name", target_field_name="title")


def reset_indexer_with_retry(retries=6, delay=5):
    """Retries reset_indexer(): a just-finished run can look in progress for a few seconds."""
    for attempt in range(retries):
        try:
            indexer_client.reset_indexer(INDEXER_NAME)
            return
        except HttpResponseError as e:
            if attempt == retries - 1:
                raise
            print(f"(reset busy, retrying in {delay}s: {e.message})")
            time.sleep(delay)


def run_and_wait(reset=False, poll_seconds=5):
    """Runs the indexer and waits for a new result; reset=True reprocesses every blob."""
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


def show_hits(results, fields=("state", "title", "chunk"), snippet_len=180):
    """Prints each result's rank, scores, and the fields you ask for."""
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


# ---- Clip 2: embeddings and vector search ----


def add_vector_search(vectorizer, dimensions=1536):
    """VectorSearch: adds the vector field and an HNSW profile that uses your vectorizer; dimensions must match the embedding skill."""
    index = index_client.get_index(INDEX_NAME)
    index.fields.append(
        SearchField(
            name="vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
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


def add_skill(skill, include_vector=False):
    """SearchIndexerSkillset: appends a skill to the live skillset and refreshes the projection."""
    skillset = indexer_client.get_skillset(SKILLSET_NAME)
    skillset.skills = list(skillset.skills) + [skill]
    skillset.index_projection = build_index_projection(include_vector=include_vector)
    indexer_client.create_or_update_skillset(skillset)
    print("Skillset updated: skill added.")


# ---- Clip 3: filters and semantic ranking ----


def add_index_field(field):
    """SearchIndex: adds one field to the live index."""
    index = index_client.get_index(INDEX_NAME)
    index.fields.append(field)
    index_client.create_or_update_index(index)
    print(f"Index updated: '{field.name}' field added.")


def add_field_mapping(mapping):
    """SearchIndexer: adds one field mapping to the live indexer."""
    indexer = indexer_client.get_indexer(INDEXER_NAME)
    indexer.field_mappings = list(indexer.field_mappings) + [mapping]
    indexer_client.create_or_update_indexer(indexer)
    print(f"Indexer updated: mapping to '{mapping.target_field_name}' added.")


def set_projection(include_vector=True, include_state=False):
    """SearchIndexerIndexProjection: rebuilds the live skillset's projection with the fields you choose."""
    skillset = indexer_client.get_skillset(SKILLSET_NAME)
    skillset.index_projection = build_index_projection(include_vector=include_vector, include_state=include_state)
    indexer_client.create_or_update_skillset(skillset)
    print("Skillset updated: projection refreshed.")


def add_semantic_search(configuration):
    """SemanticSearch: attaches your semantic configuration to the live index as the default."""
    index = index_client.get_index(INDEX_NAME)
    index.semantic_search = SemanticSearch(
        configurations=[configuration],
        default_configuration_name=configuration.name,
    )
    index_client.create_or_update_index(index)
    print("Semantic configuration added (query time only; no indexer re-run).")
