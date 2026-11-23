import argparse
import os
from functools import lru_cache
from hashlib import file_digest, sha256
from itertools import batched
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

from evidence_store import PUBLISHED_PASSAGES, ROOT, database_path, evidence_db

MODEL_NAME = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
COLLECTION = "published_multilingual_e5_small_v1"
MODEL_FILES = {
    "model.onnx": ("onnx/model_qint8_avx512_vnni.onnx", "dd476dd0c2514e9b9be83aeb3853fac0763e0bdf4a71645407587d77c48a2d88"),
    "tokenizer.json": ("tokenizer.json", "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39"),
}
TOPIC_LABELS = {
    "irrigation": "rice irrigation, field drainage, soil moisture · వరి సాగునీరు, నీటి పారుదల, నేల తేమ · धान की सिंचाई, जल निकासी, मिट्टी की नमी",
    "harvest": "rice harvest, crop maturity, storage · వరి కోత, పంట పరిపక్వత, నిల్వ · धान की कटाई, फसल पकना, भंडारण",
    "spraying": "field spraying, dry leaves · పిచికారీ, ఆకులు ఆరడం · छिड़काव, सूखी पत्तियाँ",
    "grain-drying": "drying harvested grain, grain moisture · కోసిన ధాన్యం ఆరబెట్టడం, ధాన్యం తేమ · कटे धान को सुखाना, अनाज की नमी",
    "district-rainfall-forecast": "district rainfall forecast, rain in millimeters · జిల్లా వర్షపాత అంచనా, వర్షం మిల్లీమీటర్లు · ज़िले का वर्षा पूर्वानुमान, मिलीमीटर बारिश",
}


class EvidenceIndexUnavailable(RuntimeError):
    pass


def evidence_mode():
    mode = os.environ.get("AGRIRAG_EVIDENCE_MODE", "chroma")
    if mode not in ("chroma", "sqlite"):
        raise ValueError("AGRIRAG_EVIDENCE_MODE must be chroma or sqlite.")
    return mode


def model_directory():
    return Path(os.environ.get("AGRIRAG_E5_DIR", ROOT / "data" / "e5-small"))


def artifact_hash(path):
    with path.open("rb") as file:
        return file_digest(file, "sha256").hexdigest()


def download_model():
    directory = model_directory()
    directory.mkdir(parents=True, exist_ok=True)
    for name, (remote, expected) in MODEL_FILES.items():
        destination = directory / name
        if destination.is_file() and artifact_hash(destination) == expected:
            continue
        url = f"https://huggingface.co/{MODEL_NAME}/resolve/{MODEL_REVISION}/{remote}"
        with NamedTemporaryFile(dir=directory, suffix=".part", delete=False) as temporary:
            temporary_path = Path(temporary.name)
        try:
            digest = sha256()
            with urlopen(url, timeout=60) as response, temporary_path.open("wb") as output:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != expected:
                raise EvidenceIndexUnavailable(f"Checksum verification failed for {name}.")
            temporary_path.replace(destination)
        finally:
            temporary_path.unlink(missing_ok=True)


@lru_cache(maxsize=2)
def encoder(model_dir):
    import onnxruntime as ort
    from tokenizers import Tokenizer

    directory = Path(model_dir)
    model = directory / "model.onnx"
    tokenizer_file = directory / "tokenizer.json"
    if not model.is_file() or not tokenizer_file.is_file():
        raise EvidenceIndexUnavailable("Install the multilingual E5 ONNX model before using evidence retrieval.")
    options = ort.SessionOptions()
    options.intra_op_num_threads = min(4, os.cpu_count() or 1)
    options.inter_op_num_threads = 1
    tokenizer = Tokenizer.from_file(str(tokenizer_file))
    tokenizer.enable_truncation(max_length=512)
    tokenizer.enable_padding(pad_id=1, pad_token="<pad>")
    return tokenizer, ort.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])


