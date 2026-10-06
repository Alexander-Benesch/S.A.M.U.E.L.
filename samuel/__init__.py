from samuel.build_info import resolve_build_info

# Resolve once at process start.  This keeps the build revision stable even if
# self-mode later changes the same working tree during the process.
__build_info__ = resolve_build_info()
__version__ = __build_info__.product_version

__all__ = ["__build_info__", "__version__"]
