from langchain_core.documents import Document

from app import split_documents


def test_split_documents_returns_chunks():
    docs = [Document(page_content="A" * 2500)]
    chunks = split_documents(docs)
    assert len(chunks) > 1
    assert all(chunk.page_content for chunk in chunks)
