class AIModuleError(Exception):
    HTTP_STATUS = {"config": 503, "auth": 502, "timeout": 504, "unavailable": 502,
                   "bad_response": 502, "bad_input": 422}

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message

    @property
    def http_status(self) -> int:
        return self.HTTP_STATUS.get(self.kind, 502)
