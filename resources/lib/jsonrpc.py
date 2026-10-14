# -*- coding: utf-8 -*-
"""Thin JSON-RPC client. Kodi-free: inside Kodi the executor is xbmc.executeJSONRPC."""
import json


class RpcError(Exception):
    pass


class Rpc:
    def __init__(self, executor):
        self.executor = executor
        self._next_id = 0

    def call(self, method, **params):
        self._next_id += 1
        request = {'jsonrpc': '2.0', 'id': self._next_id, 'method': method}
        if params:
            request['params'] = params
        raw = self.executor(json.dumps(request))
        try:
            response = json.loads(raw)
        except (TypeError, ValueError) as e:
            raise RpcError(f'{method}: unreadable response') from e
        if 'error' in response:
            err = response['error']
            raise RpcError(f'{method}: {err.get("message", err)}')
        return response.get('result') or {}
