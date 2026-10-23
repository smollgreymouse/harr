"""Shared protocol and backend abstraction for Harr Einherjar."""
from common.executor.protocol import WORKER_CONTRACT, extract_json_object, is_worker_handoff_text, parse_worker_handoff
from common.executor.backends import (
    BackendAdapter, BackendCapabilities, BackendStartRequest, BackendResumeRequest,
    einherjar_config_path, get_backend_adapter, get_builtin_backend_names,
    list_available_backends, load_einherjar_config, probe_backend, resolve_backend,
    resolve_backend_name,
)
__all__ = [
    "WORKER_CONTRACT", "extract_json_object", "is_worker_handoff_text", "parse_worker_handoff",
    "BackendAdapter", "BackendCapabilities", "BackendStartRequest", "BackendResumeRequest",
    "einherjar_config_path", "get_backend_adapter", "get_builtin_backend_names",
    "list_available_backends", "load_einherjar_config", "probe_backend", "resolve_backend",
    "resolve_backend_name",
]
