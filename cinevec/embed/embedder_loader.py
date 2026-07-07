from cinevec.embed.download import download_embedding_model
from cinevec.embed.embedder import Embedder
from cinevec.logging import logger
from cinevec.utils.file_utils import load_config_file, path_exists


def get_embedder():
    """Get the embedding model."""
    config = load_config_file()
    model_dir = config.embedding_model_dir 
    model_name = config.embedding_model
    full_model_path = f"{model_dir}/{model_name}"

    if not path_exists(model_dir):
        download_embedding_model(model_name, dest=model_dir)
    return Embedder(path=full_model_path)
