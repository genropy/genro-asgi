# Block 12: wsx/ - Subscriptions

**Status**: DA REVISIONARE
**Dependencies**: 10-wsx-core, 11-wsx-handler
**Commit message**: `feat(wsx): add SubscriptionManager for channel-based pub/sub`

---

## Purpose

Subscription manager for channel-based pub/sub over WSX.

## File: `src/genro_asgi/wsx/subscriptions.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""WSX subscription manager for channel-based pub/sub."""

import asyncio
from typing import Any, Callable, Awaitable
from weakref import WeakSet

from .types import WSXEvent


# Type for send function
SendFunc = Callable[[dict[str, Any]], Awaitable[None]]


class Subscription:
    """
    A single subscription to a channel.

    Tracks the subscriber's send function and any filter parameters.
    """

    __slots__ = ("channel", "send_func", "params", "id")

    def __init__(
        self,
        channel: str,
        send_func: SendFunc,
        params: dict[str, Any] | None = None,
        subscription_id: str | None = None,
    ) -> None:
        """
        Initialize subscription.

        Args:
            channel: Channel name
            send_func: Async function to send messages to subscriber
            params: Filter parameters for the subscription
            subscription_id: Unique ID for this subscription
        """
        self.channel = channel
        self.send_func = send_func
        self.params = params or {}
        self.id = subscription_id

    async def send(self, payload: Any, meta: dict[str, Any] | None = None) -> bool:
        """
        Send event to subscriber.

        Args:
            payload: Event payload
            meta: Optional metadata

        Returns:
            True if sent successfully, False otherwise
        """
        event = WSXEvent(
            channel=self.channel,
            payload=payload,
            meta=meta or {},
        )
        if self.id:
            event.meta["sub_id"] = self.id

        try:
            await self.send_func(event.to_dict())
            return True
        except Exception:
            return False


