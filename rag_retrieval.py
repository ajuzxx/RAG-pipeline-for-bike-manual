import os
from dotenv import load_dotenv

# Global variables
vector_store = None
llm = None
PROMPT = None

def initialize_rag():
    global vector_store, llm, PROMPT
    try:
        print("Initializing RAG pipeline (Manual Mode)...")
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_huggingface import HuggingFaceEmbeddings
        from langchain_community.vectorstores import Chroma
        from langchain_core.prompts import PromptTemplate

        # Load environment variables from .env file
        load_dotenv()
        
        # Read API Key from environment variable
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set. Please create a .env file or set the variable.")
        os.environ["GOOGLE_API_KEY"] = api_key

        # Initialize Embeddings
        print("Loading embeddings...")
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")

        # Load Vector DB
        print("Loading Vector DB...")
        vector_store = Chroma(persist_directory="./chroma_db", embedding_function=embeddings)

        # Initialize LLM
        print("Loading LLM...")
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite")

        # Create Custom Prompt Template
        template = """Use the following pieces of context to answer the question at the end.
If you don't know the answer, just say that you don't know, don't try to make up an answer.
IMPORTANT: After answering, please provide a 'Context Adherence Score' (0-100%) indicating how much of your answer is based strictly on the provided context vs your general knowledge.

Context:
{context}

Question: {question}

Answer:"""

        PROMPT = PromptTemplate(
            template=template, input_variables=["context", "question"]
        )
        print("RAG pipeline initialized successfully.")

    except Exception as e:
        print(f"Failed to initialize RAG: {e}")
        raise e

def get_answer(question):
    global vector_store, llm, PROMPT
    
    # Initialize if needed
    if vector_store is None:
        try:
            initialize_rag()
        except Exception as e:
            return {"result": f"System Error: Failed to initialize RAG pipeline. {e}", "source_documents": []}

    print(f"Question: {question}")
    try:
        # 1. Retrieve relevant documents
        print("Retrieving documents...")
        source_documents = vector_store.similarity_search(question, k=4)
        
        # 2. Prepare Context
        context = "\n\n".join([doc.page_content for doc in source_documents])
        
        # 3. Generate Answer
        print("Generating answer...")
        formatted_prompt = PROMPT.format(context=context, question=question)
        response = llm.invoke(formatted_prompt)
        
        # Response is an AIMessage object
        result_text = response.content
        
        return {
            "result": result_text,
            "source_documents": source_documents
        }  
    except Exception as e:
        print(f"Error running chain: {e}")
        import traceback
        traceback.print_exc()
        return {"result": f"Error: {e}", "source_documents": []}

if __name__ == "__main__":
    question = "How do I check the engine oil level?"
    result = get_answer(question)
    print("\nAnswer:")
    print(result.get('result', 'No result'))
    
    print("\n" + "="*40)
    print("SOURCE DOCUMENTS USED:")
    print("="*40)
    if 'source_documents' in result:
        for i, doc in enumerate(result['source_documents']):
            print(f"\nDocument {i+1}:")
            print(f"Source: {doc.metadata.get('source', 'Unknown')}")
            print(f"Content Preview: {doc.page_content[:200]}...")
            print("-" * 20)

