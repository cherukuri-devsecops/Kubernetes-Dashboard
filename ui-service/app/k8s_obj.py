"""
K8sObj — dict subclass that supports attribute access on top of normal dict
operations so that Jinja2 templates written for the Kubernetes Python SDK
continue to work with JSON dicts returned by the backend API.

Usage:
    pod  = k8s_obj(response.json())          # single object
    pods = k8s_obj(response.json())          # list → list[K8sObj]

Then in Jinja2:
    {{ pod.metadata.name }}                  # attribute access
    {% for k, v in pod.metadata.labels.items() %}  # dict iteration
    {{ (c.resources.requests or {}).get('cpu', '—') }}  # .get()
"""


class K8sObj(dict):
    """Dict subclass with attribute-style access and None-safe missing keys."""

    def __getattr__(self, name: str):
        try:
            v = dict.__getitem__(self, name)
        except KeyError:
            return None
        return _wrap(v)

    def __bool__(self) -> bool:
        return dict.__len__(self) > 0

    # Ensure pickling / copy work correctly
    def __getstate__(self):
        return dict(self)

    def __setstate__(self, state):
        self.update(state)


def _wrap(v):
    """Recursively wrap dicts → K8sObj and lists → list[wrapped]."""
    if isinstance(v, dict):
        return K8sObj(v)
    if isinstance(v, list):
        return [_wrap(i) for i in v]
    return v


def k8s_obj(data):
    """Wrap a backend JSON response for template compatibility.

    Accepts a single dict or a list of dicts.
    """
    return _wrap(data)