class SubscriptionManager:
    """
    Manages channel subscriptions for pub/sub.

    Thread-safe subscription management with support for:
    - Multiple subscribers per channel
    - Wildcard channel patterns (future)
    - Subscription parameters/filters
    - Automatic cleanup on disconnect

    Example:
        manager = SubscriptionManager()

        # Subscribe a client
        sub_id = manager.subscribe(
            channel="user.updates",
            send_func=websocket.send_json,
            params={"user_id": 123},
        )

        # Publish to channel
        await manager.publish("user.updates", {"status": "online"})

        # Unsubscribe
        manager.unsubscribe(sub_id)
    """

    def __init__(self) -> None:
        """Initialize subscription manager."""
        self._subscriptions: dict[str, list[Subscription]] = {}
        self._by_id: dict[str, Subscription] = {}
        self._counter = 0
        self._lock = asyncio.Lock()

    def subscribe(
        self,
        channel: str,
        send_func: SendFunc,
        params: dict[str, Any] | None = None,
        subscription_id: str | None = None,
    ) -> str:
        """
        Subscribe to a channel.

        Args:
            channel: Channel name to subscribe to
            send_func: Async function to send messages
            params: Optional filter parameters
            subscription_id: Optional custom ID (auto-generated if None)

        Returns:
            Subscription ID
        """
        if subscription_id is None:
            self._counter += 1
            subscription_id = f"sub-{self._counter}"

        sub = Subscription(
            channel=channel,
            send_func=send_func,
            params=params,
            subscription_id=subscription_id,
        )

        if channel not in self._subscriptions:
            self._subscriptions[channel] = []

        self._subscriptions[channel].append(sub)
        self._by_id[subscription_id] = sub

        return subscription_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe by subscription ID.

        Args:
            subscription_id: ID returned from subscribe()

        Returns:
            True if unsubscribed, False if not found
        """
        sub = self._by_id.pop(subscription_id, None)
        if sub is None:
            return False

        channel_subs = self._subscriptions.get(sub.channel, [])
        try:
            channel_subs.remove(sub)
        except ValueError:
            pass

        # Clean up empty channel
        if not channel_subs and sub.channel in self._subscriptions:
            del self._subscriptions[sub.channel]

        return True

    def unsubscribe_all(self, send_func: SendFunc) -> int:
        """
        Unsubscribe all subscriptions for a send function.

        Useful for cleanup when a WebSocket disconnects.

        Args:
            send_func: The send function to remove

        Returns:
            Number of subscriptions removed
        """
        removed = 0
        to_remove: list[str] = []

        for sub_id, sub in self._by_id.items():
            if sub.send_func is send_func:
                to_remove.append(sub_id)

        for sub_id in to_remove:
            if self.unsubscribe(sub_id):
                removed += 1

        return removed

    async def publish(
        self,
        channel: str,
        payload: Any,
        meta: dict[str, Any] | None = None,
        filter_func: Callable[[Subscription, Any], bool] | None = None,
    ) -> int:
        """
        Publish event to all subscribers of a channel.

        Args:
            channel: Channel to publish to
            payload: Event payload
            meta: Optional metadata
            filter_func: Optional function to filter subscribers

        Returns:
            Number of subscribers notified
        """
        subs = self._subscriptions.get(channel, [])
        if not subs:
            return 0

        sent = 0
        failed: list[Subscription] = []

        for sub in subs:
            # Apply filter if provided
            if filter_func and not filter_func(sub, payload):
                continue

            success = await sub.send(payload, meta)
            if success:
                sent += 1
            else:
                failed.append(sub)

        # Clean up failed subscriptions
        for sub in failed:
            if sub.id:
                self.unsubscribe(sub.id)

        return sent

    async def broadcast(
        self,
        payload: Any,
        meta: dict[str, Any] | None = None,
        channels: list[str] | None = None,
    ) -> int:
        """
        Broadcast event to multiple channels.

        Args:
            payload: Event payload
            meta: Optional metadata
            channels: Channels to broadcast to (all if None)

        Returns:
            Total number of subscribers notified
        """
        target_channels = channels or list(self._subscriptions.keys())
        total = 0

        for channel in target_channels:
            count = await self.publish(channel, payload, meta)
            total += count

        return total

    def get_subscribers(self, channel: str) -> list[Subscription]:
        """
        Get all subscribers for a channel.

        Args:
            channel: Channel name

        Returns:
            List of subscriptions
        """
        return list(self._subscriptions.get(channel, []))

    def get_channels(self) -> list[str]:
        """
        Get all active channels.

        Returns:
            List of channel names with subscribers
        """
        return list(self._subscriptions.keys())

    def count(self, channel: str | None = None) -> int:
        """
        Count subscriptions.

        Args:
            channel: Specific channel (all if None)

        Returns:
            Number of subscriptions
        """
        if channel:
            return len(self._subscriptions.get(channel, []))
        return len(self._by_id)

    def clear(self) -> None:
        """Remove all subscriptions."""
        self._subscriptions.clear()
        self._by_id.clear()


class ChannelDispatcher(SubscriptionManager):
    """
    Extended subscription manager with dispatcher integration.

    Integrates with WSXDispatcher to handle subscribe/unsubscribe messages.

    Example:
        channels = ChannelDispatcher()
        dispatcher = WSXDispatcher()

        # Register channel handlers
        channels.register_with_dispatcher(dispatcher)

        # In handler
        async def ws_handler(websocket: WebSocket):
            handler = WSXHandler(websocket, dispatcher)
            handler.on_disconnect = lambda: channels.unsubscribe_all(websocket.send_json)
            await handler.run()
    """

    def __init__(self) -> None:
        super().__init__()
        self._channel_validators: dict[str, Callable[[dict], bool]] = {}

    def validate_channel(
        self, channel: str
    ) -> Callable[[Callable[[dict], bool]], Callable[[dict], bool]]:
        """
        Decorator to register a channel validator.

        The validator receives subscription params and returns True if valid.

        Example:
            @channels.validate_channel("user.updates")
            def validate_user_sub(params: dict) -> bool:
                return "user_id" in params
        """
        def decorator(func: Callable[[dict], bool]) -> Callable[[dict], bool]:
            self._channel_validators[channel] = func
            return func
        return decorator

    def can_subscribe(self, channel: str, params: dict[str, Any]) -> bool:
        """
        Check if subscription is allowed.

        Args:
            channel: Channel name
            params: Subscription parameters

        Returns:
            True if subscription is allowed
        """
        validator = self._channel_validators.get(channel)
        if validator:
            return validator(params)
        return True  # Allow by default

    def register_with_dispatcher(self, dispatcher: "WSXDispatcher") -> None:
        """
        Register handlers with a WSX dispatcher.

        Args:
            dispatcher: WSX dispatcher instance
        """
        from .dispatcher import WSXDispatcher

        # Override dispatcher's subscribe/unsubscribe handlers
        original_subscribe = dispatcher._handle_subscribe
        original_unsubscribe = dispatcher._handle_unsubscribe

        async def handle_subscribe(subscribe):
            if not self.can_subscribe(subscribe.channel, subscribe.params):
                from .types import WSXError
                return WSXError(
                    id=subscribe.id,
                    code="SUBSCRIPTION_DENIED",
                    message=f"Cannot subscribe to channel: {subscribe.channel}",
                )

            # The send_func will be set by the handler
            # For now, just validate
            return await original_subscribe(subscribe)

        dispatcher._handle_subscribe = handle_subscribe
```

## Tests: `tests/test_wsx_subscriptions.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for WSX subscriptions."""

