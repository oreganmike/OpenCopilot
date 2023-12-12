import os
from typing import List, Dict
from langchain.vectorstores.base import VectorStore
from routes.workflow.utils.document_similarity_dto import DocumentSimilarityDTO
from shared.utils.opencopilot_utils import StoreOptions
from shared.utils.opencopilot_utils.get_vector_store import get_vector_store
from utils.chat_models import CHAT_MODELS
from utils.get_chat_model import get_chat_model
from utils.get_logger import CustomLogger
from utils.llm_consts import vs_thresholds
from qdrant_client import QdrantClient, models
from langchain.docstore.document import Document
from shared.utils.opencopilot_utils.get_embeddings import get_embeddings

client = QdrantClient(url=os.getenv("QDRANT_URL", "http://qdrant:6333"))
logger = CustomLogger(module_name=__name__)
chat = get_chat_model(CHAT_MODELS.gpt_3_5_turbo_16k)

stores = {
    "knowledgebase": get_vector_store(StoreOptions("knowledgebase")),
    "flows": get_vector_store(StoreOptions("flows")),
    "actions": get_vector_store(StoreOptions("actions")),
}

# Define score thresholds for each collection
score_thresholds: Dict[str, float] = {
    "knowledgebase": vs_thresholds.get("kb_score_threshold"),
    "flows": vs_thresholds.get("flows_score_threshold"),
    "actions": vs_thresholds.get("actions_score_threshold"),
}


async def get_relevant_documents(
    text: str, bot_id: str, collection_name: str
) -> List[DocumentSimilarityDTO]:
    try:
        embedding = get_embeddings()
        query_vector = embedding.embed_query(text)

        query_response = client.search(
            collection_name=collection_name,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.bot_id",
                        match=models.MatchValue(value=bot_id),
                    )
                ]
            ),
            query_vector=query_vector,
            with_payload=True,
            limit=4,
            search_params=models.SearchParams(hnsw_ef=128, exact=False),
            score_threshold=score_thresholds.get(collection_name, 0.0),
        )

        documents_with_similarity: List[DocumentSimilarityDTO] = []
        for response in query_response:
            payload = response.payload

            if not payload:
                continue

            documents_with_similarity.append(
                DocumentSimilarityDTO(
                    score=response.score,
                    type=collection_name,
                    document=Document(
                        page_content=payload.get("page_content", ""),
                        metadata=payload.get("metadata", {}),
                    ),
                )
            )

        return documents_with_similarity

    except Exception as e:
        logger.error(
            f"Error occurred while getting relevant {collection_name} summaries",
            incident=f"get_relevant_{collection_name}",
            payload=text,
            error=str(e),
        )
        return []


async def get_relevant_actions(text: str, bot_id: str) -> List[DocumentSimilarityDTO]:
    return await get_relevant_documents(text, bot_id, "actions")


async def get_relevant_flows(text: str, bot_id: str) -> List[DocumentSimilarityDTO]:
    return await get_relevant_documents(text, bot_id, "flows")


async def get_relevant_knowledgebase(
    text: str, bot_id: str
) -> List[DocumentSimilarityDTO]:
    return await get_relevant_documents(text, bot_id, "knowledgebase")
