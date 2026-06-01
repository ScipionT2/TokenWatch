"""TokenWatch CLI tests."""

from pathlib import Path

from src import cli


class TestCLI:
    def test_parser_accepts_commands(self):
        parser = cli.build_parser()
        assert parser.parse_args(["init"]).command == "init"
        assert parser.parse_args(["status"]).command == "status"
        args = parser.parse_args(["serve", "--host", "127.0.0.1", "--port", "9000", "--reload"])
        assert args.command == "serve"
        assert args.host == "127.0.0.1"
        assert args.port == 9000
        assert args.reload is True

    def test_init_env_creates_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_example = tmp_path / ".env.example"
        env_example.write_text("OPENAI_API_KEY=\n")
        msg = cli.init_env(env_file=env_file, env_example=env_example)
        assert "initialized" in msg
        assert env_file.read_text() == "OPENAI_API_KEY=\n"

    def test_init_env_does_not_overwrite_existing_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("KEEP=1\n")
        msg = cli.init_env(env_file=env_file, env_example=tmp_path / "missing")
        assert "already initialized" in msg
        assert env_file.read_text() == "KEEP=1\n"

    def test_status_text_contains_dashboard_and_proxy_status(self):
        text = cli.status_text()
        assert "TokenWatch status" in text
        assert "/dashboard" in text
        assert "OpenAI proxy forwarding" in text

    def test_main_status_returns_zero(self, capsys):
        code = cli.main(["status"])
        out = capsys.readouterr().out
        assert code == 0
        assert "TokenWatch status" in out
