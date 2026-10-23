"""Headless tests of the MeshOmit screen with a fake node. Run: python -m pytest tests -q"""
import asyncio
import json
import os
import shutil
import sys
import tempfile

os.environ.pop("NO_COLOR", None)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from textual.widgets import Input, Label, OptionList, RichLog  # noqa: E402

from fake_node import ALICE_KEY, BOB_KEY, channel_msg, dm, make_config, start  # noqa: E402
from meshomit.app import ALL, MeshOmitApp, RoomScreen, SendScreen, load_config  # noqa: E402

SIZE = (170, 50)


def run(coro_fn):
    """pytest without plugins: each test is a sync function that runs its coroutine in a fresh loop and
    a fresh temporary folder (left behind only if Windows still holds a file in it)."""
    tmp = tempfile.mkdtemp(prefix="meshomit_test_")
    try:
        asyncio.run(coro_fn(tmp))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def nick_names(app):
    lst = app.query_one("#nicks", OptionList)
    return [str(lst.get_option_at_index(i).prompt).split("  ")[0].strip() for i in range(lst.option_count)]


def window_names(app):
    lst = app.query_one("#channels", OptionList)
    return [str(lst.get_option_at_index(i).prompt).strip() for i in range(lst.option_count)]


def feed_text(app, n=3):
    log = app.query_one("#conversation", RichLog)
    return " ".join(s.text.strip() for s in log.lines[-n:])


def find_in_feed(app, needle):
    """(x, y) offset inside the feed widget of the first occurrence of needle, for mouse events."""
    log = app.query_one("#conversation", RichLog)
    for i, strip in enumerate(log.lines):
        if needle in strip.text:
            return strip.text.index(needle) + 3, i + 1 - log.scroll_offset.y
    raise AssertionError("not in the feed: " + needle)


def test_windows_unread_and_nicks():
    async def body(tmp):
        cfg_path = make_config(tmp)
        app = MeshOmitApp(load_config(cfg_path), cfg_path)
        async with app.run_test(size=SIZE) as pilot:
            eng = await start(app, pilot)
            assert [app.view_names[v] for v in app.views] == ["All", "Public", "#test"]
            eng.on_channel_msg(channel_msg(0, "Alice T-Deck", "hello public", hops=2))
            eng.on_channel_msg(channel_msg(1, "Bob Heltec", "Test", hops=3))
            await pilot.pause(0.3)
            await pilot.press("escape", "3")
            await pilot.pause(0.3)
            assert app.view == ("chan", 1)
            assert app.query_one("#conversation", RichLog).border_title == "#test"
            assert nick_names(app) == ["Bob Heltec"]
            eng.on_channel_msg(channel_msg(0, "Alice T-Deck", "again"))
            await pilot.pause(0.3)
            assert app.unread[("chan", 0)] == 1
            assert any(w.startswith("2 Public") and "(1)" in w for w in window_names(app))
            await pilot.press("2")
            await pilot.pause(0.3)
            assert app.unread[("chan", 0)] == 0 and nick_names(app) == ["Alice T-Deck"]
            eng.stop()
    run(body)


def test_input_line_sends_to_selected_window():
    async def body(tmp):
        cfg_path = make_config(tmp, {"0": "Public", "1": "#test", "2": "#room"})
        app = MeshOmitApp(load_config(cfg_path), cfg_path)
        async with app.run_test(size=SIZE) as pilot:
            eng = await start(app, pilot)
            inp = app.query_one("#send_line", Input)
            lab = app.query_one("#send_to", Label)
            assert app.focused is inp
            assert str(lab.render()) == "All -> #test"
            inp.value = "/w 4"
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert app.view == ("chan", 2) and str(lab.render()) == "#room"
            inp.value = "hello room"
            await pilot.press("enter")
            await pilot.pause(0.4)
            assert eng.mc.sent[-1] == ("chan", 2, "hello room") and inp.value == ""
            # letters are text while the line has the focus: no mode change, nothing sent
            await pilot.press("m", "t", "q")
            await pilot.pause(0.2)
            assert inp.value == "mtq" and eng.mode == "operator" and len(eng.mc.sent) == 1
            inp.value = ""
            # the t key follows the selected window once the line is left
            await pilot.press("escape", "t")
            await pilot.pause(0.4)
            assert eng.mc.sent[-1] == ("chan", 2, "Test")
            await pilot.press("1", "t")
            await pilot.pause(0.4)
            assert eng.mc.sent[-1] == ("chan", 1, "Test")  # All view: the beacon channel
            # Enter focuses the line again; an empty Enter opens the big send window
            await pilot.press("enter")
            await pilot.pause(0.2)
            assert app.focused is inp
            await pilot.press("enter")
            await pilot.pause(0.5)
            assert isinstance(app.screen, SendScreen)
            await pilot.press("escape")
            await pilot.pause(0.3)
            assert app.focused is inp
            eng.stop()
    run(body)


