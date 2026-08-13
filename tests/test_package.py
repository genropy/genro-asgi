from importlib.metadata import version

import genro_asgi


def test_version():
    # The contract of #16: __version__ IS the installed distribution's
    # version — never a literal that a release bump can leave behind.
    assert genro_asgi.__version__ == version("genro-asgi")


def test_root_exports_public_api():
    expected = [
        "ASGIApp",
        "ApiKeyStore",
        "ApplicationGrammar",
        "AsgiConfigBuilder",
        "AsgiDbHandlerBase",
        "AsgiServer",
        "AsgiServerGrammar",
        "AuthCore",
        "AuthMethod",
        "AuthMixin",
        "AuthSection",
        "Avatar",
        "BaseApplication",
        "BaseConfiguration",
        "BaseMiddleware",
        "BaseServer",
        "ChannelClient",
        "CommunicationMixin",
        "ConfigError",
        "ConfigurationHandler",
        "DefaultConfig",
        "FileApiKeyStore",
        "FileUserStore",
        "Frame",
        "FrameStream",
        "HTTPBadRequest",
        "HTTPException",
        "HTTPForbidden",
        "HTTPNotFound",
        "HTTPUnauthorized",
        "McpApplication",
        "McpEngine",
        "McpError",
        "McpOpenApiApplication",
        "Message",
        "MemorySessionStore",
        "MiddlewareMixin",
        "OidcMethod",
        "OpenAPIPlugin",
        "OpenAPITranslator",
        "OpenApiApplication",
        "PasswordMethod",
        "PluginMixin",
        "Receive",
        "Redirect",
        "RegisteredRequest",
        "Request",
        "RequestRegistry",
        "Response",
        "RoutedApplication",
        "Scope",
        "Send",
        "ServerApplication",
        "Session",
        "SessionMixin",
        "SessionStore",
        "StorageMixin",
        "TaskGrammar",
        "UserStore",
        "__version__",
        "router_openapi",
    ]
    assert genro_asgi.__all__ == expected
    for name in expected:
        assert hasattr(genro_asgi, name)
