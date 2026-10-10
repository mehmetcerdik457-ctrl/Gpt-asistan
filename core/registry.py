"""Simple registry for tools and agents."""


class Registry:
    def __init__(self):
        self._tools = {}
        self._agents = {}

    def tool(self, name=None):
        def deco(fn):
            self.register_tool(name or fn.__name__, fn)
            return fn
        return deco

    def register_tool(self, name, fn):
        if name in self._tools:
            raise ValueError("tool already registered: " + name)
        self._tools[name] = fn

    def register_agent(self, name, agent):
        if name in self._agents:
            raise ValueError("agent already registered: " + name)
        self._agents[name] = agent

    def call_tool(self, name, *args, **kwargs):
        if name not in self._tools:
            raise KeyError("unknown tool: " + name)
        return self._tools[name](*args, **kwargs)

    def get_agent(self, name):
        return self._agents[name]

    def tools(self):
        return sorted(self._tools)

    def agents(self):
        return sorted(self._agents)
