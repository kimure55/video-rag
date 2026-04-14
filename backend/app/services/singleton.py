from app.services.chroma_service import ChromaService

_chroma_service: ChromaService = None


def get_chroma_service() -> ChromaService:
    global _chroma_service
    if _chroma_service is None:
        _chroma_service = ChromaService()
    return _chroma_service


def init_chroma_service():
    get_chroma_service()
