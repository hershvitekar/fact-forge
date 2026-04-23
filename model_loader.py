"""
Preload all NLP models at startup.

- spaCy trg
- GLiNER
- GLiREL
- ESGBert (3 models)
- sentence-transformers

No model is ever unloaded during pipeline execution.
Every function receives its model as a parameter rather than loading it
internally.
"""

import logging

import spacy
from gliner import GLiNER
from glirel import GLiREL
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, pipeline

import config


class Models:
    """Container for all NLP models"""

    def __init__(self):
        self.nlp = None  # spaCy
        self.gliner = None
        self.glirel = None
        self.embedder = None  # sentence-transformers
        self.esg_env = None  # ESGBERT Environment
        self.esg_social = None  # ESGBERT Social
        self.esg_gov = None  # ESGBERT Governance


def _load_transformer_pipeline(model_name: str, task: str, **pipeline_kwargs):
    """Create a Hugging Face pipeline for the given task and model."""
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    return pipeline(task, model=model_name, tokenizer=tokenizer, **pipeline_kwargs)


def load_models(
    esg_env_model: str = None,
    esg_social_model: str = None,
    esg_gov_model: str = None,
):
    """Load every NLP model into RAM and return a Models container."""
    models = Models()

    logging.info("Loading spaCy model: %s", config.SPACY_MODEL)
    models.nlp = spacy.load(config.SPACY_MODEL)

    logging.info("Loading GLiNER model: %s", config.GLINER_MODEL)
    models.gliner = GLiNER.from_pretrained(config.GLINER_MODEL)

    logging.info("Loading GLiREL model: %s", config.GLIREL_MODEL)
    models.glirel = GLiREL.from_pretrained(config.GLIREL_MODEL)

    logging.info("Loading sentence transformer: %s", config.SENTENCE_TRANSFORMER)
    models.embedder = SentenceTransformer(config.SENTENCE_TRANSFORMER)

    esg_env_model = esg_env_model or config.ESGBERT_MODEL
    esg_social_model = esg_social_model or config.ESGBERT_MODEL
    esg_gov_model = esg_gov_model or config.ESGBERT_MODEL

    logging.info("Loading ESG environment model: %s", esg_env_model)
    models.esg_env = _load_transformer_pipeline(
        esg_env_model,
        task="text-classification",
    )

    logging.info("Loading ESG social model: %s", esg_social_model)
    models.esg_social = _load_transformer_pipeline(
        esg_social_model,
        task="text-classification",
    )

    logging.info("Loading ESG governance model: %s", esg_gov_model)
    models.esg_gov = _load_transformer_pipeline(
        esg_gov_model,
        task="text-classification",
    )

    return models

