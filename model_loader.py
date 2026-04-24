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

import gc
import torch
import logging
import spacy
from gliner import GLiNER
from glirel import GLiREL
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, pipeline

import config


class Models:
    """Container for all NLP models with lazy loading to save memory."""

    def __init__(self):
        self._nlp = None
        self._gliner = None
        self._glirel = None
        self._embedder = None
        self._esg_models = {}  # Cache for ESG-BERT models

    @property
    def nlp(self):
        if self._nlp is None:
            logging.info("Loading spaCy model: %s", config.SPACY_MODEL)
            self._nlp = spacy.load(config.SPACY_MODEL)
        return self._nlp

    @property
    def gliner(self):
        if self._gliner is None:
            logging.info("Loading GLiNER model: %s", config.GLINER_MODEL)
            self._gliner = GLiNER.from_pretrained(config.GLINER_MODEL)
        return self._gliner

    @property
    def glirel(self):
        if self._glirel is None:
            logging.info("Loading GLiREL model: %s", config.GLIREL_MODEL)
            self._glirel = GLiREL.from_pretrained(config.GLIREL_MODEL)
        return self._glirel

    @property
    def embedder(self):
        if self._embedder is None:
            logging.info("Loading sentence transformer: %s", config.SENTENCE_TRANSFORMER)
            self._embedder = SentenceTransformer(config.SENTENCE_TRANSFORMER)
        return self._embedder

    def _get_esg_model(self, model_name):
        model_name = model_name or config.ESGBERT_MODEL
        if model_name not in self._esg_models:
            logging.info("Loading ESG classification model: %s", model_name)
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            self._esg_models[model_name] = pipeline(
                "text-classification", 
                model=model_name, 
                tokenizer=tokenizer
            )
        return self._esg_models[model_name]

    @property
    def esg_env(self):
        return self._get_esg_model(config.ESGBERT_MODEL)

    @property
    def esg_social(self):
        return self._get_esg_model(config.ESGBERT_MODEL)

    @property
    def esg_gov(self):
        return self._get_esg_model(config.ESGBERT_MODEL)

    def clear(self, model_attr=None):
        """Unload models from memory."""
        if model_attr:
            logging.info("Unloading model: %s", model_attr)
            if model_attr == 'esg_models':
                self._esg_models = {}
            else:
                setattr(self, f"_{model_attr}", None)
        else:
            logging.info("Unloading all models...")
            self._nlp = None
            self._gliner = None
            self._glirel = None
            self._embedder = None
            self._esg_models = {}
        
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def load_models():
    """Return a Models container (models will load lazily)."""
    return Models()

