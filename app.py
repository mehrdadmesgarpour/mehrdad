import os
from dataclasses import dataclass
from typing import List

import streamlit as st
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

try:
    from openai import OpenAI
except Exception:  # noqa: BLE001
    OpenAI = None


DATA_DIR = "data/chroma"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass
class ChatConfig:
    persist_directory: str = DATA_DIR
    embedding_model: str = EMBED_MODEL


@st.cache_resource(show_spinner=False)
def get_embeddings(model_name: str):
    return HuggingFaceEmbeddings(model_name=model_name)


def load_pdf_documents(uploaded_files) -> List[Document]:
    docs: List[Document] = []
    os.makedirs("data/uploads", exist_ok=True)

    for uploaded in uploaded_files:
        file_path = os.path.join("data/uploads", uploaded.name)
        with open(file_path, "wb") as f:
            f.write(uploaded.getbuffer())

        loader = PyPDFLoader(file_path)
        docs.extend(loader.load())

    return docs


def split_documents(documents: List[Document]) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    return splitter.split_documents(documents)


def build_vector_store(chunks: List[Document], config: ChatConfig) -> Chroma:
    embeddings = get_embeddings(config.embedding_model)
    vectordb = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=config.persist_directory,
    )
    return vectordb


def load_vector_store(config: ChatConfig) -> Chroma:
    embeddings = get_embeddings(config.embedding_model)
    return Chroma(
        persist_directory=config.persist_directory,
        embedding_function=embeddings,
    )


def generate_answer(question: str, contexts: List[Document]) -> str:
    joined_context = "\n\n".join([c.page_content for c in contexts[:4]])

    if OpenAI is not None and os.getenv("OPENAI_API_KEY"):
        client = OpenAI()
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful PDF assistant. Use only the provided context. "
                        "If context is missing, say you don't know."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Context:\n{joined_context}\n\nQuestion: {question}",
                },
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or "No answer produced."

    if not joined_context.strip():
        return "I could not find relevant information in the uploaded PDFs."

    return (
        "OpenAI API key not configured, so here is an extractive answer from the PDF context:\n\n"
        f"{joined_context[:1200]}"
    )


def main():
    st.set_page_config(page_title="PDF Chatbot", page_icon="📄", layout="wide")
    st.title("📄 LLM PDF Chatbot")
    st.caption("Upload PDF files, index them into a vector database, and chat with their content.")

    config = ChatConfig()

    with st.sidebar:
        st.header("Knowledge Base")
        uploaded_files = st.file_uploader(
            "Upload one or more PDFs",
            type=["pdf"],
            accept_multiple_files=True,
        )

        if st.button("Build / Refresh PDF Database", use_container_width=True):
            if not uploaded_files:
                st.warning("Please upload at least one PDF.")
            else:
                with st.spinner("Reading PDFs and building vector DB..."):
                    documents = load_pdf_documents(uploaded_files)
                    chunks = split_documents(documents)
                    build_vector_store(chunks, config)
                st.success(f"Done! Indexed {len(chunks)} chunks from {len(uploaded_files)} file(s).")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    question = st.chat_input("Ask something about your PDFs")

    for role, content in st.session_state.chat_history:
        with st.chat_message(role):
            st.markdown(content)

    if question:
        st.session_state.chat_history.append(("user", question))
        with st.chat_message("user"):
            st.markdown(question)

        if not os.path.isdir(config.persist_directory):
            answer = "Please build the PDF database first using the sidebar button."
        else:
            vectordb = load_vector_store(config)
            contexts = vectordb.similarity_search(question, k=4)
            answer = generate_answer(question, contexts)

        st.session_state.chat_history.append(("assistant", answer))
        with st.chat_message("assistant"):
            st.markdown(answer)


if __name__ == "__main__":
    main()
