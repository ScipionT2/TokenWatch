"""Token-Tracker CLI tests."""

from pathlib import Path

from src import cli


class TestCLI:
    def test_parser_accepts_commands(self):
        parser = cli.build_parser()
        assert parser.parse_args(["init"]).command == "init"
        assert parser.parse_args(["status"]).command == "status"
        assert parser.parse_args(["preflight"]).command == "preflight"
        args = parser.parse_args(["serve", "--host", "127.0.0.1", "--port", "9000", "--reload"])
        assert args.command == "serve"
        assert args.host == "127.0.0.1"
        assert args.port == 9000
        assert args.reload is True
        demo_args = parser.parse_args(["demo", "--reset"])
        assert demo_args.command == "demo"
        assert demo_args.reset is True

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
        assert "Token-Tracker status" in text
        assert "/dashboard" in text
        assert "OpenAI proxy forwarding" in text
        assert "Preflight:" in text

    def test_preflight_text_reports_status_and_fixes(self):
        text = cli.preflight_text()
        assert "Token-Tracker production preflight" in text
        assert "Status:" in text
        assert "admin_key" in text

    def test_seed_demo_data_creates_requests_and_project(self):
        msg = cli.seed_demo_data(reset=True)
        assert "demo data seeded" in msg.lower()
        assert "Demo API key" in msg
        from src.services.request_logger import request_logger
        from src.services.projects import project_store
        assert request_logger.count() == 10
        assert len(project_store.list_projects()) == 1

    def test_main_status_returns_zero(self, capsys):
        code = cli.main(["status"])
        out = capsys.readouterr().out
        assert code == 0
        assert "Token-Tracker status" in out

    def test_main_preflight_returns_zero(self, capsys):
        code = cli.main(["preflight"])
        out = capsys.readouterr().out
        assert code == 0
        assert "production preflight" in out
