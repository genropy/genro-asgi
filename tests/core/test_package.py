import subprocess
import sys
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
        "AuthMixin",
        "Avatar",
        "BaseApplication",
        "BaseConfiguration",
        "BaseMiddleware",
        "BaseServer",
        "ChannelClient",
        "CommunicationMixin",
        "ConfigError",
        "ConfigurationHandler",
        "ConfigurationProfiles",
        "ConfigurationProfilesApplication",
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
        "HTTPUnprocessableContent",
        "HTTPUnsupportedMediaType",
        "McpApplication",
        "McpEngine",
        "McpError",
        "McpOpenApiApplication",
        "Message",
        "MemorySessionStore",
        "MiddlewareMixin",
        "OpenAPIPlugin",
        "OpenAPITranslator",
        "OpenApiApplication",
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
        "Session",
        "SessionMixin",
        "SessionStore",
        "SiteHome",
        "StorageMixin",
        "TaskGrammar",
        "UploadedFile",
        "UserStore",
        "__version__",
        "router_openapi",
    ]
    assert genro_asgi.__all__ == expected
    for name in expected:
        assert hasattr(genro_asgi, name)


def test_importing_the_core_loads_no_module_of_the_server_app_package():
    # D-SA-2: the core imports nothing of genro_asgi_server_app. Asked in a
    # fresh interpreter, because this one has already imported the package
    # through the tests that exercise it.
    loaded = subprocess.run(
        [
            sys.executable,
            "-c",
            "import genro_asgi, sys; "
            "print([m for m in sys.modules if m.startswith('genro_asgi_server_app')])",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert loaded == "[]"
