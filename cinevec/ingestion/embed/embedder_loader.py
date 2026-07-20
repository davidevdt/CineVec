from box import ConfigBox

from cinevec.ingestion.embed.download import download_embedding_model
from cinevec.ingestion.embed.embedder import Embedder
from cinevec.utils.file_utils import path_exists


def get_embedder(config: ConfigBox) -> Embedder:
    """Get the embedding model."""
    model_dir = config.embedding_model_dir
    model_name = config.embedding_model
    full_model_path = f"{model_dir}/{model_name}"

    # The model's own folder, not the parent: the parent exists while the model
    # is missing under a mounted volume, or after changing embedding-model.
    if not path_exists(full_model_path):
        download_embedding_model(model_name, dest=model_dir)
    return Embedder(path=full_model_path)
