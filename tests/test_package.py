import genro_asgi_core


def test_version():
    assert genro_asgi_core.__version__ == "0.1.0"


def test_root_exports_public_api():
    expected = [
        "ASGIApp",
        "ApiKeyStore",
        "AsgiConfigBuilder",
        "AsgiDbHandlerBase",
        "AsgiServer",
        "AuthCore",
        "AuthMixin",
        "Avatar",
        "BaseApplication",
        "BaseMiddleware",
        "BaseServer",
        "ChannelClient",
        "CommunicationMixin",
        "ConfigurationHandler",
        "FileApiKeyStore",
        "FileSessionStore",
        "FileUserStore",
        "Frame",
        "FrameStream",
        "HTTPException",
        "LocalStorage",
        "LocalStorageNode",
        "Message",
        "MemorySessionStore",
        "MiddlewareMixin",
        "Projection",
        "Receive",
        "Redirect",
        "RegisteredRequest",
        "RequestRegistry",
        "Scope",
        "Send",
        "Session",
        "SessionMixin",
        "SessionStore",
        "StorageMixin",
        "StorageNode",
        "UserStore",
        "__version__",
    ]
    assert genro_asgi_core.__all__ == expected
    for name in expected:
        assert hasattr(genro_asgi_core, name)