def test_private_messages_and_commands():
    async def body(tmp):
        cfg_path = make_config(tmp)
        app = MeshOmitApp(load_config(cfg_path), cfg_path)
        async with app.run_test(size=SIZE) as pilot:
            eng = await start(app, pilot)
            inp = app.query_one("#send_line", Input)
            lab = app.query_one("#send_to", Label)
            inp.value = "/query Bob Heltec"
            await pilot.press("enter")
            await pilot.pause(0.4)
            assert app.view == ("dm", BOB_KEY) and str(lab.render()) == "<Bob Heltec>"
            inp.value = "secret hello"
            await pilot.press("enter")
            await pilot.pause(0.4)
            assert eng.mc.sent[-1] == ("dm", BOB_KEY, "secret hello")
            # Bob answers into the same window
            eng.on_contact_msg(dm("123456012345", "hi back"))
            await pilot.pause(0.3)
            assert "hi back" in feed_text(app, 4)
            # /msg with a two-word name, from any window
            inp.value = "/msg Alice T-Deck hi alice"
            await pilot.press("enter")
            await pilot.pause(0.4)
            assert eng.mc.sent[-1] == ("dm", ALICE_KEY, "hi alice")
            assert ("dm", ALICE_KEY) in app.views
            # mode commands
            inp.value = "/bot"
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert eng.mode == "bot"
            inp.value = "/op"
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert eng.mode == "operator"
            inp.value = "/nosuch"
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert "Unknown command" in feed_text(app, 4)
            eng.stop()
    run(body)


def test_click_name_in_feed():
    async def body(tmp):
        cfg_path = make_config(tmp)
        app = MeshOmitApp(load_config(cfg_path), cfg_path)
        async with app.run_test(size=SIZE) as pilot:
            eng = await start(app, pilot)
            eng.on_channel_msg(channel_msg(0, "Alice T-Deck", "hello public"))
            eng.on_channel_msg(channel_msg(0, "Zed", "nobody knows me"))
            await pilot.pause(0.3)
            log = app.query_one("#conversation", RichLog)
            x, y = find_in_feed(app, "<Alice")
            await pilot.hover("#conversation", offset=(x, y))
            await pilot.pause(0.3)
            assert "@click" in log.hover_style.meta
            await pilot.click("#conversation", offset=(x, y))
            await pilot.pause(0.5)
            inp = app.query_one("#send_line", Input)
            assert app.view == ("dm", ALICE_KEY) and app.focused is inp
            # an unknown station: back to its channel with a mention typed
            await pilot.press("escape", "1")
            await pilot.pause(0.3)
            x, y = find_in_feed(app, "<Zed")
            await pilot.click("#conversation", offset=(x, y))
            await pilot.pause(0.5)
            assert inp.value == "@[Zed] " and app.view == ("chan", 0)
            eng.stop()
    run(body)


