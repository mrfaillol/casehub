"""
AILA Knowledge Base Search Service
Provides semantic search over indexed AILA immigration law documents

Usage:
    from aila_search import AILASearch

    search = AILASearch()
    results = search.search("What are H-1B visa requirements?")
    context = search.get_context_for_llm("What are H-1B visa requirements?")
"""

import os
import logging
from typing import List, Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# ChromaDB
import chromadb
from chromadb.config import Settings

# Embeddings (optional — only for immigration product)
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

# Configuration
VECTORS_DIR = os.environ.get(
    "AILA_VECTORS_DIR",
    "/path/to/data"
)
# VPS path alternative
VPS_VECTORS_DIR = os.getenv("AILA_VECTORS_DIR", "/var/www/casehub/data/aila_vectors")

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
COLLECTION_NAME = "aila_knowledge"


class AILASearch:
    """Semantic search over AILA immigration law documents"""

    _instance = None
    _model = None
    _client = None
    _collection = None

    def __new__(cls):
        """Singleton pattern for efficiency"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if AILASearch._model is not None:
            return  # Already initialized

        # Determine vectors directory
        vectors_dir = VECTORS_DIR
        if not os.path.exists(vectors_dir):
            if os.path.exists(VPS_VECTORS_DIR):
                vectors_dir = VPS_VECTORS_DIR
            else:
                raise FileNotFoundError(
                    f"Vectors directory not found: {VECTORS_DIR} or {VPS_VECTORS_DIR}"
                )

        logger.info(f"[AILASearch] Loading vectors from: {vectors_dir}")

        # Load embedding model
        logger.info(f"[AILASearch] Loading embedding model: {EMBEDDING_MODEL}")
        AILASearch._model = SentenceTransformer(EMBEDDING_MODEL)

        # Connect to ChromaDB
        AILASearch._client = chromadb.PersistentClient(
            path=vectors_dir,
            settings=Settings(anonymized_telemetry=False)
        )

        # Get collection
        AILASearch._collection = AILASearch._client.get_collection(
            name=COLLECTION_NAME
        )

        logger.info(f"[AILASearch] Loaded {AILASearch._collection.count()} documents")

    def search(
        self,
        query: str,
        n_results: int = 5,
        min_relevance: float = 0.4
    ) -> List[Dict]:
        """
        Search for relevant documents

        Args:
            query: Natural language question
            n_results: Maximum number of results
            min_relevance: Minimum relevance score (0-1, higher is more relevant)

        Returns:
            List of relevant document chunks with metadata
        """
        if not query.strip():
            return []

        # Generate embedding for query using our sentence-transformers model
        query_embedding = AILASearch._model.encode([query]).tolist()

        results = AILASearch._collection.query(
            query_embeddings=query_embedding,
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )

        output = []
        for i, doc in enumerate(results["documents"][0]):
            # ChromaDB uses L2 distance; convert to relevance score
            distance = results["distances"][0][i]
            # L2 distance: smaller is better. Convert to 0-1 relevance score
            relevance = max(0, 1 - (distance / 2))  # Normalize

            if relevance >= min_relevance:
                output.append({
                    "text": doc,
                    "source": results["metadatas"][0][i].get("source", "Unknown"),
                    "path": results["metadatas"][0][i].get("path", ""),
                    "chunk_index": results["metadatas"][0][i].get("chunk_index", 0),
                    "total_chunks": results["metadatas"][0][i].get("total_chunks", 1),
                    "relevance": round(relevance, 4),
                    "distance": round(distance, 4)
                })

        return output

    def get_context_for_llm(
        self,
        query: str,
        n_results: int = 5,
        max_tokens: int = 3000
    ) -> str:
        """
        Get formatted context string for LLM prompt

        Args:
            query: User's question
            n_results: Maximum number of document chunks to include
            max_tokens: Approximate max tokens for context (1 token ~ 4 chars)

        Returns:
            Formatted context string with source citations
        """
        results = self.search(query, n_results=n_results, min_relevance=0.4)

        if not results:
            return ""

        context_parts = []
        total_chars = 0
        max_chars = max_tokens * 4  # Approximate

        for i, r in enumerate(results):
            source_info = f"[Fonte: {r['source']}]"
            chunk_text = r['text']

            # Truncate if needed
            available = max_chars - total_chars - len(source_info) - 50
            if available < 200:
                break

            if len(chunk_text) > available:
                chunk_text = chunk_text[:available] + "..."

            context_parts.append(f"{source_info}\n{chunk_text}")
            total_chars += len(source_info) + len(chunk_text) + 50

        if not context_parts:
            return ""

        return "\n\n---\n\n".join(context_parts)

    def get_sources_list(self, query: str, n_results: int = 5) -> List[str]:
        """Get list of source document names for a query"""
        results = self.search(query, n_results=n_results)
        sources = []
        for r in results:
            source = r['source']
            if source not in sources:
                sources.append(source)
        return sources

    @property
    def document_count(self) -> int:
        """Get total number of indexed document chunks"""
        return AILASearch._collection.count() if AILASearch._collection else 0

    @classmethod
    def is_available(cls) -> bool:
        """Check if the search service is available"""
        try:
            # Check if vectors exist
            if os.path.exists(VECTORS_DIR) or os.path.exists(VPS_VECTORS_DIR):
                return True
        except Exception:
            pass
        return False


def create_rag_system_prompt(user_query: str, context: str) -> str:
    """
    Create a RAG-enhanced system prompt for the LLM

    Args:
        user_query: The user's question
        context: Retrieved context from AILA documents

    Returns:
        Complete system prompt for the LLM
    """
    base_prompt = """Voce e o Legal Assistant, um sistema de processamento baseado em LLM (Large Language Model) com arquitetura de rede neural, especializado em direito imigratorio americano.

