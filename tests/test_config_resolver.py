from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lib.config.resolver import ConfigResolver
from lib.config.service import ProviderStatus
from lib.db.base import Base


async def _make_session():
    """Create an in-memory SQLite database and return ``(factory, engine)``."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory, engine


def _make_ready_provider(name: str, media_types: list[str]) -> ProviderStatus:
    return ProviderStatus(
        name=name,
        display_name=name,
        description="",
        status="ready",
        media_types=media_types,
        capabilities=[],
        required_keys=[],
        configured_keys=[],
        missing_keys=[],
    )


class _FakeConfigService:
    """Minimal ConfigService fake that only implements what the resolver needs."""

    def __init__(
        self,
        settings: dict[str, str] | None = None,
        *,
        ready_providers: list[ProviderStatus] | None = None,
    ):
        self._settings = settings or {}
        self._ready_providers = ready_providers

    async def get_setting(self, key: str, default: str = "") -> str:
        return self._settings.get(key, default)

    async def get_default_video_backend(self) -> tuple[str, str]:
        return ("gemini-aistudio", "veo-3.1-fast-generate-preview")

    async def get_default_image_backend(self) -> tuple[str, str]:
        return ("gemini-aistudio", "gemini-3.1-flash-image-preview")

    async def get_provider_config(self, provider: str) -> dict[str, str]:
        return {"api_key": f"key-{provider}"}

    async def get_all_provider_configs(self) -> dict[str, dict[str, str]]:
        return {"gemini-aistudio": {"api_key": "key-aistudio"}}

    async def get_all_providers_status(self) -> list[ProviderStatus]:
        if self._ready_providers is not None:
            return self._ready_providers
        return [_make_ready_provider("gemini-aistudio", ["text", "image", "video"])]


class TestVideoGenerateAudio:
    """Verify defaults, global config, and project overrides for video_generate_audio."""

    async def test_default_is_false_when_db_empty(self, tmp_path):
        """Return False when the DB has no value."""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={})
        result = await resolver._resolve_video_generate_audio(fake_svc, project_name=None)
        assert result is False

    async def test_global_true(self, tmp_path):
        """Return True when the DB value is 'true'."""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={"video_generate_audio": "true"})
        result = await resolver._resolve_video_generate_audio(fake_svc, project_name=None)
        assert result is True

    async def test_global_false(self, tmp_path):
        """Return False when the DB value is 'false'."""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={"video_generate_audio": "false"})
        result = await resolver._resolve_video_generate_audio(fake_svc, project_name=None)
        assert result is False

    async def test_bool_parsing_variants(self, tmp_path):
        """Verify parsing of common boolean strings."""
        resolver = ConfigResolver.__new__(ConfigResolver)
        for val, expected in [("TRUE", True), ("1", True), ("yes", True), ("0", False), ("no", False), ("", False)]:
            fake_svc = _FakeConfigService(settings={"video_generate_audio": val} if val else {})
            result = await resolver._resolve_video_generate_audio(fake_svc, project_name=None)
            assert result is expected, f"Failed for {val!r}: got {result}"

    async def test_project_override_true_over_global_false(self, tmp_path):
        """A project-level True override should beat a global False."""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={"video_generate_audio": "false"})
        with patch("lib.config.resolver.get_project_manager") as mock_pm:
            mock_pm.return_value.load_project.return_value = {"video_generate_audio": True}
            result = await resolver._resolve_video_generate_audio(fake_svc, project_name="demo")
        assert result is True

    async def test_project_override_false_over_global_true(self, tmp_path):
        """A project-level False override should beat a global True."""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={"video_generate_audio": "true"})
        with patch("lib.config.resolver.get_project_manager") as mock_pm:
            mock_pm.return_value.load_project.return_value = {"video_generate_audio": False}
            result = await resolver._resolve_video_generate_audio(fake_svc, project_name="demo")
        assert result is False

    async def test_project_none_skips_override(self, tmp_path):
        """Do not load project config when project_name is None."""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={"video_generate_audio": "true"})
        result = await resolver._resolve_video_generate_audio(fake_svc, project_name=None)
        assert result is True

    async def test_project_override_string_value(self, tmp_path):
        """Project overrides should also parse correctly when stored as strings."""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={"video_generate_audio": "true"})
        with patch("lib.config.resolver.get_project_manager") as mock_pm:
            mock_pm.return_value.load_project.return_value = {"video_generate_audio": "false"}
            result = await resolver._resolve_video_generate_audio(fake_svc, project_name="demo")
        assert result is False


class TestDefaultBackends:
    """Verify video/image backend resolution for explicit values and auto-resolve."""

    async def test_video_backend_explicit(self):
        """Return the explicit DB value when present."""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(
            settings={"default_video_backend": "ark/doubao-seedance-1-5-pro"},
        )
        result = await resolver._resolve_default_video_backend(fake_svc, None)
        assert result == ("ark", "doubao-seedance-1-5-pro")

    async def test_video_backend_auto_resolve(self):
        """Auto-resolve should choose the default model from the first ready provider."""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={})
        # Auto-resolve finds a ready provider in PROVIDER_REGISTRY before checking custom providers.
        factory, engine = await _make_session()
        try:
            async with factory() as session:
                result = await resolver._resolve_default_video_backend(fake_svc, session)
            assert result[0] in ("gemini-aistudio", "gemini-vertex", "ark", "grok")
        finally:
            await engine.dispose()

    async def test_video_backend_auto_resolve_no_ready_provider(self):
        """Raise ValueError when no ready provider or custom provider is available."""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={}, ready_providers=[])
        factory, engine = await _make_session()
        try:
            async with factory() as session:
                with pytest.raises(ValueError, match="No available video provider found"):
                    await resolver._resolve_default_video_backend(fake_svc, session)
        finally:
            await engine.dispose()

    async def test_image_backend_explicit(self):
        """Return the explicit DB value when present."""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(
            settings={"default_image_backend": "grok/grok-2-image"},
        )
        result = await resolver._resolve_default_image_backend(fake_svc, None)
        assert result == ("grok", "grok-2-image")

    async def test_image_backend_auto_resolve(self):
        """Use auto-resolve when the DB has no explicit value."""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={})
        factory, engine = await _make_session()
        try:
            async with factory() as session:
                result = await resolver._resolve_default_image_backend(fake_svc, session)
            assert result[0] in ("gemini-aistudio", "gemini-vertex", "ark", "grok")
        finally:
            await engine.dispose()

    async def test_image_backend_auto_resolve_no_ready_provider(self):
        """Raise ValueError when no ready provider or custom provider is available."""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={}, ready_providers=[])
        factory, engine = await _make_session()
        try:
            async with factory() as session:
                with pytest.raises(ValueError, match="No available image provider found"):
                    await resolver._resolve_default_image_backend(fake_svc, session)
        finally:
            await engine.dispose()


class TestProviderConfig:
    """Verify that provider-config methods delegate to ConfigService."""

    async def test_provider_config(self):
        factory, engine = await _make_session()
        try:
            resolver = ConfigResolver.__new__(ConfigResolver)
            fake_svc = _FakeConfigService()
            async with factory() as session:
                result = await resolver._resolve_provider_config(fake_svc, session, "gemini-aistudio")
            assert result == {"api_key": "key-gemini-aistudio"}
        finally:
            await engine.dispose()

    async def test_all_provider_configs(self):
        factory, engine = await _make_session()
        try:
            resolver = ConfigResolver.__new__(ConfigResolver)
            fake_svc = _FakeConfigService()
            async with factory() as session:
                result = await resolver._resolve_all_provider_configs(fake_svc, session)
            assert "gemini-aistudio" in result
        finally:
            await engine.dispose()


class TestSessionReuse:
    """Verify session reuse behavior inside the session() context manager."""

    async def test_session_context_manager_reuses_single_session(self):
        """resolver.session() should create only one session for repeated calls."""
        factory, engine = await _make_session()
        try:
            call_count = 0
            real_call = factory.__call__

            def counting_factory():
                nonlocal call_count
                call_count += 1
                return real_call()

            resolver = ConfigResolver(factory)
            fake_backend = ("gemini-aistudio", "test-model")

            # Without session(): each call creates a new session.
            call_count = 0
            with (
                patch.object(resolver, "_session_factory", side_effect=counting_factory),
                patch.object(resolver, "_resolve_default_video_backend", return_value=fake_backend),
                patch.object(resolver, "_resolve_default_image_backend", return_value=fake_backend),
            ):
                await resolver.default_video_backend()
                await resolver.default_image_backend()
            assert call_count == 2, f"Without session(), 2 sessions should be created, got {call_count}"

            # With session(): only one session should be created.
            call_count = 0
            with patch.object(resolver, "_session_factory", side_effect=counting_factory):
                async with resolver.session() as r:
                    with (
                        patch.object(r, "_resolve_default_video_backend", return_value=fake_backend),
                        patch.object(r, "_resolve_default_image_backend", return_value=fake_backend),
                        patch.object(r, "_resolve_video_generate_audio", return_value=False),
                    ):
                        await r.default_video_backend()
                        await r.default_image_backend()
                        await r.video_generate_audio()
            # session() creates one, and inner calls reuse the bound session.
            assert call_count == 1, f"With session(), only 1 session should be created, got {call_count}"
        finally:
            await engine.dispose()

    async def test_bound_resolver_shares_session_object(self):
        """A bound resolver should return the same session object from _open_session."""
        factory, engine = await _make_session()
        try:
            resolver = ConfigResolver(factory)
            sessions_seen = []

            async with resolver.session() as r:
                async with r._open_session() as (s1, _):
                    sessions_seen.append(s1)
                async with r._open_session() as (s2, _):
                    sessions_seen.append(s2)

            assert sessions_seen[0] is sessions_seen[1]
        finally:
            await engine.dispose()

    async def test_unbound_resolver_creates_separate_sessions(self):
        """An unbound resolver should create a different session each time."""
        factory, engine = await _make_session()
        try:
            resolver = ConfigResolver(factory)
            sessions_seen = []

            async with resolver._open_session() as (s1, _):
                sessions_seen.append(s1)
            async with resolver._open_session() as (s2, _):
                sessions_seen.append(s2)

            assert sessions_seen[0] is not sessions_seen[1]
        finally:
            await engine.dispose()
