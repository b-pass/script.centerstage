import json

from jsonrpc import Rpc


class FakeRpc(Rpc):
    """Rpc whose methods are answered by handlers: {method: fn(params) -> result}."""

    def __init__(self, handlers):
        self.handlers = handlers
        self.calls = []
        super().__init__(self._execute)

    def _execute(self, raw):
        request = json.loads(raw)
        params = request.get('params', {})
        self.calls.append((request['method'], params))
        handler = self.handlers.get(request['method'])
        if handler is None:
            return json.dumps({'id': request['id'], 'error': {'code': -32601,
                                                                'message': 'Method not found.'}})
        result = handler(params)
        if isinstance(result, Exception):
            return json.dumps({'id': request['id'], 'error': {'code': -32100,
                                                                'message': str(result)}})
        return json.dumps({'id': request['id'], 'result': result})
