from buddy.safety import keep_alive


def test_keep_alive_logs_errors_and_keeps_the_handler_installed(capsys):
    @keep_alive
    def handler():
        raise RuntimeError("corrupt frame")

    assert handler() is True
    assert "corrupt frame" in capsys.readouterr().err


def test_keep_alive_passes_through_normal_results():
    @keep_alive
    def handler(x):
        return x * 2

    assert handler(21) == 42
