import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from rag_retrieval import get_answer
import glob

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/manuals", StaticFiles(directory="bike_manuals"), name="manuals")

class Query(BaseModel):
    question: str

@app.get("/")
async def read_root():
    return {"message": "Welcome to Bike RAG API. Go to /static/index.html to use the UI."}

@app.post("/api/chat")
async def chat(query: Query):
    try:
        response = get_answer(query.question)
        
        # Serialize source documents
        sources = []
        if "source_documents" in response:
            for doc in response["source_documents"]:
                sources.append({
                    "content": doc.page_content,
                    "source": os.path.basename(doc.metadata.get("source", "")),
                    "page": doc.metadata.get("page", "Unknown")
                })
        
        return {
            "answer": response["result"],
            "sources": sources
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sources")
async def get_sources():
    # List all PDFs in the bike_manuals directory
    files = glob.glob("bike_manuals/*.pdf")
    return {"files": [os.path.basename(f) for f in files]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