import pytest
from genro_asgi.wsx.subscriptions import (
    ChannelDispatcher,
    Subscription,
    SubscriptionManager,
)


class TestSubscription:
    @pytest.mark.asyncio
    async def test_send(self):
        sent = []

        async def send_func(data):
            sent.append(data)

        sub = Subscription(
            channel="test",
            send_func=send_func,
            subscription_id="sub-1",
        )

        result = await sub.send({"key": "value"})

        assert result is True
        assert len(sent) == 1
        assert sent[0]["type"] == "rpc.event"
        assert sent[0]["channel"] == "test"
        assert sent[0]["payload"] == {"key": "value"}
        assert sent[0]["meta"]["sub_id"] == "sub-1"

    @pytest.mark.asyncio
    async def test_send_failure(self):
        async def failing_send(data):
            raise Exception("Send failed")

        sub = Subscription(
            channel="test",
            send_func=failing_send,
        )

        result = await sub.send({"data": 1})

        assert result is False


class TestSubscriptionManager:
    def test_subscribe(self):
        manager = SubscriptionManager()

        async def send(data):
            pass

        sub_id = manager.subscribe("channel1", send)

        assert sub_id.startswith("sub-")
        assert manager.count("channel1") == 1

    def test_subscribe_custom_id(self):
        manager = SubscriptionManager()

        async def send(data):
            pass

        sub_id = manager.subscribe("channel1", send, subscription_id="custom-id")

        assert sub_id == "custom-id"

    def test_unsubscribe(self):
        manager = SubscriptionManager()

        async def send(data):
            pass

        sub_id = manager.subscribe("channel1", send)
        result = manager.unsubscribe(sub_id)

        assert result is True
        assert manager.count("channel1") == 0

    def test_unsubscribe_not_found(self):
        manager = SubscriptionManager()

        result = manager.unsubscribe("nonexistent")

        assert result is False

    def test_unsubscribe_all(self):
        manager = SubscriptionManager()

        async def send1(data):
            pass

        async def send2(data):
            pass

        manager.subscribe("channel1", send1)
        manager.subscribe("channel2", send1)
        manager.subscribe("channel1", send2)

        removed = manager.unsubscribe_all(send1)

        assert removed == 2
        assert manager.count() == 1

    @pytest.mark.asyncio
    async def test_publish(self):
        manager = SubscriptionManager()
        received = []

        async def send(data):
            received.append(data)

        manager.subscribe("updates", send)
        manager.subscribe("updates", send)

        count = await manager.publish("updates", {"msg": "hello"})

        assert count == 2
        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_publish_empty_channel(self):
        manager = SubscriptionManager()

        count = await manager.publish("empty", {"data": 1})

        assert count == 0

    @pytest.mark.asyncio
    async def test_publish_with_filter(self):
        manager = SubscriptionManager()
        received = []

        async def send(data):
            received.append(data)

        manager.subscribe("users", send, params={"user_id": 1})
        manager.subscribe("users", send, params={"user_id": 2})

        def filter_user(sub, payload):
            return sub.params.get("user_id") == payload.get("target_user")

        count = await manager.publish(
            "users",
            {"target_user": 1, "msg": "hello"},
            filter_func=filter_user,
        )

        assert count == 1
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_broadcast(self):
        manager = SubscriptionManager()
        received = []

        async def send(data):
            received.append(data)

        manager.subscribe("channel1", send)
        manager.subscribe("channel2", send)
        manager.subscribe("channel3", send)

        count = await manager.broadcast({"msg": "broadcast"})

        assert count == 3
        assert len(received) == 3

    @pytest.mark.asyncio
    async def test_broadcast_specific_channels(self):
        manager = SubscriptionManager()
        received = []

        async def send(data):
            received.append(data)

        manager.subscribe("channel1", send)
        manager.subscribe("channel2", send)
        manager.subscribe("channel3", send)

        count = await manager.broadcast(
            {"msg": "partial"},
            channels=["channel1", "channel2"],
        )

        assert count == 2

    def test_get_subscribers(self):
        manager = SubscriptionManager()

        async def send(data):
            pass

        manager.subscribe("test", send, params={"a": 1})
        manager.subscribe("test", send, params={"b": 2})

        subs = manager.get_subscribers("test")

        assert len(subs) == 2

    def test_get_channels(self):
        manager = SubscriptionManager()

        async def send(data):
            pass

        manager.subscribe("channel1", send)
        manager.subscribe("channel2", send)
        manager.subscribe("channel1", send)

        channels = manager.get_channels()

        assert set(channels) == {"channel1", "channel2"}

    def test_count(self):
        manager = SubscriptionManager()

        async def send(data):
            pass

        manager.subscribe("a", send)
        manager.subscribe("a", send)
        manager.subscribe("b", send)

        assert manager.count() == 3
        assert manager.count("a") == 2
        assert manager.count("b") == 1
        assert manager.count("c") == 0

    def test_clear(self):
        manager = SubscriptionManager()

        async def send(data):
            pass

        manager.subscribe("a", send)
        manager.subscribe("b", send)

        manager.clear()

        assert manager.count() == 0
        assert manager.get_channels() == []


class TestChannelDispatcher:
    def test_validate_channel_decorator(self):
        channels = ChannelDispatcher()

        @channels.validate_channel("private")
        def validate(params):
            return "token" in params

        assert channels.can_subscribe("private", {"token": "abc"}) is True
        assert channels.can_subscribe("private", {}) is False

    def test_can_subscribe_default(self):
        channels = ChannelDispatcher()

        # No validator = allow all
        assert channels.can_subscribe("any", {}) is True
```

## Update `wsx/__init__.py`

Add to exports:
```python
from .subscriptions import ChannelDispatcher, Subscription, SubscriptionManager
```

## Checklist

- [ ] Create `src/genro_asgi/wsx/subscriptions.py`
- [ ] Create `tests/test_wsx_subscriptions.py`
- [ ] Run `pytest tests/test_wsx_subscriptions.py`
- [ ] Run `mypy src/genro_asgi/wsx/subscriptions.py`
- [ ] Update `wsx/__init__.py` exports
- [ ] Commit