def test_invite_join_marks_creator_and_saves_config():
    async def body(tmp):
        cfg_path = make_config(tmp)
        app = MeshOmitApp(load_config(cfg_path), cfg_path)
        async with app.run_test(size=SIZE) as pilot:
            eng = await start(app, pilot)
            key = "00112233445566778899aabbccddeeff"
            eng.on_contact_msg(dm("abcdef012345", "join me on channel secretgroup, key " + key))
            await pilot.pause(0.3)
            assert eng.pending_invite["name"] == "secretgroup" and eng.pending_invite["from"] == "Alice T-Deck"
            await pilot.press("escape", "1", "j")
            await pilot.pause(0.5)
            assert isinstance(app.screen, RoomScreen)
            assert app.screen.query_one("#room_name", Input).value == "secretgroup"
            await pilot.click("#go")
            await pilot.pause(0.8)
            set_ch = [s for s in eng.mc.sent if s[0] == "set_channel"][-1]
            assert set_ch[1] == 2 and set_ch[2] == "secretgroup" and set_ch[3].hex() == key
            assert eng.rooms["secretgroup"]["creator"] == "Alice T-Deck"
            assert app.view == ("chan", 2)
            assert nick_names(app)[0] == "*Alice T-Deck"
            assert any("secretgroup" in w and "*Alice T-Deck" in w for w in window_names(app))
            with open(cfg_path, encoding="utf-8") as f:
                saved = json.load(f)
            assert saved["channels"]["2"] == "secretgroup" and saved["rooms"]["secretgroup"]["secret"] == key
            eng.stop()
    run(body)


def test_whois_and_distance_tag():
    async def body(tmp):
        cfg_path = make_config(tmp)
        app = MeshOmitApp(load_config(cfg_path), cfg_path)
        async with app.run_test(size=SIZE) as pilot:
            eng = await start(app, pilot)
            inp = app.query_one("#send_line", Input)
            inp.value = "/whois alice"
            await pilot.press("enter")
            await pilot.pause(0.4)
            text = feed_text(app)
            assert "Alice T-Deck: companion" in text and "8.0 km W of TestNode" in text and "openstreetmap" in text
            inp.value = "/whois Bob Heltec"
            await pilot.press("enter")
            await pilot.pause(0.4)
            assert "repeater" in feed_text(app, 2) and "No position" in feed_text(app, 2)
            inp.value = "/whois nobody"
            await pilot.press("enter")
            await pilot.pause(0.4)
            assert "not in the node's contact list" in feed_text(app, 4)
            eng.on_channel_msg(channel_msg(0, "Alice T-Deck", "hi", hops=2))
            await pilot.pause(0.3)
            app.refresh_nicks()
            await pilot.pause(0.2)
            lst = app.query_one("#nicks", OptionList)
            assert "8.0km W" in str(lst.get_option_at_index(0).prompt)
            eng.stop()
    run(body)


def test_all_view_is_default_and_room_join_is_silent():
    async def body(tmp):
        cfg_path = make_config(tmp)
        app = MeshOmitApp(load_config(cfg_path), cfg_path)
        async with app.run_test(size=SIZE) as pilot:
            eng = await start(app, pilot)
            assert app.view == ALL and eng.mode == "operator"
            idx, msg = await eng.add_room("#mytown", None)
            await pilot.pause(0.3)
            assert idx == 2 and "joined" in msg
            assert not [s for s in eng.mc.sent if s[0] == "chan"]  # nothing announced on the air
            assert eng.invite_text("#mytown", None).startswith("join me on channel #mytown")
            eng.stop()
    run(body)


def test_operator_reply_to_last_test():
    async def body(tmp):
        cfg_path = make_config(tmp)
        app = MeshOmitApp(load_config(cfg_path), cfg_path)
        async with app.run_test(size=SIZE) as pilot:
            eng = await start(app, pilot)
            inp = app.query_one("#send_line", Input)
            inp.value = "/reply"
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert "No test call heard" in feed_text(app, 3) and inp.value == ""
            eng.on_channel_msg(channel_msg(0, "W3DEF", "hello all", hops=3, snr=1.0))
            eng.on_channel_msg(channel_msg(1, "K1ABC", "Test", hops=2, snr=7.5))
            await pilot.pause(0.3)
            await pilot.press("escape", "1", "a")
            await pilot.pause(0.3)
            assert app.view == ("chan", 1) and app.focused is inp
            assert inp.value.startswith("@[K1ABC]") and "2 hops" in inp.value and "Springfield" in inp.value
            assert "+7.5" in inp.value or "copy" in inp.value
            inp.value = "/reply w3def"
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert app.view == ("chan", 0) and inp.value.startswith("@[W3DEF]") and "3 hops" in inp.value
            await pilot.press("enter")
            await pilot.pause(0.4)
            assert eng.mc.sent[-1][0] == "chan" and eng.mc.sent[-1][1] == 0 and "@[W3DEF]" in eng.mc.sent[-1][2]
            eng.stop()
    run(body)


