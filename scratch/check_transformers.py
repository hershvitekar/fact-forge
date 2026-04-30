import ast
_original_parse = ast.parse
def _patched_parse(source, *args, **kwargs):
    try:
        return _original_parse(source, *args, **kwargs)
    except Exception:
        return _original_parse("def dummy(): pass", *args, **kwargs)
ast.parse = _patched_parse

import torch
torch.jit._state.disable()

try:
    from transformers.models.auto.configuration_auto import CONFIG_MAPPING
    print("rt_detr_v2 in CONFIG_MAPPING:", "rt_detr_v2" in CONFIG_MAPPING)
    
    from transformers.models.rt_detr_v2 import RTDetrV2Config
    print("RTDetrV2Config imported successfully")
except Exception as e:
    import traceback
    traceback.print_exc()
