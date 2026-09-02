import time
import pytest
import unittest.mock as mock

from bleak import exc

import tion_btle.tion
from tion_btle.tion import Tion
from tion_btle.lite import TionLiteFamily
from tion_btle.lite import TionLite
from tion_btle.s3 import TionS3
from tion_btle.s4 import TionS4
from tion_btle.tion import retry, MaxTriesExceededError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "retries, repeats, succeed_run, t_delay",
    [
        pytest.param(0, 1, 0, 0, id="Succeed after first attempt with no retry"),
        pytest.param(1, 1, 0, 0, id="Succeed after first attempt with retry"),
        pytest.param(5, 4, 3, 0, id="Succeed after first 3rd attempt with 5 retry"),
        pytest.param(1, 2, 3, 0, id="Fail after one retry"),
        pytest.param(2, 2, 1, 2, id="Delay between retries"),
    ]
)
async def test_retry(retries: int, repeats: int, succeed_run: int, t_delay: int):
    class TestRetry:
        count = 0

        @retry(retries=retries, delay=t_delay)
        def a(self, _succeed_run: int = 0):
            if self.count <= _succeed_run:
                self.count += 1
                if self.count - 1 == _succeed_run:
                    return "expected_result"

            raise exc.BleakError

    i = TestRetry()
    start = time.time()

    if succeed_run < repeats:
        assert await i.a(_succeed_run=succeed_run) == "expected_result"
    else:
        with pytest.raises(MaxTriesExceededError) as c:
            await i.a(_succeed_run=succeed_run)

    end = time.time()

    assert i.count == repeats
    assert end - start >= t_delay


class TestLogLevels:
    count = 0

    def setUp(self):
        self.count = 0
        tion_btle.tion._LOGGER.debug = mock.MagicMock(name='method')
        tion_btle.tion._LOGGER.info = mock.MagicMock(name='method')
        tion_btle.tion._LOGGER.warning = mock.MagicMock(name='method')
        tion_btle.tion._LOGGER.critical = mock.MagicMock(name='method')

    @pytest.mark.asyncio
    async def test_debug_log_level(self):
        @retry(retries=0)
        async def debug():
            pass

        with mock.patch('tion_btle.tion._LOGGER') as log_mock:
            await debug()
            log_mock.debug.assert_called()
            log_mock.info.assert_not_called()
            log_mock.warning.assert_not_called()
            log_mock.critical.assert_not_called()

    @pytest.mark.asyncio
    async def test_warning_log_level(self):
        """Make sure that we have warnings for exception, but have no critical if all goes well finally"""
        @retry(retries=1)
        async def warning():
            if self.count == 0:
                self.count += 1
                raise exc.BleakError
            else:
                pass

        with mock.patch('tion_btle.tion._LOGGER') as log_mock:
            await warning()
            log_mock.warning.assert_called()
            log_mock.critical.assert_not_called()

    @pytest.mark.asyncio
    async def test_critical_log_level(self):
        """Make sure that we have message at critical level if all goes bad"""
        @retry(retries=0)
        async def critical():
            raise exc.BleakError

        with mock.patch('tion_btle.tion._LOGGER.critical') as log_mock:
            try:
                await critical()
            except MaxTriesExceededError:
                pass
            log_mock.assert_called()


@pytest.mark.parametrize(
    "raw_temperature, result",
    [
        [0x09, 9],
        [0xFF, -1]
    ]
)
def test_decode_temperature(raw_temperature, result):
    assert Tion.decode_temperature(raw_temperature) == result


@pytest.mark.parametrize(
    "instance",
    [Tion, TionLiteFamily, TionLite, TionS3, TionS4]
)
def test_mac(instance):
    target = 'foo'
    t_tion = instance(target)
    assert t_tion.mac == target


@pytest.mark.asyncio
async def test_new_bleak_client_is_created_for_each_connection():
    clients = []

    class FakeBleakClient:
        def __init__(self, device):
            self.device = device
            self.is_connected = False
            clients.append(self)

        async def connect(self):
            self.is_connected = True
            return True

        async def disconnect(self):
            self.is_connected = False

    with mock.patch("tion_btle.tion.BleakClient", FakeBleakClient):
        t_tion = Tion("foo")
        await t_tion._try_connect()
        await t_tion._disconnect()
        await t_tion._try_connect()

    assert len(clients) == 2
    assert clients[0] is not clients[1]


@pytest.mark.asyncio
async def test_direct_retry_uses_a_fresh_bleak_client():
    clients = []

    class FakeBleakClient:
        def __init__(self, device):
            self.device = device
            self.is_connected = False
            clients.append(self)

        async def connect(self):
            if len(clients) == 1:
                raise exc.BleakError("first connection failed")
            self.is_connected = True
            return True

    with (
        mock.patch("tion_btle.tion.BleakClient", FakeBleakClient),
        mock.patch("tion_btle.tion.asyncio.sleep", new=mock.AsyncMock()),
    ):
        await Tion("foo")._try_connect()

    assert len(clients) == 2
    assert clients[0] is not clients[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("instance", [Tion, TionLiteFamily, TionLite, TionS3, TionS4])
async def test_connection_factory_uses_latest_ble_device(instance):
    client = mock.MagicMock()
    client.is_connected = True
    connection_factory = mock.AsyncMock(return_value=client)
    t_tion = instance("old-device", connection_factory=connection_factory)

    t_tion.update_btle_device("new-device")
    await t_tion._try_connect()

    connection_factory.assert_awaited_once_with("new-device")


@pytest.mark.asyncio
async def test_connection_factory_owns_its_retry_policy():
    connection_factory = mock.AsyncMock(side_effect=exc.BleakError("failed"))
    t_tion = Tion("device", connection_factory=connection_factory)

    with pytest.raises(exc.BleakError):
        await t_tion._try_connect()

    connection_factory.assert_awaited_once_with("device")


@pytest.mark.asyncio
async def test_linux_notifications_force_bluez_start_notify():
    client = mock.MagicMock()
    client.is_connected = True
    client.start_notify = mock.AsyncMock()
    t_tion = Tion("foo")
    t_tion._btle = client

    with mock.patch("tion_btle.tion.sys.platform", "linux"):
        await t_tion._enable_notifications()

    client.start_notify.assert_awaited_once_with(
        t_tion.uuid_notify,
        t_tion._delegation.handleNotification,
        bluez={"use_start_notify": True},
    )
