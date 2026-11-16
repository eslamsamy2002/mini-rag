from .BaseController import BaseController
from stores.llm.LLMEnums import DocumentTypeEnum
from models.df_schemes import Project, DataChunk
from typing import List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class NLPController(BaseController):

    def __init__(self, vectordb_client, generation_client, embedding_client,
                 template_parser):
        super().__init__()
        self.vectordb_client = vectordb_client
        self.generation_client = generation_client
        self.embedding_client = embedding_client
        self.template_parser= template_parser
        
    def _to_dict(self, obj: Any) -> Any:
        """Safely convert Pydantic/Qdrant models to plain dicts."""
        if isinstance(obj, list):
            return [self._to_dict(item) for item in obj]
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return obj

    def create_collection_name(self, project_id: str):
        # Prefer embedding_client size (384) over vectordb default if available
        size = getattr(self.embedding_client, "embedding_size", self.vectordb_client.default_vector_size)
        return f"collection_{size}_{project_id}".strip()
    
    async def reset_vector_db_collection(self, project: Project):
        collection_name = self.create_collection_name(project_id=project.project_id)
        return await self.vectordb_client.delete_collection(collection_name=collection_name)

    async def get_vector_db_collection_info(self, project: Project):
        collection_name = self.create_collection_name(project_id=project.project_id)
        collection_info = await self.vectordb_client.get_collection_info(collection_name=collection_name)
        return self._to_dict(collection_info)

    async def index_into_vector_db(self, project: Project, chunks: List[DataChunk],
                             chunks_ids: List[int], do_reset: bool = False) -> bool:
        # Step 1: get collection name
        collection_name = self.create_collection_name(project_id=project.project_id)

        # Step 2: batch embed chunks (64 per request to respect Cohere limits)
        texts = [c.chunk_text for c in chunks]
        metadata = [c.chunk_metadata for c in chunks]
        vectors = []
        batch_size = 64

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_vectors = self.embedding_client.embed_batch(
                texts=batch_texts,
                document_type=DocumentTypeEnum.DOCUMENT.value
            )
            if not batch_vectors:
                return False
            vectors.extend(batch_vectors)

        # Step 3: create collection if not exists
        _ = await self.vectordb_client.create_collection(
            collection_name=collection_name,
            embedding_size=self.embedding_client.embedding_size,
            do_reset=do_reset,
        )

        # Step 4: insert into vector DB
        is_inserted = await self.vectordb_client.insert_many(
            collection_name=collection_name,
            texts=texts,
            metadata=metadata,
            vectors=vectors,
            record_ids=chunks_ids,
        )

        return is_inserted

    async def search_vector_db_collection(self, project: Project, text: str, limit: int = 10):
        try:
            # 1. Collection Name
            collection_name = self.create_collection_name(project_id=project.project_id)
            logger.info(f"[NLP DEBUG] Checking collection: '{collection_name}'")

            # 2. Embedding
            vectors = self.embedding_client.embed_text(
                text=text,
                document_type=DocumentTypeEnum.QUERY.value
            )
            
            if not vectors:
                logger.error("[NLP DEBUG] Embedding failed: embedding_client returned None or empty")
                return False

            query_vector = vectors[0] if isinstance(vectors[0], list) else vectors
            logger.info(f"[NLP DEBUG] Vector embedded successfully (dim: {len(query_vector)})")

            # 3. Vector DB Search
            results = await self.vectordb_client.search_by_vector(
                collection_name=collection_name,
                vector=query_vector,
                limit=limit
            )

            if results is False:
                logger.error(f"[NLP DEBUG] search_by_vector returned False (collection '{collection_name}' likely does not exist)")
                return False

            if results is None:
                logger.error("[NLP DEBUG] search_by_vector returned None (database query failed)")
                return False

            logger.info(f"[NLP DEBUG] Successfully retrieved {len(results)} records")
            return results

        except Exception as e:
            logger.exception(f"[NLP DEBUG] Unexpected exception in search: {e}")
            return False
    
    async def answer_rag_question(self, project: Project, query: str, limit: int = 10):
        
        
        # step1: retrieve related documents
        retrieved_documents = await self.search_vector_db_collection(
            project=project,
            text=query,
            limit=limit,
        )
        
        if not retrieved_documents or len(retrieved_documents) == 0:
            return None
        
        # step2: Construct LLM prompt
        system_prompt = self.template_parser.get("rag", "system_prompt")

        documents_prompts = "\n".join([
            self.template_parser.get("rag", "document_prompt", {
                    "doc_num": idx + 1,
                    "chunk_text": self.generation_client.process_text(doc.text),
            })
            for idx, doc in enumerate(retrieved_documents)
        ])

        footer_prompt = self.template_parser.get("rag", "footer_prompt",{"query": query})
        
        # step3: Construct Generation Client Prompts
        chat_history = [
            self.generation_client.construct_prompt(
                prompt=system_prompt,
                role=self.generation_client.enums.SYSTEM.value,
            )
        ]

        full_prompt = "\n\n".join([ documents_prompts,  footer_prompt])

        # step4: Retrieve the Answer
        answer = self.generation_client.generate_text(
            prompt=full_prompt,
            chat_history=chat_history
        )

        return answer, full_prompt, chat_history