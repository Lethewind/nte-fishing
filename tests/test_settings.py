from src.settings import ROOT_DIR, load_settings


def test_language_map_derives_window_titles_and_template_names(monkeypatch):
    monkeypatch.setenv("LANGUAGES", "jp,en")
    monkeypatch.setenv("WINDOW_TITLES_JP", "ゲーム,日本語")
    monkeypatch.setenv("WINDOW_TITLES_EN", "Game EN")

    configured = load_settings()

    assert [profile.lang for profile in configured.profiles] == ["jp", "en"]
    assert configured.profiles[0].title_aliases == ("ゲーム", "日本語")
    assert configured.profiles[0].result_template == ROOT_DIR / "assets" / "click_bank_jp.png"
    assert configured.profiles[1].title_aliases == ("Game EN",)
    assert configured.profiles[1].result_template == ROOT_DIR / "assets" / "click_bank_en.png"


def test_default_languages_map_to_existing_assets(monkeypatch):
    monkeypatch.delenv("LANGUAGES", raising=False)
    monkeypatch.delenv("WINDOW_TITLES_ZH", raising=False)
    monkeypatch.delenv("WINDOW_TITLES_ZHTW", raising=False)

    configured = load_settings()

    assert [profile.lang for profile in configured.profiles] == ["zh", "zhtw"]
    assert configured.profiles[0].title_aliases == ("异环", "異環")
    assert configured.profiles[1].title_aliases == ("NTE",)
    assert all(profile.result_template.is_file() for profile in configured.profiles)