def test_fields_in_typed_messages():
    from meshomit.app import FieldScreen

    async def body(tmp):
        cfg_path = make_config(tmp)
        app = MeshOmitApp(load_config(cfg_path), cfg_path)
        async with app.run_test(size=SIZE) as pilot:
            eng = await start(app, pilot)
            inp = app.query_one("#send_line", Input)
            eng.on_channel_msg(channel_msg(1, "K1ABC", "Test", hops=2, snr=7.5))
            await pilot.pause(0.3)
            # fields are filled in when sending, unknown ones stay as typed
            inp.value = "@[K1ABC] got you {hops} {via}, {location} {nosuch}"
            await pilot.press("enter")
            await pilot.pause(0.4)
            sent = eng.mc.sent[-1][2]
            assert sent.startswith("@[K1ABC] got you 2 hops ?, Springfield {nosuch}"), sent
            # typing { opens the list; Enter on an entry inserts the field
            inp.value = "@[K1ABC] "
            inp.cursor_position = len(inp.value)
            await pilot.press("left_curly_bracket")
            await pilot.pause(0.5)
            assert isinstance(app.screen, FieldScreen), type(app.screen).__name__
            await pilot.press("down", "enter")
            await pilot.pause(0.4)
            assert inp.value == "@[K1ABC] {hops}" and app.focused is inp, inp.value
            # the last entries are the emoticons: shown as pictures, inserted as text
            inp.value = "@[K1ABC] {hops} "
            inp.cursor_position = len(inp.value)
            await pilot.press("left_curly_bracket")
            await pilot.pause(0.5)
            assert isinstance(app.screen, FieldScreen)
            await pilot.press("end", "enter")
            await pilot.pause(0.4)
            assert inp.value == "@[K1ABC] {hops} +1 ", inp.value
            # Escape leaves the brace alone
            inp.value = "snr is {"
            inp.cursor_position = len(inp.value)
            await pilot.pause(0.5)
            assert isinstance(app.screen, FieldScreen)
            await pilot.press("escape")
            await pilot.pause(0.3)
            assert inp.value == "snr is {"
            eng.stop()
    run(body)


def test_saved_lines():
    from meshomit.app import FieldScreen, SnippetEditScreen, SnippetScreen

    async def body(tmp):
        cfg_path = make_config(tmp)
        app = MeshOmitApp(load_config(cfg_path), cfg_path)
        async with app.run_test(size=SIZE) as pilot:
            eng = await start(app, pilot)
            inp = app.query_one("#send_line", Input)
            eng.on_channel_msg(channel_msg(1, "K1ABC", "Test", hops=2, snr=7.5))
            await pilot.pause(0.3)
            # {{key}} typed by hand expands, with the fields inside it
            inp.value = "@[K1ABC] {{tx}}, {{hop}} {{nosuch}}"
            await pilot.press("enter")
            await pilot.pause(0.4)
            sent = eng.mc.sent[-1][2]
            assert sent.startswith("@[K1ABC] thank you, 2 hops ? from Springfield") and sent.endswith("{{nosuch}}"), sent
            # { { opens the saved lines; Enter inserts the highlighted one
            inp.value = "@[K1ABC] "
            inp.cursor_position = len(inp.value)
            await pilot.press("left_curly_bracket")
            await pilot.pause(0.4)
            assert isinstance(app.screen, FieldScreen)
            await pilot.press("left_curly_bracket")
            await pilot.pause(0.5)
            assert isinstance(app.screen, SnippetScreen), type(app.screen).__name__
            await pilot.press("down", "enter")
            await pilot.pause(0.4)
            assert inp.value == "@[K1ABC] thank you ", inp.value
            # a new saved line through the window, kept in messages.json
            inp.value = "{"
            inp.cursor_position = 1
            await pilot.pause(0.4)
            await pilot.press("left_curly_bracket")
            await pilot.pause(0.5)
            assert isinstance(app.screen, SnippetScreen)
            await pilot.press("n")
            await pilot.pause(0.4)
            assert isinstance(app.screen, SnippetEditScreen)
            app.screen.query_one("#snip_key", Input).value = "gn"
            app.screen.query_one("#snip_text", Input).value = "good night from {location}"
            await pilot.click("#snip_save")
            await pilot.pause(0.5)
            assert isinstance(app.screen, SnippetScreen)
            assert eng.msgs["snippets"]["gn"] == "good night from {location}"
            with open(os.path.join(tmp, "messages.json"), encoding="utf-8") as f:
                saved = json.load(f)
            assert saved["snippets"]["gn"] == "good night from {location}" and saved["quick"]
            await pilot.press("escape")
            await pilot.pause(0.3)
            assert app.focused is inp and inp.value == "{"
            eng.stop()
    run(body)