def embed(texts, role):
    import numpy as np

    tokenizer, model = encoder(str(model_directory().resolve()))
    tokens = tokenizer.encode_batch([f"{role}: {text}" for text in texts])
    attention = np.array([item.attention_mask for item in tokens], dtype=np.int64)
    arrays = {
        "input_ids": np.array([item.ids for item in tokens], dtype=np.int64),
        "attention_mask": attention,
        "token_type_ids": np.array([item.type_ids for item in tokens], dtype=np.int64),
    }
    hidden = model.run(None, {entry.name: arrays[entry.name] for entry in model.get_inputs()})[0]
    pooled = (hidden * attention[:, :, None]).sum(axis=1) / attention.sum(axis=1, keepdims=True)
    return (pooled / np.linalg.norm(pooled, axis=1, keepdims=True)).astype(np.float32).tolist()


@lru_cache(maxsize=4)
def collection_at(path):
    import chromadb

    client = chromadb.PersistentClient(path=path, settings=chromadb.Settings(anonymized_telemetry=False))
    return client.get_or_create_collection(
        COLLECTION, embedding_function=None, configuration={"hnsw": {"space": "cosine"}},
    )


def collection():
    path = os.environ.get("AGRIRAG_CHROMA_PATH", database_path().with_suffix(".chroma"))
    return collection_at(str(Path(path).resolve()))


def passage_text(passage):
    topic = passage["topic"] or ""
    return " ".join(filter(None, (
        TOPIC_LABELS.get(topic, topic.replace("-", " ")),
        passage["crop"], passage["crop_stage"], passage["content"],
    )))


def sync(index, passages):
    """Upsert changed published records. Approval and scope always come from SQLite."""
    for batch in batched(passages, 64):
        texts = {row["id"]: passage_text(row) for row in batch}
        hashes = {id_: sha256(text.encode()).hexdigest() for id_, text in texts.items()}
        stored = index.get(ids=list(texts), include=["metadatas"])
        signatures = dict(zip(stored["ids"], stored["metadatas"]))
        changed = [id_ for id_, fingerprint in hashes.items() if (signatures.get(id_) or {}).get("fingerprint") != fingerprint]
        if changed:
            index.upsert(
                ids=changed, embeddings=embed([texts[id_] for id_ in changed], "passage"),
                metadatas=[{"fingerprint": hashes[id_]} for id_ in changed],
            )


def rank(question, passages):
    if not passages:
        return []
    if evidence_mode() == "sqlite":
        # Applicability is checked before ranking. Keep every candidate for conflict detection.
        return sorted(passages, key=lambda row: row["id"])
    index = collection()
    sync(index, passages)
    query_embedding = embed([question], "query")
    by_id = {row["id"]: row for row in passages}
    distances = []
    # Rank every eligible candidate so a lower-ranked contradictory source cannot disappear.
    for batch in batched(by_id, 128):
        result = index.query(query_embeddings=query_embedding, ids=list(batch), n_results=len(batch), include=["distances"])
        distances.extend(zip(result["distances"][0], result["ids"][0]))
    if {id_ for _, id_ in distances} != by_id.keys():
        raise EvidenceIndexUnavailable("Chroma did not return every eligible evidence passage.")
    return [by_id[id_] for _, id_ in sorted(distances)]


def prepare_index(install_model):
    if evidence_mode() == "sqlite":
        print("SQLite evidence mode enabled. Vector indexing skipped.")
        return
    if install_model:
        download_model()
    with evidence_db() as connection:
        published = connection.execute(PUBLISHED_PASSAGES).fetchall()
    if published:
        sync(collection(), published)
    print(f"Indexed {len(published)} published evidence passages.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare retrieval for the published evidence catalog.")
    parser.add_argument("--download-model", action="store_true", help="Install the pinned E5 ONNX artifacts and verify their checksums.")
    args = parser.parse_args()
    prepare_index(args.download_model)