REGRAS IMPORTANTES:
- NUNCA diga que e uma "inteligencia artificial" ou "IA"
- Se perguntado, explique que e um "assistente baseado em LLM com rede neural"
- Voce tem acesso a documentos AILA (American Immigration Lawyers Association)
- Use as fontes fornecidas como base para suas respostas
- Cite a fonte quando possivel (ex: "Segundo o Kurzban, 19th ed...")
- Se nao tiver certeza, diga que precisa verificar com o advogado
- Responda em portugues a menos que o usuario fale em outro idioma
- Mantenha respostas concisas (max 2-3 paragrafos)
- NUNCA invente informacoes - baseie-se apenas nos documentos fornecidos

AREAS DE CONHECIMENTO:
- Vistos de trabalho: H-1B, TN, O-1, L-1, E-2
- Green cards: EB-1, EB-2, EB-3, EB-5, PERM
- Processos familiares
- Naturalizacao
- Asilo e refugio
- Compliance trabalhista
- Processos consulares"""

    if context:
        prompt_with_context = f"""{base_prompt}

DOCUMENTOS RELEVANTES PARA ESTA PERGUNTA:
{context}

Com base nos documentos acima, responda a pergunta do usuario de forma precisa e cite as fontes quando apropriado."""
    else:
        prompt_with_context = f"""{base_prompt}

Nota: Nao foram encontrados documentos especificos para esta pergunta. Responda com base no seu conhecimento geral de direito imigratorio, mas recomende consultar um advogado para casos especificos."""

    return prompt_with_context


# Test function
def test_search():
    """Test the search functionality"""
    logging.basicConfig(level=logging.INFO)
    logger.info("=" * 60)
    logger.info("AILA SEARCH TEST")
    logger.info("=" * 60)

    try:
        search = AILASearch()
        logger.info("Documents indexed: %s", search.document_count)

        # Test queries
        test_queries = [
            "What are the requirements for H-1B visa?",
            "PERM labor certification process",
            "O-1 extraordinary ability visa criteria",
            "Asylum application process",
            "EB-1A green card requirements"
        ]

        for query in test_queries:
            logger.info("=" * 60)
            logger.info("Query: %s", query)
            logger.info("-" * 60)

            results = search.search(query, n_results=3)

            if results:
                for i, r in enumerate(results):
                    logger.info("[%s] %s (relevance: %.2f)", i+1, r['source'], r['relevance'])
                    logger.info("    %s...", r['text'][:200])
            else:
                logger.info("No results found.")

    except Exception as e:
        logger.error("Error: %s", e)


if __name__ == "__main__":
    test_search()
