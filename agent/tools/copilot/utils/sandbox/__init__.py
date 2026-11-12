"""LLM code execution sandbox (no Docker, stdlib only).

Public API:

* :func:`execute_in_sandbox` -- validate and run generated code in a one-shot
  child process, returning a generator of deserialized results.
* :class:`SandboxError` -- raised on policy rejection, timeout or child failure;
  its ``kind`` attribute carries a stable failure code (see the class docstring).
"""

from .executor import SandboxError, execute_in_sandbox

__all__ = ["execute_in_sandbox", "SandboxError"]
