from cinevec.ingestion.embed.download import download_embedding_model
from cinevec.ingestion.embed.embedder import Embedder
from cinevec.utils.file_utils import path_exists
from box import ConfigBox


def get_embedder(config: ConfigBox) -> Embedder:
    """Get the embedding model."""
    model_dir = config.embedding_model_dir
    model_name = config.embedding_model
    full_model_path = f"{model_dir}/{model_name}"

    if not path_exists(model_dir):
        download_embedding_model(model_name, dest=model_dir)
    return Embedder(path=full_model_path)
