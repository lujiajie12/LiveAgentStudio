"""Graph package.

Keep package initialization side-effect free so submodule imports do not
accidentally create circular dependencies during app startup.
"""

__all__: list[str] = []
