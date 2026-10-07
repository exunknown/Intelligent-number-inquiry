"""问数执行过程中的可分类异常。"""

from collections.abc import Mapping

CONVERSATION_CLARIFICATION_REQUIRED = "conversation_clarification_required"


class QueryExecutionError(RuntimeError):
    """携带机器可读错误码和重试语义的执行异常。"""

    def __init__(
        self,
        code: str,
        message: str,
        retryable: bool,
        *,
        details: Mapping[str, object] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = dict(details or {})
