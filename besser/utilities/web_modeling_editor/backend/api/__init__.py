# Lazy import to avoid pulling in the full services/__init__.py chain
# which requires optional dependencies like bocl, deep_translator, etc.
def __getattr__(name):
    if name == "editor_workflow_router":
        from besser.utilities.web_modeling_editor.backend.api.editor_workflow_api import router
        return router
    raise AttributeError(name)