def test_contacts_manual_add_forget_clear():
    from fake_node import event as ev

    async def body(tmp):
        cfg_path = make_config(tmp)
        app = MeshOmitApp(load_config(cfg_path), cfg_path)
        async with app.run_test(size=SIZE) as pilot:
            eng = await start(app, pilot)
            inp = app.query_one("#send_line", Input)
            inp.value = "/contacts manual on"
            await pilot.press("enter")
            await pilot.pause(0.4)
            assert eng.manual_contacts and eng.mc.manual is True
            with open(cfg_path, encoding="utf-8") as f:
                assert json.load(f)["contacts"]["manual"] is True
            # an advert arrives: it waits instead of being added
            eng.on_new_contact(ev({"public_key": "77" * 32, "adv_name": "Carol Node", "type": 1, "out_path_len": 2,
                                   "last_advert": 1, "adv_lat": 0.0, "adv_lon": 0.0, "flags": 0, "out_path": ""}))
            await pilot.pause(0.2)
            assert "77" * 32 not in eng.mc.contacts and len(eng.pending_adverts()) == 1
            inp.value = "/add"
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert "Carol Node" in feed_text(app, 3)
            inp.value = "/add carol"
            await pilot.press("enter")
            await pilot.pause(0.4)
            assert "77" * 32 in eng.mc.contacts and eng.mc.sent[-1] == ("add_contact", "77" * 32)
            with open(os.path.join(tmp, "contacts.json"), encoding="utf-8") as f:
                assert [c["adv_name"] for c in json.load(f)] == ["Carol Node"]
            # forget
            inp.value = "/forget Carol Node"
            await pilot.press("enter")
            await pilot.pause(0.4)
            assert "77" * 32 not in eng.mc.contacts and eng.mc.sent[-1] == ("remove_contact", "77" * 32)
            # export and clear
            inp.value = "/contacts clear"
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert len(eng.mc.contacts) == 2 and "clear yes" in feed_text(app, 3)
            inp.value = "/contacts clear yes"
            await pilot.press("enter")
            await pilot.pause(0.8)
            assert len(eng.mc.contacts) == 0
            backups = [f for f in os.listdir(tmp) if f.startswith("contacts-backup-")]
            assert len(backups) == 1
            with open(os.path.join(tmp, backups[0]), encoding="utf-8") as f:
                assert len(json.load(f)) == 2
            eng.stop()
    run(body)


def test_at_opens_people_list():
    from meshomit.app import PeopleScreen

    async def body(tmp):
        cfg_path = make_config(tmp)
        app = MeshOmitApp(load_config(cfg_path), cfg_path)
        async with app.run_test(size=SIZE) as pilot:
            eng = await start(app, pilot)
            inp = app.query_one("#send_line", Input)
            eng.on_channel_msg(channel_msg(0, "Zed", "hello", hops=3))
            eng.on_channel_msg(channel_msg(1, "Alice T-Deck", "Test", hops=2))
            await pilot.pause(0.3)
            await pilot.press("escape", "3")  # the #test window: Alice first
            await pilot.pause(0.3)
            await pilot.press("enter")
            inp.value = "hi "
            inp.cursor_position = 3
            await pilot.press("at")
            await pilot.pause(0.5)
            assert isinstance(app.screen, PeopleScreen), type(app.screen).__name__
            assert [r[0] for r in app.screen.rows] == ["Alice T-Deck", "Zed"] and app.screen.rows[0][4] is True
            await pilot.press("enter")
            await pilot.pause(0.4)
            assert inp.value == "hi @[Alice T-Deck] " and app.focused is inp, inp.value
            # an @ inside a word (an email, say) does not open it
            inp.value = "mail me at x@y"
            inp.cursor_position = len(inp.value)
            await pilot.pause(0.4)
            assert not isinstance(app.screen, PeopleScreen)
            eng.stop()
    run(body)
