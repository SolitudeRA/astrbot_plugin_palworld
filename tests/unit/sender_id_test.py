from main import PalWorldTerminal


class _FakeEvent:
    def __init__(self, platform, sender):
        self._p, self._s = platform, sender
    def get_platform_name(self):
        return self._p
    def get_sender_id(self):
        return self._s


def test_sender_id_is_platform_scoped_composite():
    assert PalWorldTerminal._sender_id(_FakeEvent("aiocqhttp", "12345")) == "aiocqhttp:12345"


def test_sender_id_distinguishes_same_number_across_platforms():
    a = PalWorldTerminal._sender_id(_FakeEvent("aiocqhttp", "12345"))
    b = PalWorldTerminal._sender_id(_FakeEvent("telegram", "12345"))
    assert a != b
