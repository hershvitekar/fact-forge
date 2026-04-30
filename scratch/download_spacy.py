import ast
_original_parse = ast.parse
def _patched_parse(source, *args, **kwargs):
    try:
        return _original_parse(source, *args, **kwargs)
    except IndentationError:
        return _original_parse("def dummy(): pass", *args, **kwargs)
ast.parse = _patched_parse

import spacy.cli
spacy.cli.download("en_core_web_trf")
