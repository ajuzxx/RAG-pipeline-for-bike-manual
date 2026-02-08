import os
import logging
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path

# Third-party imports
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class IngestionConfig:
    source_dir: str = "bike_manuals"
    persist_dir: str = "./chroma_db"
    # User requested upgrade to a stronger model
    embedding_model: str = "sentence-transformers/all-mpnet-base-v2"
    chunk_size: int = 800  # Smaller chunks for manuals
    chunk_overlap: int = 200
    registry_file: str = "processed_files.json"
    separators: List[str] = field(default_factory=lambda: ["\n\n", "\n", " ", ""])

class DocumentProcessor:
    def __init__(self, config: IngestionConfig):
        self.config = config

    def calculate_file_hash(self, file_path: str) -> str:
        """Calculate MD5 hash of a file to track changes."""
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            buf = f.read()
            hasher.update(buf)
        return hasher.hexdigest()

    def extract_metadata(self, file_path: str) -> Dict:
        """
        Extract metadata from filename. 
        Enriching with 'bike_model' helps in filtering during retrieval.
        """
        filename = os.path.basename(file_path)
        # Attempt to extract bike model (assuming format like "ModelName_Manual.pdf")
        # Simple heuristic: take the first part before _, -, or space
        bike_model = re.split(r'[_\-\s]', filename)[0]
        return {
            "source": filename,
            "bike_model": bike_model,
            "file_path": str(file_path)
        }

    def process_file(self, file_path: str) -> List[Document]:
        """Load, clean, and split a single PDF file."""
        loader = PyPDFLoader(file_path)
        try:
            raw_docs = loader.load()
        except Exception as e:
            logger.error(f"Failed to load {file_path}: {e}")
            return []

        cleaned_docs = []
        for doc in raw_docs:
            # Filter empty or too short pages (likely cover pages or blank)
            if not doc.page_content or len(doc.page_content.strip()) < 50:
                continue
            
            # Enrich metadata
            doc.metadata.update(self.extract_metadata(file_path))
            
            # Basic cleaning
            doc.page_content = self.clean_text(doc.page_content)
            cleaned_docs.append(doc)
            
        # Smart Split
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
            separators=self.config.separators
        )
        return text_splitter.split_documents(cleaned_docs)

    @staticmethod
    def clean_text(text: str) -> str:
        """Remove extra whitespace and artifacts."""
        # Replace multiple newlines with double newline (preserve paragraph structure)
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Replace non-breaking spaces
        text = text.replace('\xa0', ' ')
        return text.strip()

class VectorDatabase:
    def __init__(self, config: IngestionConfig):
        self.config = config
        self.embeddings = HuggingFaceEmbeddings(model_name=self.config.embedding_model)
        self.vectorstore = Chroma(
            persist_directory=self.config.persist_dir,
            embedding_function=self.embeddings
        )
        self.registry = self._load_registry()

    def _load_registry(self) -> Dict[str, str]:
        """Load the processed files registry from JSON."""
        if os.path.exists(self.config.registry_file):
            try:
                with open(self.config.registry_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}

    def _save_registry(self):
        """Save the registry to disk."""
        with open(self.config.registry_file, 'w') as f:
            json.dump(self.registry, f, indent=2)

    def is_processed(self, filename: str, file_hash: str) -> bool:
        """Check if file is already processed with the same hash."""
        return self.registry.get(filename) == file_hash

    def mark_processed(self, filename: str, file_hash: str):
        """Update registry with new file hash."""
        self.registry[filename] = file_hash
        self._save_registry()

    def add_documents(self, documents: List[Document]):
        """Add documents to the Chroma vector store."""
        if not documents:
            return
        
        self.vectorstore.add_documents(documents)
        # self.vectorstore.persist() # Auto-persists in newer versions

    def query(self, query_text: str, k: int = 3):
        """Run a validation query."""
        return self.vectorstore.similarity_search(query_text, k=k)

class RAGPipeline:
    def __init__(self):
        self.config = IngestionConfig()
        self.processor = DocumentProcessor(self.config)
        self.db = VectorDatabase(self.config)

    def run(self):
        logger.info("Starting RAG Ingestion Pipeline...")
        source_path = Path(self.config.source_dir)
        if not source_path.exists():
            logger.error(f"Source directory '{self.config.source_dir}' does not exist.")
            return

        pdf_files = list(source_path.glob("**/*.pdf"))
        logger.info(f"Found {len(pdf_files)} PDF files in {self.config.source_dir}.")

        new_docs_count = 0
        
        for file_path in pdf_files:
            str_path = str(file_path)
            # Calculate hash to check for changes
            file_hash = self.processor.calculate_file_hash(str_path)
            filename = file_path.name
            
            # Incremental Ingestion Check
            if self.db.is_processed(filename, file_hash):
                logger.info(f"Skipping '{filename}' (already processed and unchanged).")
                continue
            
            logger.info(f"Processing '{filename}'...")
            docs = self.processor.process_file(str_path)
            
            if docs:
                self.db.add_documents(docs)
                self.db.mark_processed(filename, file_hash)
                new_docs_count += len(docs)
                logger.info(f"Successfully added {len(docs)} chunks from '{filename}'.")
            else:
                logger.warning(f"No valid content found in '{filename}'.")

        if new_docs_count > 0:
            logger.info(f"Ingestion complete. Total new chunks added: {new_docs_count}")
        else:
            logger.info("Ingestion complete. No new documents to add.")

        # Validation
        self.validate()

    def validate(self):
        logger.info("-" * 40)
        logger.info("Running System Validation Check...")
        test_query = "How to adjust chain slack?" # Generic query relevant to bikes
        logger.info(f"Test Query: '{test_query}'")
        
        results = self.db.query(test_query)
        if results:
            logger.info("Validation SUCCESS. Retrieved relevant context:")
            top_doc = results[0]
            preview = top_doc.page_content[:200].replace('\n', ' ')
            logger.info(f"Top Result Source: {top_doc.metadata.get('source', 'Unknown')}")
            logger.info(f"Top Result Preview: {preview}...")
        else:
            logger.warning("Validation WARNING: Query returned no results. Database might be empty.")

if __name__ == "__main__":
    pipeline = RAGPipeline()
    pipeline.run()  