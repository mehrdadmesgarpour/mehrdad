# PDF LLM Chatbot (Web GUI)

This project is a **web-based PDF chatbot** using a simple RAG architecture:

1. Upload PDF files in the Streamlit sidebar.
2. Parse and chunk PDF text.
3. Store chunks in a **Chroma vector database**.
4. Retrieve relevant chunks for each question.
5. Generate answers with an LLM (OpenAI API), or fallback to extractive context if no API key is set.

## Architecture

- **Frontend/UI:** Streamlit chat interface
- **Document ingestion:** `PyPDFLoader`
- **Chunking:** `RecursiveCharacterTextSplitter`
- **Vector database:** Chroma (persistent local storage in `data/chroma`)
- **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2`
- **LLM:** OpenAI Chat Completions (`gpt-4o-mini` by default)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional environment variables:

```bash
export OPENAI_API_KEY="your_api_key"
export OPENAI_MODEL="gpt-4o-mini"
```

## Run

```bash
streamlit run app.py
```

Then open `http://localhost:8501`.

## Notes

- Without `OPENAI_API_KEY`, the app still works and returns extractive context from PDFs.
- Vector DB data is persisted under `data/chroma`.
